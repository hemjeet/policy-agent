import os
import json
import logging
import re
import asyncio
from typing import List
from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, filter_messages, trim_messages, BaseMessage
)
from langchain_core.outputs import Generation
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt.tool_node import ToolNode
from langchain_redis import RedisSemanticCache
from langchain_openai import OpenAIEmbeddings
from langgraph.checkpoint.redis.aio import AsyncRedisSaver 
import tiktoken
from .config import (
    SYSTEM_PROMPT, TOOLS, KB_TOOL, ROUTER_PROMPT,
    REDIS_URL, KB_CACHE_THRESHOLD, KB_CACHE_TTL,
)
from .state import PolicyAgentState

logger = logging.getLogger(__name__)
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "4000"))
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "5"))


def tiktoken_counter(messages: list[BaseMessage]) -> int:
    """Fallback token counter using cl100k_base since deepseek model isn't recognized."""
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
    except KeyError:
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
        num_tokens += len(encoding.encode(text)) + 4
    return num_tokens


def _trim_context(messages: List[BaseMessage]) -> List[BaseMessage]:
    filtered = filter_messages(messages, include_types=["human", "ai", "tool"])
    trimmed = trim_messages(
        messages= filtered,
        strategy="last",
        start_on="human",
        include_system=False,
        max_tokens=MAX_CONTEXT_TOKENS,
        token_counter=tiktoken_counter

    )

    if not trimmed:
        trimmed = messages[-10:]
    logger.info("Trimmed to %d messages (from %d)", len(trimmed), len(messages))
    return trimmed


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


class PolicyAgentV2:
    def __init__(self, router_llm, llm, checkpointer, tools):
        self.router_llm = router_llm
        self.llm = llm
        self.checkpointer = checkpointer
        self.cache = RedisSemanticCache(
            redis_url=REDIS_URL,
            embeddings=OpenAIEmbeddings(model="text-embedding-3-small"),
            distance_threshold=0.1,
            ttl=KB_CACHE_TTL,
        )
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
            response = await self.router_llm.ainvoke(router_messages, config={"callbacks": []})

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
                cached = await asyncio.to_thread(self.cache.lookup, messages[-1].content, llm_string="kb")
                if cached:
                    updates['messages'] = AIMessage(content=cached[0].text)
                    updates['iteration_count'] = iteration_count
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
        logger.info("LLM call | intent=%s | tools=%s | msg_count=%d",
                    intent, [t.name for t in tool_mode], len(messages))
        trimmed = _trim_context(messages)
        
        response = await llm_with_tools.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), *trimmed]
        )

        if hasattr(response, 'tool_calls') and response.tool_calls:
            logger.info("LLM wants tools: %s", [tc['name'] for tc in response.tool_calls])
        if response.content:
            preview = response.content[:120].replace("\n", "\\n")
            logger.info("LLM response | %.120s", preview)

        updates['messages'] = response
        updates['iteration_count'] = iteration_count
        return updates

    async def _should_continue(self, state: PolicyAgentState):
        last_msg = state['messages'][-1]

        if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
            tool_name = last_msg.tool_calls[0]['name']
            if tool_name == 'search_knowledge_base':
                return 'kb_tools'
            return 'tools'

        if state.get('intent') == 'KNOWLEDGE_BASE' and isinstance(last_msg, AIMessage):
            for msg in reversed(state['messages']):
                if isinstance(msg, HumanMessage):
                    await asyncio.to_thread(
                        self.cache.update,
                        msg.content,
                        llm_string="kb",
                        return_val=[Generation(text=last_msg.content)],
                    )
                    break

        return END

    def _build_graph(self):
        workflow = StateGraph(PolicyAgentState)
        workflow.add_node('llm_call', self._llm_call)
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
