"""
Unit tests for the PII Vault, masking, unmasking, and streaming unmasker.
"""
import logging

import pytest

import agent.pii as pii_module
from agent.pii import (
    PIIVault,
    mask_text,
    unmask_text,
    register_pii,
    resolve_pii,
    pseudonymize,
    pseudonymize_or_redact,
    pseudonymize_text,
    PIILogFilter,
    StreamingUnmasker,
    pii_vault,
)


def test_pii_vault_basic_registration_and_resolve():
    vault = PIIVault()
    token = vault.register("+91-9876543210", "PHONE")
    assert token == "[PHONE_1]"
    assert vault.resolve(token) == "+91-9876543210"
    assert vault.resolve("Look up [PHONE_1]") == "Look up +91-9876543210"

    # Re-registering same value returns same canonical token
    token2 = vault.register("+91-9876543210", "PHONE")
    assert token2 == "[PHONE_1]"


def test_mask_and_unmask_regex_patterns():
    pii_vault.clear()

    raw_text = (
        "Customer Amit Kumar with email amit.kumar@example.com and phone +91-9876543210 "
        "has policy POL-HLT-2024-001 and claim CLM-2024-0001. "
        "Aadhaar: 1234 5678 9012, PAN: ABCDE1234F."
    )

    masked = mask_text(raw_text)

    # Verify PII is masked
    assert "amit.kumar@example.com" not in masked
    assert "+91-9876543210" not in masked
    assert "POL-HLT-2024-001" not in masked
    assert "CLM-2024-0001" not in masked
    assert "1234 5678 9012" not in masked
    assert "ABCDE1234F" not in masked

    assert "[EMAIL_1]" in masked
    assert "[PHONE_1]" in masked
    assert "[POLICY_NO_1]" in masked
    assert "[CLAIM_NO_1]" in masked
    assert "[AADHAAR_1]" in masked
    assert "[PAN_1]" in masked

    # Verify unmasking perfectly restores original text
    unmasked = unmask_text(masked)
    assert unmasked == raw_text


def test_streaming_unmasker_handles_split_tokens():
    pii_vault.clear()

    phone = "+91-9876543210"
    token = register_pii(phone, "PHONE")
    assert token == "[PHONE_1]"
    assert resolve_pii("[PHONE_1]") == phone

    # Simulate LLM chunking that splits token: "Hello [PHO" then "NE_1] here"
    chunks = ["Hello ", "[PHO", "NE_1]", " here"]

    unmasker = StreamingUnmasker(pii_vault)
    output_pieces = []
    for chunk in chunks:
        for piece in unmasker.process_chunk(chunk):
            output_pieces.append(piece)
    for piece in unmasker.flush():
        output_pieces.append(piece)

    full_output = "".join(output_pieces)
    assert full_output == "Hello +91-9876543210 here"


def test_register_and_resolve_database_entities():
    pii_vault.clear()

    register_pii("Priya Sharma", "NAME")
    register_pii("priya.sharma@example.com", "EMAIL")

    msg = "Found details for [NAME_1] with email [EMAIL_1]"
    unmasked = unmask_text(msg)
    assert unmasked == "Found details for Priya Sharma with email priya.sharma@example.com"


# ---------------------------------------------------------------------------
# One-way pseudonymization (local HMAC + KMS)
# ---------------------------------------------------------------------------

def test_pseudonymize_local_hmac_is_deterministic(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "")
    monkeypatch.setattr(pii_module, "PII_HMAC_KEY", "test-secret-key")

    a = pseudonymize("amit.kumar@example.com")
    b = pseudonymize("amit.kumar@example.com")
    c = pseudonymize("other@example.com")

    assert a is not None
    assert a == b
    assert a != c
    assert len(a) == 64  # SHA-256 hex digest


def test_pseudonymize_local_hmac_key_changes_digest(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "")

    monkeypatch.setattr(pii_module, "PII_HMAC_KEY", "key-one")
    d1 = pseudonymize("+91-9876543210")

    monkeypatch.setattr(pii_module, "PII_HMAC_KEY", "key-two")
    d2 = pseudonymize("+91-9876543210")

    assert d1 != d2


