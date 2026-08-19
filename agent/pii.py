"""
PII Vault and Reversible Masking/Unmasking Pipeline.

Provides deterministic tokenization for sensitive personal and policy information
so that only typed tokens ([PHONE_1], [EMAIL_1], [NAME_1], etc.) travel through
the LLM, LangGraph state checkpointer, semantic cache, and observability tracing,
while real values are restored just-in-time for database lookups and user responses.
"""
import os
import re
import threading
import logging
import hashlib
import hmac as hmac_lib
from typing import Dict, Optional, Generator

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env so PII_MASKING_ENABLED is honored regardless of import order/path
load_dotenv()

PII_MASKING_ENABLED = os.getenv("PII_MASKING_ENABLED", "true").lower() == "true"

# Shared regex rules used by both reversible masking (mask_text) and
# irreversible pseudonymization (pseudonymize_text). Order is insertion order.
_PII_PATTERNS = {
    "POLICY_NO": re.compile(r"\bPOL-[A-Z]{3,4}-\d{4}-\d{3,4}\b"),
    "CLAIM_NO": re.compile(r"\bCLM-\d{4}-\d{4,6}\b"),
    "CUSTOMER_ID": re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    ),
    "EMAIL": re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"),
    "AADHAAR": re.compile(r"\b\d{4}[-\s]\d{4}[-\s]\d{4}\b"),
    "PAN": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "PHONE": re.compile(r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{9}\b"),
}


def _is_valid_phone(raw: str) -> bool:
    """Guard against masking years/short numbers as phones."""
    digits = re.sub(r"\D", "", raw)
    return len(digits) in (10, 11, 12)


class PIIVault:
    """Thread-safe reversible vault storing bidirectional mappings between PII and tokens."""

    def __init__(self):
        self._lock = threading.RLock()
        self._value_to_token: Dict[str, str] = {}
        self._token_to_value: Dict[str, str] = {}
        self._type_counters: Dict[str, int] = {}

    def clear(self) -> None:
        """Reset the vault (useful between test suites)."""
        with self._lock:
            self._value_to_token.clear()
            self._token_to_value.clear()
            self._type_counters.clear()

    def register(self, value: Optional[str], pii_type: str) -> str:
        """Register a known real value and return its canonical token."""
        if not value or not str(value).strip():
            return ""

        val_str = str(value).strip()
        pii_type = pii_type.upper().strip()

        with self._lock:
            if val_str in self._value_to_token:
                return self._value_to_token[val_str]

            count = self._type_counters.get(pii_type, 0) + 1
            self._type_counters[pii_type] = count
            token = f"[{pii_type}_{count}]"

            self._value_to_token[val_str] = token
            self._token_to_value[token] = val_str
            return token

    def resolve(self, text_or_token: Optional[str]) -> str:
        """Resolve a token (e.g. '[PHONE_1]') back to its real value.

        If the input is not a token or contains text, replaces any tokens found.
        """
        if not text_or_token:
            return "" if text_or_token is None else str(text_or_token)

        val_str = str(text_or_token).strip()

        with self._lock:
            # Exact match lookup
            if val_str in self._token_to_value:
                return self._token_to_value[val_str]

            # In-text token replacement
            result = val_str
            for token, real_val in sorted(self._token_to_value.items(), key=lambda x: len(x[0]), reverse=True):
                if token in result:
                    result = result.replace(token, real_val)
            return result

    def mask_text(self, text: Optional[str]) -> str:
        """Detect PII via registered values and regex patterns, replacing with tokens."""
        if not text or not PII_MASKING_ENABLED:
            return "" if text is None else str(text)

        masked = str(text)

        with self._lock:
            # 1. Replace already registered explicit values (longest first to avoid substrings).
            #    Word-boundary-aware so a short value like "Amit" doesn't corrupt "Amitabh",
            #    and "Kumar" doesn't get replaced inside "Kumaran".
            registered_items = sorted(
                self._value_to_token.items(),
                key=lambda x: len(x[0]),
                reverse=True
            )
            for real_val, token in registered_items:
                if len(real_val) < 3:
                    continue
                pattern = (
                    r"(?<![A-Za-z0-9_])"
                    + re.escape(real_val)
                    + r"(?![A-Za-z0-9_])"
                )
                masked = re.sub(pattern, lambda _m: token, masked)

        # 2. Regex-based detection for unregistered PII
        for pii_type, pattern in _PII_PATTERNS.items():
            def _repl(m, _type=pii_type):
                raw = m.group(0)
                if _type == "PHONE" and not _is_valid_phone(raw):
                    return raw
                return self.register(raw, _type)
            masked = pattern.sub(_repl, masked)

        return masked

    def unmask_text(self, text: Optional[str]) -> str:
        """Reverse all tokens in text back to their real values."""
        if not text or not PII_MASKING_ENABLED:
            return "" if text is None else str(text)

        result = str(text)
        with self._lock:
            tokens = sorted(
                self._token_to_value.items(),
                key=lambda x: len(x[0]),
                reverse=True
            )
            for token, real_val in tokens:
                if token in result:
                    result = result.replace(token, real_val)
        return result


