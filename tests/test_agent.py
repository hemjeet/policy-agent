"""
Unit tests for the router prompt and intent classification logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from typesafe_sdk import TypeSafeError

from agent.agent import PolicyAgent


# ---------------------------------------------------------------------------
# Test: Router intent classification
# ---------------------------------------------------------------------------

class MockChoiceAnswer:
    def __init__(self, choice: str, confidence: float = 0.95, probabilities: dict = None):
        self.choice = choice
        self.confidence = confidence
        self.probabilities = probabilities or {choice: 0.95}


class MockSystemOneResponse:
    def __init__(self, intent_choice: str):
        self.choices = {"intent": MockChoiceAnswer(intent_choice)}


class TestRouterClassification:
    """Tests for the Jev (TypeSafe AI) intent classification."""

    @pytest.fixture
    def agent(self):
        """Create a PolicyAgent with mocked LLM and Jev client."""
        from langgraph.checkpoint.memory import MemorySaver
        mock_llm = MagicMock()
        mock_jev = AsyncMock()
        mock_checkpointer = MemorySaver()
        mock_cache = MagicMock()
        agent = PolicyAgent(
            llm=mock_llm,
            checkpointer=mock_checkpointer,
            cache=mock_cache,
            jev_client=mock_jev,
        )
        return agent

    @pytest.mark.asyncio
    async def test_knowledge_base_intent(self, agent):
        agent._jev_client.system_one = AsyncMock(
            return_value=MockSystemOneResponse("knowledge_base")
        )
        state = {"messages": [HumanMessage(content="How do I file a claim?")]}
        result = await agent._route_intent(state, {})
        assert result == {"intent": "KNOWLEDGE_BASE"}

    @pytest.mark.asyncio
    async def test_transactional_intent(self, agent):
        agent._jev_client.system_one = AsyncMock(
            return_value=MockSystemOneResponse("transactional")
        )
        state = {"messages": [HumanMessage(content="What is the status of my claim?")]}
        result = await agent._route_intent(state, {})
        assert result == {"intent": "TRANSACTIONAL"}

    @pytest.mark.asyncio
    async def test_mixed_intent(self, agent):
        agent._jev_client.system_one = AsyncMock(
            return_value=MockSystemOneResponse("mixed")
        )
        state = {"messages": [HumanMessage(content="Check my claims and explain the policy")]}
        result = await agent._route_intent(state, {})
        assert result == {"intent": "MIXED"}

    @pytest.mark.asyncio
    async def test_out_of_scope_intent(self, agent):
        agent._jev_client.system_one = AsyncMock(
            return_value=MockSystemOneResponse("out_of_scope")
        )
        state = {"messages": [HumanMessage(content="Write a Python script")]}
        result = await agent._route_intent(state, {})
        assert result == {"intent": "OUT_OF_SCOPE"}

    @pytest.mark.asyncio
    async def test_router_fallback_on_error(self, agent):
        agent._jev_client.system_one = AsyncMock(side_effect=TypeSafeError("Jev API timeout"))
        state = {"messages": [HumanMessage(content="Hello")]}
        result = await agent._route_intent(state, {})
        assert result == {"intent": "KNOWLEDGE_BASE"}  # Fallback on error

    @pytest.mark.asyncio
    async def test_router_with_no_human_message(self, agent):
        state = {"messages": [AIMessage(content="Hello")]}
        result = await agent._route_intent(state, {})
        assert result == {"intent": "TRANSACTIONAL"}  # Default when no human message


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
