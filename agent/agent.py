import os
import asyncio
import json
import logging
import re
from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, BaseMessage,
)
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt.tool_node import ToolNode
import httpx
import tiktoken
from aiobreaker import CircuitBreaker, CircuitBreakerError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import timedelta

from .config import SYSTEM_PROMPT, ROUTER_PROMPT, OUT_OF_SCOPE_RESPONSE, ALL_TOOLS
from .pii import register_pii
from .state import PolicyAgentState
from .semaphores import LLM_SEMAPHORE, ROUTER_LLM_SEMAPHORE

logger = logging.getLogger(__name__)
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "4000"))

# ── Circuit Breaker & Retry ────────────────────────────────────────────

llm_breaker = CircuitBreaker(fail_max=5, timeout_duration=timedelta(seconds=30))

retry_exceptions = (
    ConnectionError,
    TimeoutError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)

# ── Token counting & context trimming ──────────────────────────────────
_encoding = tiktoken.get_encoding("cl100k_base")


def _count_tokens(messages: list[BaseMessage]) -> int:
    """Count tokens using cl100k_base encoder."""
    num_tokens = 0
    for msg in messages:
        content = msg.content
        if isinstance(content, list):
            text = " ".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            text = str(content) if content else ""
        num_tokens += len(_encoding.encode(text)) + 4  # message overhead
    return num_tokens