# Global singleton vault
pii_vault = PIIVault()


def mask_text(text: Optional[str]) -> str:
    """Detect PII and replace with canonical tokens."""
    return pii_vault.mask_text(text)


def unmask_text(text: Optional[str]) -> str:
    """Restore tokens back to original values."""
    return pii_vault.unmask_text(text)


def register_pii(value: Optional[str], pii_type: str) -> str:
    """Register a known real value into the vault."""
    return pii_vault.register(value, pii_type)


def resolve_pii(text_or_token: Optional[str]) -> str:
    """Resolve token(s) back to real values for tool execution."""
    return pii_vault.resolve(text_or_token)


# ---------------------------------------------------------------------------
# One-way pseudonymization (HMAC via AWS KMS, or local HMAC fallback).
#
# Unlike the reversible PIIVault, these digests are irreversible and
# deterministic — ideal for logs, Arize trace attributes, and analytics where
# you need to correlate events without ever storing or recovering the raw PII.
#
# Resolution order for pseudonymize():
#   1. AWS KMS GenerateMac  — if key id is provided (arg or PII_KMS_KEY_ID)
#   2. Local HMAC-SHA256     — if PII_HMAC_KEY is set
#   3. None                 — unconfigured (caller should redact instead)
#
# Requires `boto3` only when using KMS (imported lazily).
# ---------------------------------------------------------------------------

PII_KMS_KEY_ID = os.getenv("PII_KMS_KEY_ID", "").strip()
PII_HMAC_KEY = os.getenv("PII_HMAC_KEY", "").strip()
PII_KMS_MAC_ALGORITHM = os.getenv("PII_KMS_MAC_ALGORITHM", "HMAC_SHA_256")
PII_LOG_MASKING_ENABLED = os.getenv("PII_LOG_MASKING_ENABLED", "true").lower() == "true"

# KMS GenerateMac accepts at most 4096 bytes per call.
_KMS_MAX_MESSAGE_BYTES = 4096

_kms_client = None
_pseudonym_unconfigured_warned = False


def _get_kms_client():
    """Return a cached boto3 KMS client, importing boto3 lazily."""
    global _kms_client
    if _kms_client is None:
        try:
            import boto3
        except ImportError as e:
            raise RuntimeError(
                "PII_KMS_KEY_ID is set but boto3 is not installed. "
                "Install boto3 (pip install boto3) or unset PII_KMS_KEY_ID "
                "to fall back to the local HMAC key (PII_HMAC_KEY)."
            ) from e
        _kms_client = boto3.client("kms")
    return _kms_client


