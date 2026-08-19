import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from langchain_core.tools import tool
from sqlalchemy import func

from data.db import SessionLocal
from data.models import Customer, Policy, Claim
from .retry import retry_on_db_error, RETRYABLE_EXCEPTIONS

from agent.pii import resolve_pii, register_pii, mask_text
logger = logging.getLogger(__name__)


class CustomerProfile(BaseModel):
    """Customer profile returned by get_customer_info."""
    customer_id: str
    name: str
    email: str
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    total_policies: int = 0
    active_policies: int = 0
    total_claims: int = 0
    pending_claims: int = 0


class CustomerInfoOutput(BaseModel):
    """Response from get_customer_info tool."""
    success: bool = True
    message: str = ""
    customer: Optional[CustomerProfile] = None


def _safe(val):
    """Convert date/Decimal to string/float for serialization."""
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    return val


@tool
@retry_on_db_error()
def get_customer_info(
    email: Optional[str] = None,
    phone: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> str:
    """Look up customer profile information.

    Retrieves a customer's name, contact details, address, and summary
    counts (total policies, active policies, total claims, pending claims).
    Use this when you need to identify a customer or pull their profile.

    Args:
        email: The customer's registered email address.
        phone: The customer's registered phone number.
        customer_id: The customer's internal ID (UUID).

    At least one of email, phone, or customer_id must be provided.
    """
    output = CustomerInfoOutput(success=False, message="")
    db = SessionLocal()

    # Resolve token if passed masked arg
    resolved_email = resolve_pii(email) if email else None
    resolved_phone = resolve_pii(phone) if phone else None
    resolved_id = resolve_pii(customer_id) if customer_id else None

    try:
        query = db.query(Customer)

        if resolved_email:
            query = query.filter((Customer.email == resolved_email) | (Customer.email == email))
        elif resolved_phone:
            query = query.filter((Customer.phone == resolved_phone) | (Customer.phone == phone))
        elif resolved_id:
            query = query.filter((Customer.id == resolved_id) | (Customer.id == customer_id))
        else:
            output.message = (
                "Please provide an email, phone number, or customer ID to look up."
            )
            return mask_text(output.model_dump_json())

        customer = query.first()

        if not customer:
            output.message = (
                "No customer found matching the provided details. "
                "Please verify the information and try again."
            )
            return mask_text(output.model_dump_json())

        # Register customer PII in vault
        register_pii(str(customer.id), "CUSTOMER_ID")
        register_pii(customer.full_name, "NAME")
        register_pii(customer.first_name, "NAME")
        register_pii(customer.last_name, "NAME")
        register_pii(customer.email, "EMAIL")
        if customer.phone:
            register_pii(customer.phone, "PHONE")
        if customer.date_of_birth:
            register_pii(str(customer.date_of_birth), "DOB")
        if customer.full_address:
            register_pii(customer.full_address, "ADDRESS")
        if customer.city:
            register_pii(customer.city, "ADDRESS")
        if customer.state:
            register_pii(customer.state, "ADDRESS")
        if customer.pincode:
            register_pii(customer.pincode, "ADDRESS")

        total_policies = (
            db.query(func.count(Policy.id))
            .filter(Policy.customer_id == customer.id)
            .scalar()
        )
        active_policies = (
            db.query(func.count(Policy.id))
            .filter(Policy.customer_id == customer.id, Policy.status == "active")
            .scalar()
        )
        total_claims = (
            db.query(func.count(Claim.id))
            .join(Policy, Claim.policy_id == Policy.id)
            .filter(Policy.customer_id == customer.id)
            .scalar()
        )
        pending_claims = (
            db.query(func.count(Claim.id))
            .join(Policy, Claim.policy_id == Policy.id)
            .filter(
                Policy.customer_id == customer.id,
                Claim.status.in_(["submitted", "under_review"]),
            )
            .scalar()
        )

        output.customer = CustomerProfile(
            customer_id=str(customer.id),
            name=customer.full_name,
            email=customer.email,
            phone=customer.phone,
            date_of_birth=_safe(customer.date_of_birth),
            address=customer.full_address,
            total_policies=total_policies or 0,
            active_policies=active_policies or 0,
            total_claims=total_claims or 0,
            pending_claims=pending_claims or 0,
        )

        output.success = True
        output.message = (
            f"Found customer {customer.full_name} ({customer.email}). "
            f"Active policies: {active_policies or 0}. "
            f"Pending claims: {pending_claims or 0}."
        )

    except Exception as e:
        if isinstance(e, RETRYABLE_EXCEPTIONS):
            raise
        logger.exception("Error looking up customer")
        output.message = f"Error while looking up customer: {str(e)}"
        output.success = False
    finally:
        db.close()

    return mask_text(output.model_dump_json())
