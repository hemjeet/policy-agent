"""
Unit tests for OTP-based authentication.

Covers the full auth lifecycle:
  - OTP generation → storage → verification (agent.auth module)
  - JWT token creation and decoding (agent.auth module)
  - /auth/send-otp endpoint (app.py)
  - /auth/verify-otp endpoint (app.py)
  - Protected endpoint access with/without valid JWT (app.py)

All external dependencies (Redis, PostgreSQL) are mocked.
"""

import uuid
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
import jwt as pyjwt

from agent.auth import (
    generate_otp,
    store_otp,
    verify_otp,
    create_token,
    decode_token,
    JWT_SECRET,
    JWT_ALGORITHM,
    OTP_LENGTH,
)


# ═══════════════════════════════════════════════════════════════════════
#  Unit tests — agent.auth module (no FastAPI needed)
# ═══════════════════════════════════════════════════════════════════════


class TestGenerateOTP:
    """Tests for the generate_otp helper."""

    def test_otp_is_correct_length(self):
        otp = generate_otp()
        assert len(otp) == OTP_LENGTH

    def test_otp_is_numeric(self):
        otp = generate_otp()
        assert otp.isdigit()

    def test_otp_is_different_each_time(self):
        """OTPs should be unique (statistically — 10 samples)."""
        otps = {generate_otp() for _ in range(10)}
        assert len(otps) > 1  # at least 2 distinct values in 10 tries


class TestStoreAndVerifyOTP:
    """Tests for store_otp / verify_otp with a mocked Redis."""

    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        """Replace the module-level redis_client with a dict-backed fake."""
        self._store: dict[str, tuple[str, float]] = {}

        def fake_setex(key, ttl, value):
            self._store[key] = (value, time.time() + ttl)

        def fake_get(key):
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.time() > expires_at:
                del self._store[key]
                return None
            return value

        def fake_delete(key):
            self._store.pop(key, None)

        mock = MagicMock()
        mock.setex = fake_setex
        mock.get = fake_get
        mock.delete = fake_delete

        with patch("agent.auth.redis_client", mock):
            yield

    def test_verify_correct_otp(self):
        store_otp("+91-9999999999", "123456")
        assert verify_otp("+91-9999999999", "123456") is True

    def test_verify_wrong_otp(self):
        store_otp("+91-9999999999", "123456")
        assert verify_otp("+91-9999999999", "000000") is False

    def test_otp_is_single_use(self):
        """After successful verification the OTP must be consumed."""
        store_otp("+91-9999999999", "123456")
        assert verify_otp("+91-9999999999", "123456") is True
        assert verify_otp("+91-9999999999", "123456") is False  # reuse fails

    def test_verify_without_prior_store(self):
        assert verify_otp("+91-0000000000", "123456") is False

    def test_store_overwrites_previous_otp(self):
        store_otp("+91-9999999999", "111111")
        store_otp("+91-9999999999", "222222")
        assert verify_otp("+91-9999999999", "111111") is False
        assert verify_otp("+91-9999999999", "222222") is True

    def test_different_phones_are_independent(self):
        store_otp("+91-1111111111", "111111")
        store_otp("+91-2222222222", "222222")
        assert verify_otp("+91-1111111111", "111111") is True
        assert verify_otp("+91-2222222222", "222222") is True


