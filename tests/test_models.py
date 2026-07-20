"""
Unit tests for Pydantic schemas, agent state, and tool output models.
"""

import json
import pytest
from pydantic import ValidationError

from agent.state import PolicyAgentState
from tools.check_claim_status import ClaimStatusOutput, ClaimDetail, ClaimStatusEntry
from tools.get_customer_info import CustomerInfoOutput, CustomerProfile


# ---------------------------------------------------------------------------
# Test: Pydantic schemas (request/response models)
# ---------------------------------------------------------------------------

class TestChatRequestSchema:
    """Tests for the ChatRequest Pydantic model."""

    def test_valid_message(self):
        from app import ChatRequest
        req = ChatRequest(message="Hello agent")
        assert req.message == "Hello agent"
        assert req.thread_id is None

    def test_message_with_thread_id(self):
        from app import ChatRequest
        req = ChatRequest(message="Hello", thread_id="abc-123")
        assert req.thread_id == "abc-123"

    def test_empty_message_accepted(self):
        """app.py's ChatRequest has no min_length validator."""
        from app import ChatRequest
        req = ChatRequest(message="")
        assert req.message == ""


# ---------------------------------------------------------------------------
# Test: Tool output models
# ---------------------------------------------------------------------------

class TestClaimStatusOutput:
    """Tests for the ClaimStatusOutput model serialization."""

    def test_empty_output(self):
        output = ClaimStatusOutput(success=False, message="No customer found")
        data = json.loads(output.model_dump_json())
        assert data["success"] is False
        assert data["claims"] == []

    def test_output_with_claims(self):
        claim = ClaimDetail(
            claim_number="CLM-2024-0001",
            status="under_review",
            claim_type="health",
            claim_amount=50000.0,
            policy_number="POL-HLT-001",
            policy_type="health",
            customer_name="Rajesh Sharma",
            history=[
                ClaimStatusEntry(
                    old_status=None,
                    new_status="submitted",
                    notes="Claim filed",
                )
            ],
        )
        output = ClaimStatusOutput(
            success=True,
            message="Found 1 claim",
            customer_name="Rajesh Sharma",
            claims=[claim],
        )
        data = json.loads(output.model_dump_json())
        assert data["success"] is True
        assert len(data["claims"]) == 1
        assert data["claims"][0]["claim_number"] == "CLM-2024-0001"
        assert len(data["claims"][0]["history"]) == 1


class TestCustomerInfoOutput:
    """Tests for the CustomerInfoOutput model serialization."""

    def test_not_found_output(self):
        output = CustomerInfoOutput(success=False, message="No customer found")
        data = json.loads(output.model_dump_json())
        assert data["success"] is False
        assert data["customer"] is None

    def test_found_customer(self):
        profile = CustomerProfile(
            customer_id="uuid-123",
            name="Rajesh Sharma",
            email="rajesh@email.com",
            phone="+91-9876543210",
            total_policies=3,
            active_policies=2,
            total_claims=1,
            pending_claims=0,
        )
        output = CustomerInfoOutput(
            success=True,
            message="Found customer",
            customer=profile,
        )
        data = json.loads(output.model_dump_json())
        assert data["success"] is True
        assert data["customer"]["name"] == "Rajesh Sharma"
        assert data["customer"]["active_policies"] == 2


# ---------------------------------------------------------------------------
# Test: Agent state
# ---------------------------------------------------------------------------

class TestPolicyAgentState:
    """Tests for the PolicyAgentState TypedDict structure."""

    def test_state_has_required_keys(self):
        expected_keys = {
            "messages", "phone_number", "email", "customer_id",
            "policy_id", "claim_id", "iteration_count", "intent", "cached_hit",
        }
        assert set(PolicyAgentState.__annotations__.keys()) == expected_keys