def _trim_context(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Trim conversation to fit within MAX_CONTEXT_TOKENS, keeping most recent messages."""

    if _count_tokens(messages) <= MAX_CONTEXT_TOKENS:
        return messages

    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    other_msgs = [m for m in messages if not isinstance(m, SystemMessage)]

    # Always keep system messages + last human message, trim from the front
    budget = MAX_CONTEXT_TOKENS - _count_tokens(system_msgs)
    trimmed_others = []
    for msg in reversed(other_msgs):
        candidate = [msg] + list(reversed(trimmed_others))
        if _count_tokens(candidate) <= budget:
            trimmed_others.insert(0, msg)
        else:
            # Ensure we keep at least the last human message
            has_human = any(isinstance(m, HumanMessage) for m in trimmed_others)
            if not has_human and isinstance(msg, HumanMessage):
                trimmed_others.insert(0, msg)
            break

    result = system_msgs + trimmed_others
    logger.info("Trimmed context %d → %d messages (%d → %d tokens)",
                len(messages), len(result),
                _count_tokens(messages), _count_tokens(result))
    return result


# ── Force stop ─────────────────────────────────────────────────────────

def _force_stop(iteration_count: int) -> dict | None:
    if iteration_count > int(os.getenv("MAX_ITERATIONS", "5")):
        return {
            'messages': [
                AIMessage(
                    content="I'm having trouble completing this request. "
                        "Let me connect you with a support agent."
                )
            ],
            'iteration_count': iteration_count,
        }
    return None


# ── PolicyAgent ────────────────────────────────────────────────────────

class PolicyAgent:
    def __init__(self, router_llm, llm, checkpointer, cache):
        self.router_llm = router_llm
        self.llm = llm
        self.checkpointer = checkpointer
        self.cache = cache
        self.graph = self._build_graph()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(retry_exceptions),
        reraise=True
    )
    @llm_breaker
    async def _invoke_router_llm_with_retry(self, router_messages):
        async with ROUTER_LLM_SEMAPHORE:
            return await self.router_llm.ainvoke(
                router_messages, config={"run_name": "router_llm"}
            )

    @llm_breaker
    async def _invoke_llm_with_circuit_breaker(self, llm_with_tools, messages):
        async with LLM_SEMAPHORE:
            return await llm_with_tools.ainvoke(messages)

    async def _route_intent(self, state: PolicyAgentState, config: RunnableConfig):
        """Separate graph node: classify user intent via the router LLM."""
        messages = state['messages']
        last_human_message = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_human_message = msg
                break

        if not last_human_message:
            return {"intent": "TRANSACTIONAL"}

        configurable = config.get("configurable", {})
        customer_phone = configurable.get("customer_phone")

        try:
            router_messages = [
                SystemMessage(content=ROUTER_PROMPT),
            ]
            if customer_phone:
                router_messages.append(SystemMessage(content="Context: The user is already authenticated and their identity is known. If they ask to check their own claims, policies, or account details, classify as TRANSACTIONAL even if they don't provide a phone number or email in the query."))
            
            router_messages.append(HumanMessage(content=f"Classify this query: {last_human_message.content}"))
            
            response = await self._invoke_router_llm_with_retry(router_messages)

            content = response.content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\n|```$", "", content, flags=re.IGNORECASE).strip()

            data = json.loads(content)
            intent = data.get("intent", "TRANSACTIONAL").upper()
            if "MIXED" in intent:
                return {"intent": "MIXED"}
            if "KNOWLEDGE" in intent:
                return {"intent": "KNOWLEDGE_BASE"}
            if "SCOPE" in intent or "OUT" in intent:
                return {"intent": "OUT_OF_SCOPE"}
            return {"intent": "TRANSACTIONAL"}
        except CircuitBreakerError:
            logger.error("Circuit breaker is open for router LLM. Defaulting to KNOWLEDGE_BASE.")
            return {"intent": "KNOWLEDGE_BASE"}
        except Exception as e:
            logger.warning(f"Failed to run router LLM after retries: {e}. Defaulting to KNOWLEDGE_BASE.")
            return {"intent": "KNOWLEDGE_BASE"}

    async def _llm_call(self, state: PolicyAgentState, config: RunnableConfig):
        messages = state['messages']
        updates = {}
        intent = state.get('intent', 'TRANSACTIONAL')

        if messages and isinstance(messages[-1], HumanMessage):
            iteration_count = 1

            if intent == "OUT_OF_SCOPE":
                updates['messages'] = AIMessage(content=OUT_OF_SCOPE_RESPONSE)
                updates['iteration_count'] = iteration_count
                return updates

            if intent == "KNOWLEDGE_BASE" and self.cache:
                cached = await self.cache.lookup(messages[-1].content)
                if cached:
                    updates['messages'] = AIMessage(content=cached)
                    updates['iteration_count'] = iteration_count
                    updates['cached_hit'] = True
                    return updates

        else:
            iteration_count = state.get('iteration_count', 0) + 1

        force_stop = _force_stop(iteration_count)
        if force_stop:
            return force_stop

        tool_mode = ALL_TOOLS

        llm_with_tools = self.llm.bind_tools(tool_mode)
        trimmed_messages = _trim_context(messages)
        configurable = config.get("configurable", {})
        customer_phone = configurable.get("customer_phone")
        customer_name = configurable.get("customer_name")
        
        system_prompt_content = SYSTEM_PROMPT
        if customer_phone and customer_name:
            masked_phone = register_pii(customer_phone, "PHONE")
            masked_name = register_pii(customer_name, "NAME")
            system_prompt_content += f"\n\n## Current User\nYou are speaking to {masked_name}. Their registered phone number is {masked_phone}.\nYou MUST use this phone number automatically when looking up their claims or policies. Do NOT ask them for their phone number again."

        try:
            response = await self._invoke_llm_with_circuit_breaker(
                llm_with_tools,
                [SystemMessage(content=system_prompt_content), *trimmed_messages]
            )
        except CircuitBreakerError:
            updates['messages'] = AIMessage(
                content="The service is temporarily unavailable due to high load. Please try again in a few moments."
            )
            updates['iteration_count'] = iteration_count
            return updates

        model_used = response.response_metadata.get("model_name", "unknown")
        logger.info("LLM call | intent=%s | model=%s | tools=%s | msg_count=%d (trimmed from %d)",
                    intent, model_used, [t.name for t in tool_mode],
                    len(trimmed_messages), len(messages))

        if hasattr(response, 'tool_calls') and response.tool_calls:
            logger.info("LLM wants tools: %s", [tc['name'] for tc in response.tool_calls])
        if response.content:
            preview = response.content[:120].replace("\n", "\\n")
            logger.info("LLM response | %.120s", preview)

        # Cache the KB response if the LLM answered directly (no tool calls)
        has_tool_calls = getattr(response, 'tool_calls', None)
        if intent == "KNOWLEDGE_BASE" and self.cache and isinstance(response, AIMessage) and not has_tool_calls:
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    await self.cache.store(msg.content, response.content)
                    break

        updates['messages'] = response
        updates['iteration_count'] = iteration_count
        return updates

    def _should_continue(self, state: PolicyAgentState):
        last_msg = state['messages'][-1]

        if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
            return 'all_tools'

        return END

    def _build_graph(self):
        workflow = StateGraph(PolicyAgentState)
        workflow.add_node('route_intent', self._route_intent)
        workflow.add_node('llm_call', self._llm_call)
        workflow.add_node('all_tools', ToolNode(ALL_TOOLS))

        # START → route_intent → llm_call → (tools loop or END)
        workflow.add_edge(START, 'route_intent')
        workflow.add_edge('route_intent', 'llm_call')

        workflow.add_conditional_edges(
            'llm_call',
            self._should_continue,
            {
                'all_tools': 'all_tools',
                END: END
            }
        )

        # Tools loop back to llm_call (not route_intent — intent is already set)
        workflow.add_edge('all_tools', 'llm_call')

        return workflow.compile(checkpointer=self.checkpointer)