def pseudonymize(value: Optional[str], key_id: Optional[str] = None) -> Optional[str]:
    """Return a deterministic, one-way pseudonym for a PII value.

    Args:
        value: The PII value to pseudonymize (email, phone, name, ...).
        key_id: Optional KMS key id/alias/ARN. Defaults to PII_KMS_KEY_ID.

    Returns:
        Hex digest string, or None if pseudonymization is not configured.

    Raises:
        RuntimeError: if KMS is configured but unavailable (missing boto3,
            missing key, or KMS API error). Misconfiguration should be loud
            rather than silently falling back to raw PII.
    """
    if value is None:
        return None

    data = str(value).encode("utf-8")

    kms_key = (key_id or PII_KMS_KEY_ID).strip()
    if kms_key:
        if len(data) > _KMS_MAX_MESSAGE_BYTES:
            raise ValueError(
                f"KMS GenerateMac accepts at most {_KMS_MAX_MESSAGE_BYTES} bytes; "
                f"got {len(data)}."
            )
        client = _get_kms_client()
        response = client.generate_mac(
            KeyId=kms_key,
            MacAlgorithm=PII_KMS_MAC_ALGORITHM,
            Message=data,
        )
        return response["Mac"].hex()

    if PII_HMAC_KEY:
        return hmac_lib.new(
            PII_HMAC_KEY.encode("utf-8"),
            data,
            hashlib.sha256,
        ).hexdigest()

    global _pseudonym_unconfigured_warned
    if not _pseudonym_unconfigured_warned:
        logger.warning(
            "PII pseudonymization is not configured — set PII_KMS_KEY_ID (KMS) "
            "or PII_HMAC_KEY (local HMAC). pseudonymize() will return None."
        )
        _pseudonym_unconfigured_warned = True
    return None


def pseudonymize_or_redact(value: Optional[str], redacted: str = "[REDACTED]") -> str:
    """Pseudonymize a value, falling back to a redaction marker.

    Convenience wrapper for logging filters / trace redactors where a plain
    string is always needed: `pseudonymize(value) or "[REDACTED]"`.
    """
    return pseudonymize(value) or redacted


def pseudonymize_text(text: Optional[str]) -> Optional[str]:
    """Replace detected PII spans in free text with one-way pseudonyms.

    Uses the same regex rules as mask_text, but each match is replaced with an
    irreversible HMAC digest (or "[REDACTED]" when pseudonymization is not
    configured) instead of a reversible vault token. Ideal for logs, where
    recovering the original value is never required.
    """
    if text is None:
        return None

    result = str(text)
    for pii_type, pattern in _PII_PATTERNS.items():
        def _repl(m, _type=pii_type):
            raw = m.group(0)
            if _type == "PHONE" and not _is_valid_phone(raw):
                return raw
            return pseudonymize_or_redact(raw)
        result = pattern.sub(_repl, result)
    return result


class PIILogFilter(logging.Filter):
    """Defense-in-depth logging filter that strips PII from every record.

    Pseudonymizes any PII that slips through the source-level masking, so log
    files never contain raw emails, phones, Aadhaar/PAN, policy/claim numbers,
    or UUIDs. Never raises — if redaction fails, the record passes unchanged.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not PII_LOG_MASKING_ENABLED:
            return True
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        try:
            record.msg = pseudonymize_text(message)
            record.args = ()
        except Exception:
            pass
        return True


class StreamingUnmasker:
    """Handles token unmasking for streaming chunk generators without breaking partial tokens."""

    def __init__(self, vault: PIIVault = pii_vault):
        self.vault = vault
        self._buffer = ""

    def process_chunk(self, chunk: str) -> Generator[str, None, None]:
        """Process incoming chunk, unmask complete tokens, and hold partial token boundaries."""
        if not PII_MASKING_ENABLED:
            if chunk:
                yield chunk
            return

        self._buffer += chunk

        # If buffer contains potential starting '[' without closing ']'
        if "[" in self._buffer:
            parts = self._buffer.split("[")
            # The text before the first '[' is safe to unmask and yield immediately
            if parts[0]:
                yield self.vault.unmask_text(parts[0])

            # Rebuild the rest
            remaining = "[" + "[".join(parts[1:])
            # If there's a complete token bracket
            if "]" in remaining:
                last_close = remaining.rfind("]")
                to_unmask = remaining[:last_close + 1]
                self._buffer = remaining[last_close + 1:]
                yield self.vault.unmask_text(to_unmask)
            else:
                # Buffer might be too long to be a token (tokens are ~ < 25 chars)
                if len(remaining) > 30:
                    yield remaining
                    self._buffer = ""
                else:
                    self._buffer = remaining
        else:
            yield self.vault.unmask_text(self._buffer)
            self._buffer = ""

    def flush(self) -> Generator[str, None, None]:
        """Flush remaining buffered text on stream completion."""
        if self._buffer:
            yield self.vault.unmask_text(self._buffer)
            self._buffer = ""
