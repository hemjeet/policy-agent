import logging
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field
from typing import Optional, List
from langchain_core.tools import tool

from data.db import SessionLocal
from data.models import Customer, Policy, Claim, ClaimStatusHistory
from .retry import retry_on_db_error, RETRYABLE_EXCEPTIONS
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class ClaimStatusEntry(BaseModel):
    """A single entry in the claim status history timeline."""
    old_status: Optional[str] = Field(None, description="Previous status (None for initial submission)")
    new_status: str = Field(..., description="New status after the change")
    notes: Optional[str] = Field(None, description="Notes about the status change")
    changed_by: Optional[str] = Field(None, description="Who made the change")
    timestamp: Optional[str] = Field(None, description="When the change happened")


class ClaimDetail(BaseModel):
    """Full details of a single claim."""
    claim_number: str
    status: str
    claim_type: str
    claim_amount: float
    approved_amount: Optional[float] = None
    description: Optional[str] = None
    incident_date: Optional[str] = None
    filed_date: Optional[str] = None
    resolved_date: Optional[str] = None
    policy_number: str
    policy_type: str
    customer_name: str
    history: List[ClaimStatusEntry] = Field(default_factory=list)


class ClaimStatusOutput(BaseModel):
    """Response from check_claim_status tool."""
    success: bool = True
    message: str = ""
    customer_name: Optional[str] = None
    claims: List[ClaimDetail] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _safe(val):
    """Convert date/Decimal to string/float for serialization."""
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    return val


# ---------------------------------------------------------------------------
# LangChain Tool
# ---------------------------------------------------------------------------

@tool
@retry_on_db_error()
def check_claim_status(phone_number: str) -> str:
    """Look up all insurance claims for a customer by their registered phone number.

    Returns each claim's current status, details, and full status-change history.
    Use this when a customer asks about their claim status, claim timeline, or
    wants to know what happened with their claim.

    Args:
        phone_number: The customer's registered phone number (e.g. '+91-9876543210').
    """
    output = ClaimStatusOutput(success=False, message="")
    db = SessionLocal()

    try:
        # 1. Find the customer by phone number
        customer = db.query(Customer).filter(Customer.phone == phone_number).first()

        if not customer:
            output.message = (
                f"No customer found with phone number {phone_number}. "
                "Please verify the number or ask for their claim number."
            )
            return output.model_dump_json()

        output.customer_name = customer.full_name
        output.success = True

        # 2. Get all claims across all of the customer's policies
        claims = (
            db.query(Claim)
            .join(Policy, Claim.policy_id == Policy.id)
            .filter(Policy.customer_id == customer.id)
            .order_by(Claim.filed_date.desc())
            .all()
        )

        if not claims:
            output.message = (
                f"Customer {customer.full_name} found, but they have no claims on file."
            )
            return output.model_dump_json()

        # 3. Build the output for each claim
        for claim in claims:
            # The status_history relationship is already ordered by created_at
            history = [
                ClaimStatusEntry(
                    old_status=str(h.old_status) if h.old_status else None,
                    new_status=str(h.new_status),
                    notes=h.notes,
                    changed_by=h.changed_by,
                    timestamp=_safe(h.created_at),
                )
                for h in claim.status_history
            ]

            detail = ClaimDetail(
                claim_number=claim.claim_number,
                status=str(claim.status),
                claim_type=claim.claim_type,
                claim_amount=_safe(claim.claim_amount),
                approved_amount=_safe(claim.approved_amount),
                description=claim.description,
                incident_date=_safe(claim.incident_date),
                filed_date=_safe(claim.filed_date),
                resolved_date=_safe(claim.resolved_date),
                policy_number=claim.policy.policy_number,
                policy_type=str(claim.policy.policy_type),
                customer_name=customer.full_name,
                history=history,
            )
            output.claims.append(detail)

        # Human-readable summary for the LLM
        output.message = (
            f"Found {len(output.claims)} claim(s) for {customer.full_name}. "
            + " | ".join(
                f"{c.claim_number}: {c.status} (₹{c.claim_amount:,.0f})"
                for c in output.claims
            )
        )

    except Exception as e:
        if isinstance(e, RETRYABLE_EXCEPTIONS):
            raise
        logger.exception("Error querying claims")
        output.message = f"Error while looking up claims: {str(e)}"
        output.success = False
    finally:
        db.close()

    return output.model_dump_json()
