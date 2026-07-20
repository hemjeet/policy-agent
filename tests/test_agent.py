"""
Unit tests for the router prompt and intent classification logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, HumanMessage

from agent.agent import PolicyAgent


# ---------------------------------------------------------------------------
# Test: Router intent classification
# ---------------------------------------------------------------------------

class TestRouterClassification:
    """Tests for the router LLM intent classification."""

    @pytest.fixture
    def agent(self):
        """Create a PolicyAgent with mocked LLMs."""
        mock_llm = MagicMock()
        mock_router = AsyncMock()
        mock_checkpointer = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            # Patch SemanticCache to avoid Redis dependency
            mp.setattr("agent.agent.SemanticCache", MagicMock)
            agent = PolicyAgent(
                router_llm=mock_router,
                llm=mock_llm,
                checkpointer=mock_checkpointer,
                tools=[],
            )
        agent.router_llm = mock_router
        return agent

    @pytest.mark.asyncio
    async def test_knowledge_base_intent(self, agent):
        agent.router_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='{"intent": "KNOWLEDGE_BASE", "reason": "General question"}'
            )
        )
        state = {"messages": [HumanMessage(content="How do I file a claim?")]}
        result = await agent._router_llm(state)
        assert result == "KNOWLEDGE_BASE"

    @pytest.mark.asyncio
    async def test_transactional_intent(self, agent):
        agent.router_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='{"intent": "TRANSACTIONAL", "reason": "Specific claim query"}'
            )
        )
        state = {"messages": [HumanMessage(content="What is the status of my claim?")]}
        result = await agent._router_llm(state)
        assert result == "TRANSACTIONAL"

    @pytest.mark.asyncio
    async def test_router_fallback_on_error(self, agent):
        agent.router_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
        state = {"messages": [HumanMessage(content="Hello")]}
        result = await agent._router_llm(state)
        assert result == "TRANSACTIONAL"  # Should default to TRANSACTIONAL

    @pytest.mark.asyncio
    async def test_router_handles_markdown_wrapped_json(self, agent):
        agent.router_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='```json\n{"intent": "KNOWLEDGE_BASE", "reason": "FAQ"}\n```'
            )
        )
        state = {"messages": [HumanMessage(content="What is NCB?")]}
        result = await agent._router_llm(state)
        assert result == "KNOWLEDGE_BASE"

    @pytest.mark.asyncio
    async def test_router_with_no_human_message(self, agent):
        state = {"messages": [AIMessage(content="Hello")]}
        result = await agent._router_llm(state)
        assert result == "TRANSACTIONAL"  # Default when no human message


# ---------------------------------------------------------------------------
# Test: Force stop mechanism
# ---------------------------------------------------------------------------

class TestForceStop:
    """Tests for the iteration limit force-stop mechanism."""

    def test_no_stop_within_limit(self):
        from agent.agent import _force_stop
        result = _force_stop(3)
        assert result is None

    def test_stop_when_exceeding_limit(self):
        from agent.agent import _force_stop
        result = _force_stop(10)
        assert result is not None
        assert "messages" in result
        assert "connect you with a support agent" in result["messages"][0].content
