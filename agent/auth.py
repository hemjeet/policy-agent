"""
OTP-based authentication for the Policy Agent.

Flow:
  1. POST /auth/send-otp  → generate OTP, store in Redis, log it (demo mode)
  2. POST /auth/verify-otp → verify OTP, issue JWT with customer_id
  3. All /chat requests    → decode JWT, inject customer_id into graph config

OTP is currently logged (not sent via SMS) for demo/testing.
Replace the logger.info line with a Twilio/MSG91 call for production.
"""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone

import jwt
import redis

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
OTP_LENGTH = int(os.getenv("OTP_LENGTH", "6"))
OTP_EXPIRY = int(os.getenv("OTP_EXPIRY_SECONDS", "300"))  # 5 minutes

# ── Redis client ───────────────────────────────────────────────────────
_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(_redis_url, decode_responses=True)


# ── OTP helpers ────────────────────────────────────────────────────────

def generate_otp() -> str:
    """Generate a cryptographically secure N-digit OTP."""
    return "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))


def store_otp(phone: str, otp: str) -> None:
    """Store OTP in Redis with TTL. Overwrites any existing OTP for this phone."""
    redis_client.setex(f"otp:{phone}", OTP_EXPIRY, otp)


def verify_otp(phone: str, otp: str) -> bool:
    """Verify OTP against Redis. Deletes on success to prevent reuse."""
    stored = redis_client.get(f"otp:{phone}")
    if stored and stored == otp:
        redis_client.delete(f"otp:{phone}")
        return True
    return False


# ── JWT helpers ────────────────────────────────────────────────────────

def create_token(customer_id: str, phone: str, customer_name: str) -> str:
    """Issue a JWT containing the customer identity."""
    payload = {
        "sub": customer_id,
        "phone": phone,
        "name": customer_name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
