import os
import asyncio
import json
import logging
import re
from typing import List
from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, BaseMessage,
)
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.types import RetryPolicy
import httpx
import tiktoken
from tenacity import retry_if_exception

from .config import SYSTEM_PROMPT, TOOLS, KB_TOOL, ROUTER_PROMPT
from .state import PolicyAgentState
from .semantic_cache import SemanticCache

logger = logging.getLogger(__name__)
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "4000"))


# ── Token counting & context trimming ──────────────────────────────────

def _count_tokens(messages: List[BaseMessage]) -> int:
    """Count tokens using cl100k_base encoder."""
    encoding = tiktoken.get_encoding("cl100k_base")
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
        num_tokens += len(encoding.encode(text)) + 4  # message overhead
    return num_tokens


def _trim_context(messages: List[BaseMessage]) -> List[BaseMessage]:
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
    def __init__(self, router_llm, llm, checkpointer):
        self.router_llm = router_llm
        self.llm = llm
        self.checkpointer = checkpointer
        self.cache = SemanticCache()
        self.graph = self._build_graph()

    async def _router_llm(self, state: PolicyAgentState) -> str:
        messages = state['messages']
        last_human_message = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_human_message = msg
                break

        if not last_human_message:
            return "TRANSACTIONAL"

        try:
            router_messages = [
                SystemMessage(content=ROUTER_PROMPT),
                HumanMessage(content=f"Classify this query: {last_human_message.content}")
            ]
            response = await self.router_llm.ainvoke(
                router_messages, config={"callbacks": []}
            )

            content = response.content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\n|```$", "", content, flags=re.IGNORECASE).strip()

            data = json.loads(content)
            intent = data.get("intent", "TRANSACTIONAL").upper()
            if "KNOWLEDGE" in intent:
                return "KNOWLEDGE_BASE"
            return "TRANSACTIONAL"
        except Exception as e:
            logger.warning(f"Failed to run router LLM: {e}. Defaulting to TRANSACTIONAL.")
            return "TRANSACTIONAL"

    async def _llm_call(self, state: PolicyAgentState):
        messages = state['messages']
        updates = {}
        if messages and isinstance(messages[-1], HumanMessage):
            iteration_count = 1
            intent = await self._router_llm(state)
            updates['intent'] = intent

            if intent == "KNOWLEDGE_BASE":
                cached = await asyncio.to_thread(self.cache.lookup, messages[-1].content)
                if cached:
                    updates['messages'] = AIMessage(content=cached)
                    updates['iteration_count'] = iteration_count
                    updates['cached_hit'] = True
                    return updates

        else:
            iteration_count = state.get('iteration_count', 0) + 1
            intent = state.get('intent', 'TRANSACTIONAL')

        force_stop = _force_stop(iteration_count)
        if force_stop:
            return force_stop

        if intent == "KNOWLEDGE_BASE":
            tool_mode = KB_TOOL
        else:
            tool_mode = TOOLS

        llm_with_tools = self.llm.bind_tools(tool_mode)
        trimmed_messages = _trim_context(messages)
        response = await llm_with_tools.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), *trimmed_messages]
        )
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
        if intent == "KNOWLEDGE_BASE" and isinstance(response, AIMessage) and not getattr(response, 'tool_calls', None):
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    await asyncio.to_thread(self.cache.store, msg.content, response.content)
                    break

        updates['messages'] = response
        updates['iteration_count'] = iteration_count
        return updates

    async def _should_continue(self, state: PolicyAgentState):
        last_msg = state['messages'][-1]

        if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
            tool_name = last_msg.tool_calls[0]['name']
            if tool_name == 'search_knowledge_base':
                return 'kb_tools'
            if state.get('intent') != 'KNOWLEDGE_BASE':
                return 'tools'

        return END

    def _build_graph(self):
        retry_exceptions = (
            ConnectionError,
            TimeoutError,
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
        )
        workflow = StateGraph(PolicyAgentState)
        workflow.add_node('llm_call', self._llm_call, retry_policy=RetryPolicy(
            max_attempts=3,
            retry_on=lambda e: isinstance(e, retry_exceptions),
        ))
        workflow.add_node('kb_tools', ToolNode(KB_TOOL))
        workflow.add_node('tools', ToolNode(TOOLS))

        workflow.add_edge(START, 'llm_call')

        workflow.add_conditional_edges(
            'llm_call',
            self._should_continue,
            {
                'tools': 'tools',
                'kb_tools': 'kb_tools',
                END: END
            }
        )

        workflow.add_edge('tools', 'llm_call')
        workflow.add_edge('kb_tools', 'llm_call')

        return workflow.compile(checkpointer=self.checkpointer)
