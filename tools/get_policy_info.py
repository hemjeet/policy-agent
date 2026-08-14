import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field
from langchain_core.tools import tool
from sqlalchemy import func

from data.db import SessionLocal
from data.models import Customer, Policy, Claim
from .retry import retry_on_db_error, RETRYABLE_EXCEPTIONS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class PolicyDetail(BaseModel):
    """Full details of a single insurance policy."""
    policy_number: str
    policy_type: str
    status: str
    premium_amount: float
    coverage_amount: float
    deductible: float = 0.0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    customer_name: str
    active_claims_count: int = 0


class PolicyInfoOutput(BaseModel):
    """Response from get_policy_info tool."""
    success: bool = True
    message: str = ""
    customer_name: Optional[str] = None
    policies: List[PolicyDetail] = Field(default_factory=list)


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
def get_policy_info(
    policy_number: Optional[str] = None,
    customer_email: Optional[str] = None,
    customer_phone: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> str:
    """Look up insurance policy details for a customer.

    Retrieves policy information including coverage amounts, premiums,
    deductibles, validity dates, and active claims count. Use this when
    a customer asks about their policy coverage, premium, expiry date,
    or wants to see what policies they have.

    Args:
        policy_number: A specific policy number (e.g. 'POL-HLT-2024-001').
        customer_email: The customer's registered email address.
        customer_phone: The customer's registered phone number.
        status_filter: Optional filter by status ('active', 'expired', 'cancelled', 'pending').

    At least one of policy_number, customer_email, or customer_phone must be provided.
    """
    output = PolicyInfoOutput(success=False, message="")
    db = SessionLocal()

    try:
        query = db.query(Policy)

        if policy_number:
            query = query.filter(Policy.policy_number == policy_number)
        elif customer_email:
            query = (
                query.join(Customer, Policy.customer_id == Customer.id)
                .filter(Customer.email == customer_email)
            )
        elif customer_phone:
            query = (
                query.join(Customer, Policy.customer_id == Customer.id)
                .filter(Customer.phone == customer_phone)
            )
        else:
            output.message = (
                "Please provide a policy number, customer email, or phone number to look up."
            )
            return output.model_dump_json()

        if status_filter:
            query = query.filter(Policy.status == status_filter.lower())

        policies = query.order_by(Policy.start_date.desc()).all()

        if not policies:
            output.message = (
                "No policies found matching the provided criteria. "
                "Please verify the information and try again."
            )
            return output.model_dump_json()

        # Get the customer name from the first policy's customer
        first_policy = policies[0]
        customer = db.query(Customer).filter(Customer.id == first_policy.customer_id).first()
        customer_name = customer.full_name if customer else "Unknown"

        output.customer_name = customer_name
        output.success = True

        for policy in policies:
            # Count active claims for this policy
            active_claims = (
                db.query(func.count(Claim.id))
                .filter(
                    Claim.policy_id == policy.id,
                    Claim.status.in_(["submitted", "under_review", "approved"]),
                )
                .scalar()
            )

            detail = PolicyDetail(
                policy_number=policy.policy_number,
                policy_type=str(policy.policy_type),
                status=str(policy.status),
                premium_amount=_safe(policy.premium_amount),
                coverage_amount=_safe(policy.coverage_amount),
                deductible=_safe(policy.deductible),
                start_date=_safe(policy.start_date),
                end_date=_safe(policy.end_date),
                description=policy.description,
                customer_name=customer_name,
                active_claims_count=active_claims or 0,
            )
            output.policies.append(detail)

        # Human-readable summary
        parts = []
        for p in output.policies:
            parts.append(
                f"{p.policy_number}: {p.policy_type} — "
                f"Coverage ₹{p.coverage_amount:,.0f}, "
                f"Premium ₹{p.premium_amount:,.0f}, "
                f"Status: {p.status}"
            )
        output.message = (
            f"Found {len(output.policies)} policy(ies) for {customer_name}. | "
            + " | ".join(parts)
        )

    except Exception as e:
        if isinstance(e, RETRYABLE_EXCEPTIONS):
            raise
        logger.exception("Error querying policies")
        output.message = f"Error while looking up policies: {str(e)}"
        output.success = False
    finally:
        db.close()

    return output.model_dump_json()
