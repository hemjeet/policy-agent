"""
Shared pytest fixtures for the Policy Agent test suite.

All fixtures here use mocks so tests run in CI without
real databases, Redis, or LLM API keys.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage


@pytest.fixture
def mock_graph():
    """Mock the LangGraph agent graph with a canned response."""
    graph = AsyncMock()
    graph.ainvoke = AsyncMock(
        return_value={
            "messages": [AIMessage(content="Mocked AI response")]
        }
    )
    return graph


@pytest.fixture
def mock_graph_stream():
    """Mock the LangGraph agent graph for streaming."""
    graph = AsyncMock()

    async def fake_stream(*args, **kwargs):
        yield (
            AIMessage(content="Streamed chunk"),
            {"langgraph_node": "llm_call"},
        )

    graph.astream = fake_stream
    return graph


@pytest.fixture
def auth_headers():
    """Generate a valid JWT for test requests."""
    from agent.auth import create_token
    token = create_token(
        customer_id="00000000-0000-0000-0000-000000000001",
        phone="+91-0000000000",
        customer_name="Test User",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(mock_graph, mock_graph_stream):
    """
    Create a FastAPI TestClient with mocked app.state.

    Patches the lifespan so the app doesn't try to connect
    to real databases, Redis, or LLM APIs during tests.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_lifespan(app):
        app.state.graph = mock_graph
        app.state.vectorstore = MagicMock()
        yield

    with patch("app.lifespan", mock_lifespan):
        # Re-import to pick up the patched lifespan
        import importlib
        import app as app_module
        importlib.reload(app_module)
        app_module.app.router.lifespan_context = mock_lifespan

        # Set state directly for safety
        app_module.app.state.graph = mock_graph
        app_module.app.state.vectorstore = MagicMock()

        # Override auth dependency so chat tests don't need a real JWT
        from app import get_current_user
        app_module.app.dependency_overrides[get_current_user] = lambda: {
            "sub": "test-user-id",
            "phone": "+91-0000000000",
            "name": "Test User",
        }

        with TestClient(app_module.app) as test_client:
            yield test_client

        # Clean up overrides
        app_module.app.dependency_overrides.clear()