class TestJWT:
    """Tests for create_token / decode_token."""

    _customer_id = "00000000-0000-0000-0000-000000000001"
    _phone = "+91-9876543210"
    _name = "Jane Doe"

    def test_token_round_trip(self):
        token = create_token(self._customer_id, self._phone, self._name)
        payload = decode_token(token)
        assert payload["sub"] == self._customer_id
        assert payload["phone"] == self._phone
        assert payload["name"] == self._name

    def test_token_contains_expiry(self):
        token = create_token(self._customer_id, self._phone, self._name)
        payload = decode_token(token)
        assert "exp" in payload
        assert "iat" in payload

    def test_expired_token_is_rejected(self):
        expired = pyjwt.encode(
            {
                "sub": self._customer_id,
                "phone": self._phone,
                "name": self._name,
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
                "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(expired)

    def test_tampered_token_is_rejected(self):
        token = create_token(self._customer_id, self._phone, self._name)
        # Flip a character in the signature
        tampered = token[:-5] + ("A" if token[-5] != "A" else "B") + token[-4:]
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(tampered)

    def test_wrong_secret_is_rejected(self):
        token = pyjwt.encode(
            {"sub": "x", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "wrong-secret",
            algorithm=JWT_ALGORITHM,
        )
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(token)


# ═══════════════════════════════════════════════════════════════════════
#  Integration tests — FastAPI /auth/* endpoints
# ═══════════════════════════════════════════════════════════════════════

def _make_customer(phone="+91-9876543210", cid=None, first="Jane", last="Doe"):
    """Build a fake Customer ORM object."""
    c = MagicMock()
    c.id = cid or uuid.UUID("00000000-0000-0000-0000-000000000001")
    c.phone = phone
    c.first_name = first
    c.last_name = last
    c.full_name = f"{first} {last}"
    return c


class TestSendOTPEndpoint:
    """Tests for POST /auth/send-otp."""

    def test_send_otp_success(self, client):
        """Valid phone returns 200 with demo_otp."""
        customer = _make_customer()
        with (
            patch("app.db_session") as mock_ctx,
            patch("app.store_otp"),
            patch("app.generate_otp", return_value="123456"),
        ):
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = customer
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            resp = client.post("/auth/send-otp", json={"phone": "+91-9876543210"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "OTP sent successfully"
        assert data["demo_otp"] == "123456"
        assert data["expires_in"] == 300

    def test_send_otp_unknown_phone(self, client):
        """Phone not in DB → 404."""
        with patch("app.db_session") as mock_ctx:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            resp = client.post("/auth/send-otp", json={"phone": "+91-0000000000"})

        assert resp.status_code == 404
        assert "No customer found" in resp.json()["detail"]

    def test_send_otp_rejects_short_phone(self, client):
        """Pydantic validation: phone must be >= 5 chars."""
        resp = client.post("/auth/send-otp", json={"phone": "123"})
        assert resp.status_code == 422

    def test_send_otp_rejects_missing_phone(self, client):
        resp = client.post("/auth/send-otp", json={})
        assert resp.status_code == 422


class TestVerifyOTPEndpoint:
    """Tests for POST /auth/verify-otp."""

    def test_verify_otp_success(self, client):
        """Correct OTP → 200 with JWT."""
        customer = _make_customer()
        with (
            patch("app.verify_otp_code", return_value=True),
            patch("app.db_session") as mock_ctx,
        ):
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = customer
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            resp = client.post(
                "/auth/verify-otp",
                json={"phone": "+91-9876543210", "otp": "123456"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["customer_name"] == "Jane Doe"

        # The returned token should be decodable
        payload = decode_token(data["access_token"])
        assert payload["sub"] == str(customer.id)
        assert payload["name"] == "Jane Doe"

    def test_verify_otp_wrong_code(self, client):
        """Wrong OTP → 401."""
        with patch("app.verify_otp_code", return_value=False):
            resp = client.post(
                "/auth/verify-otp",
                json={"phone": "+91-9876543210", "otp": "000000"},
            )

        assert resp.status_code == 401
        assert "Invalid or expired OTP" in resp.json()["detail"]

    def test_verify_otp_rejects_short_otp(self, client):
        """Pydantic validation: otp min_length=4."""
        resp = client.post(
            "/auth/verify-otp",
            json={"phone": "+91-9876543210", "otp": "12"},
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  Integration tests — Protected endpoints (JWT guard)
# ═══════════════════════════════════════════════════════════════════════


class TestProtectedEndpoints:
    """Verify JWT guard on /chat and /chat/stream."""

    @pytest.fixture(autouse=True)
    def _use_real_auth(self, client):
        """Remove the auth override so we test real JWT validation."""
        import app as app_module
        from app import get_current_user
        app_module.app.dependency_overrides.pop(get_current_user, None)
        yield
        # Restore the override for other tests
        app_module.app.dependency_overrides[get_current_user] = lambda: {
            "sub": "test-user-id",
            "phone": "+91-0000000000",
            "name": "Test User",
        }

    def test_chat_without_token_returns_401(self, client):
        resp = client.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 401

    def test_chat_with_invalid_token_returns_401(self, client):
        resp = client.post(
            "/chat",
            json={"message": "Hello"},
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert resp.status_code == 401

    def test_chat_with_expired_token_returns_401(self, client):
        expired = pyjwt.encode(
            {
                "sub": "some-id",
                "phone": "+91-0000000000",
                "name": "Expired User",
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
                "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )
        resp = client.post(
            "/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401

    def test_chat_with_valid_token_succeeds(self, client, auth_headers):
        resp = client.post(
            "/chat",
            json={"message": "Hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_stream_without_token_returns_401(self, client):
        resp = client.post("/chat/stream", json={"message": "Hello"})
        assert resp.status_code == 401

    def test_stream_with_valid_token_succeeds(self, client, auth_headers):
        resp = client.post(
            "/chat/stream",
            json={"message": "Hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
#  Full flow: send-otp → verify-otp → use token on /chat
# ═══════════════════════════════════════════════════════════════════════


class TestEndToEndAuthFlow:
    """Simulate a complete login-then-chat sequence."""

    def test_full_otp_login_then_chat(self, client):
        customer = _make_customer()

        # Step 1: Send OTP
        with (
            patch("app.db_session") as mock_ctx,
            patch("app.store_otp"),
            patch("app.generate_otp", return_value="999999"),
        ):
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = customer
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            send_resp = client.post("/auth/send-otp", json={"phone": "+91-9876543210"})

        assert send_resp.status_code == 200
        assert send_resp.json()["demo_otp"] == "999999"

        # Step 2: Verify OTP → get JWT
        with (
            patch("app.verify_otp_code", return_value=True),
            patch("app.db_session") as mock_ctx,
        ):
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = customer
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            verify_resp = client.post(
                "/auth/verify-otp",
                json={"phone": "+91-9876543210", "otp": "999999"},
            )

        assert verify_resp.status_code == 200
        token = verify_resp.json()["access_token"]

        # Step 3: Use the JWT to call /chat
        chat_resp = client.post(
            "/chat",
            json={"message": "What are my active policies?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert chat_resp.status_code == 200
        assert "response" in chat_resp.json()