def test_pseudonymize_kms_path(monkeypatch):
    class FakeKMS:
        def __init__(self):
            self.calls = []

        def generate_mac(self, **kwargs):
            self.calls.append(kwargs)
            return {"Mac": b"\xde\xad\xbe\xef"}

    fake = FakeKMS()
    monkeypatch.setattr(pii_module, "_get_kms_client", lambda: fake)

    result = pseudonymize("amit@example.com", key_id="alias/pii")

    assert result == "deadbeef"
    assert fake.calls == [
        {
            "KeyId": "alias/pii",
            "MacAlgorithm": "HMAC_SHA_256",
            "Message": b"amit@example.com",
        }
    ]


def test_pseudonymize_kms_uses_env_key_id(monkeypatch):
    class FakeKMS:
        def generate_mac(self, **kwargs):
            return {"Mac": b"\x01\x02"}

    monkeypatch.setattr(pii_module, "_get_kms_client", lambda: FakeKMS())
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "alias/env-key")

    assert pseudonymize("anything") == "0102"


def test_pseudonymize_kms_rejects_oversized_message(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "alias/pii")

    def _boom():
        raise AssertionError("client should not be created for oversized input")

    monkeypatch.setattr(pii_module, "_get_kms_client", _boom)

    with pytest.raises(ValueError):
        pseudonymize("x" * 5000)


def test_pseudonymize_unconfigured_returns_none(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "")
    monkeypatch.setattr(pii_module, "PII_HMAC_KEY", "")
    monkeypatch.setattr(pii_module, "_pseudonym_unconfigured_warned", False)

    assert pseudonymize("anything") is None
    assert pseudonymize(None) is None
    assert pseudonymize_or_redact("anything") == "[REDACTED]"


def test_pseudonymize_or_redact_when_configured(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "")
    monkeypatch.setattr(pii_module, "PII_HMAC_KEY", "secret")

    out = pseudonymize_or_redact("value")
    assert out != "[REDACTED]"
    assert out == pseudonymize("value")


def test_pseudonymize_text_local_hmac(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "")
    monkeypatch.setattr(pii_module, "PII_HMAC_KEY", "secret")

    text = "email amit@example.com phone +91-9876543210 policy POL-HLT-2024-001"
    out = pseudonymize_text(text)

    assert "amit@example.com" not in out
    assert "+91-9876543210" not in out
    assert "POL-HLT-2024-001" not in out
    # deterministic for the same value/key
    assert out == pseudonymize_text(text)


def test_pseudonymize_text_unconfigured_redacts(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "")
    monkeypatch.setattr(pii_module, "PII_HMAC_KEY", "")
    monkeypatch.setattr(pii_module, "_pseudonym_unconfigured_warned", False)

    out = pseudonymize_text("call +91-9876543210 today")
    assert "+91-9876543210" not in out
    assert "[REDACTED]" in out


def test_pseudonymize_text_keeps_years(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "")
    monkeypatch.setattr(pii_module, "PII_HMAC_KEY", "secret")

    out = pseudonymize_text("Policy year 2024 is valid")
    assert "2024" in out  # a year must not be treated as a phone number


def test_pii_log_filter_redacts(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_KMS_KEY_ID", "")
    monkeypatch.setattr(pii_module, "PII_HMAC_KEY", "secret")
    monkeypatch.setattr(pii_module, "PII_LOG_MASKING_ENABLED", True)

    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1,
        "email amit@example.com phone %s", ("+91-9876543210",), None,
    )
    log_filter = PIILogFilter()

    assert log_filter.filter(record) is True
    message = record.getMessage()
    assert "amit@example.com" not in message
    assert "+91-9876543210" not in message


def test_pii_log_filter_disabled(monkeypatch):
    monkeypatch.setattr(pii_module, "PII_LOG_MASKING_ENABLED", False)

    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1,
        "phone +91-9876543210", (), None,
    )
    assert PIILogFilter().filter(record) is True
    assert "+91-9876543210" in record.getMessage()
