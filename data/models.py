from sqlalchemy import (
    Column, String, Date, Boolean, Text, Numeric,
    ForeignKey, Enum, ARRAY, TIMESTAMP, Integer
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from .db import Base


# ---------------------------------------------------------------------------
# Enum values (must match the Postgres enums from the migration)
# ---------------------------------------------------------------------------

POLICY_TYPES = ("health", "auto", "home", "life", "travel")
POLICY_STATUSES = ("active", "expired", "cancelled", "pending")
CLAIM_STATUSES = ("submitted", "under_review", "approved", "denied", "paid", "closed")
KB_CATEGORIES = ("claims_process", "policy_management", "billing_payments", "coverage_info", "general_faq")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), index=True)
    date_of_birth = Column(Date)
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(100))
    pincode = Column(String(10))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    policies = relationship("Policy", back_populates="customer", cascade="all, delete-orphan")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_address(self):
        parts = [self.address_line1, self.address_line2, self.city, self.state]
        addr = ", ".join(p for p in parts if p)
        if self.pincode:
            addr += f" - {self.pincode}"
        return addr


class Policy(Base):
    __tablename__ = "policies"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    policy_number = Column(String(20), unique=True, nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_type = Column(Enum(*POLICY_TYPES, name="policy_type", create_type=False), nullable=False)
    status = Column(Enum(*POLICY_STATUSES, name="policy_status", create_type=False), nullable=False, default="active")
    premium_amount = Column(Numeric(12, 2), nullable=False)
    coverage_amount = Column(Numeric(14, 2), nullable=False)
    deductible = Column(Numeric(10, 2), default=0)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="policies")
    claims = relationship("Claim", back_populates="policy", cascade="all, delete-orphan")


class Claim(Base):
    __tablename__ = "claims"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    claim_number = Column(String(20), unique=True, nullable=False, index=True)
    policy_id = Column(UUID(as_uuid=True), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(Enum(*CLAIM_STATUSES, name="claim_status", create_type=False), nullable=False, default="submitted")
    claim_type = Column(String(100), nullable=False)
    claim_amount = Column(Numeric(12, 2), nullable=False)
    approved_amount = Column(Numeric(12, 2))
    description = Column(Text)
    incident_date = Column(Date, nullable=False)
    filed_date = Column(Date, nullable=False, server_default=func.current_date())
    resolved_date = Column(Date)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    policy = relationship("Policy", back_populates="claims")
    status_history = relationship("ClaimStatusHistory", back_populates="claim", cascade="all, delete-orphan",
                                  order_by="ClaimStatusHistory.created_at")


class ClaimStatusHistory(Base):
    __tablename__ = "claim_status_history"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status = Column(Enum(*CLAIM_STATUSES, name="claim_status", create_type=False))
    new_status = Column(Enum(*CLAIM_STATUSES, name="claim_status", create_type=False), nullable=False)
    notes = Column(Text)
    changed_by = Column(String(100), default="system")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relationships
    claim = relationship("Claim", back_populates="status_history")


class KnowledgeBase(Base):
    """Structured FAQ articles (optional, kept for direct Q&A lookups)."""
    __tablename__ = "langchain_pg_embedding"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    category = Column(Enum(*KB_CATEGORIES, name="kb_category", create_type=False), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    tags = Column(ARRAY(Text), default=[])
    is_published = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeBaseCache(Base):
    """Semantic cache for knowledge base query -> response pairs."""
    __tablename__ = "kb_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    embedding = Column(Vector(1536))
    hit_count = Column(Integer, default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
