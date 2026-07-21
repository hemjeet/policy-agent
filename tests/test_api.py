"""
Unit tests for the FastAPI Policy Agent API.

These tests use mocked dependencies (LLM, DB, Redis) so they run
in CI without real credentials or infrastructure.
"""



# ---------------------------------------------------------------------------
# Test: Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_status(self, client):
        data = client.get("/health").json()
        assert data["status"] == "healthy"

    def test_health_contains_components(self, client):
        data = client.get("/health").json()
        assert "components" in data
        assert "graph" in data["components"]
        assert "vectorstore" in data["components"]


# ---------------------------------------------------------------------------
# Test: Chat endpoint
# ---------------------------------------------------------------------------

class TestChatEndpoint:
    """Tests for the /chat endpoint."""

    def test_chat_returns_response_and_thread_id(self, client, mock_graph):
        response = client.post("/chat", json={"message": "Hello"})
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "thread_id" in data
        assert data["response"] == "Mocked AI response"

    def test_chat_preserves_thread_id(self, client, mock_graph):
        response = client.post(
            "/chat",
            json={"message": "Hello", "thread_id": "test-thread-123"},
        )
        data = response.json()
        assert data["thread_id"] == "test-thread-123"

    def test_chat_generates_thread_id_when_missing(self, client, mock_graph):
        response = client.post("/chat", json={"message": "Hello"})
        data = response.json()
        assert data["thread_id"]  # Should be a non-empty UUID

    def test_chat_accepts_empty_message(self, client, mock_graph):
        """app.py doesn't enforce min_length — app_v2.py does."""
        response = client.post("/chat", json={"message": ""})
        assert response.status_code == 200

    def test_chat_accepts_blank_message(self, client, mock_graph):
        """app.py doesn't strip/reject blanks — app_v2.py does."""
        response = client.post("/chat", json={"message": "   "})
        assert response.status_code == 200

    def test_chat_rejects_missing_message(self, client):
        response = client.post("/chat", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: Chat stream endpoint
# ---------------------------------------------------------------------------

class TestChatStreamEndpoint:
    """Tests for the /chat/stream endpoint."""

    def test_stream_returns_event_stream(self, client, mock_graph_stream):
        response = client.post("/chat/stream", json={"message": "Hello"})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_stream_accepts_empty_message(self, client, mock_graph_stream):
        """app.py doesn't enforce min_length on stream endpoint."""
        response = client.post("/chat/stream", json={"message": ""})
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: CORS headers
# ---------------------------------------------------------------------------

class TestCORSHeaders:
    """Tests for CORS middleware configuration."""

    def test_cors_allows_origin(self, client):
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI should respond to preflight
        assert response.status_code in (200, 405)
