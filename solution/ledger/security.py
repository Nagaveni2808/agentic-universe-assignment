"""Turns private values into keyed hashes, so we never store them in plain text."""
import hashlib
import hmac
import os

# In real life this comes from a secret manager. Here: an environment variable,
# with a dev fallback so the pipeline runs for reviewers without setup.
_SECRET = os.environ.get("LEDGER_SECRET", "dev-only-secret-change-me").encode()


def _key(label: str) -> bytes:
    return hmac.new(_SECRET, label.encode(), hashlib.sha256).digest()


_PHONE_KEY = _key("phone")
_PII_KEY = _key("pii")


def phone_token(canonical_phone: str) -> str:
    """Same phone in -> same token out. Used to match events to leads."""
    return hmac.new(_PHONE_KEY, canonical_phone.encode(), hashlib.sha256).hexdigest()


def pii_token(value: str) -> str:
    return hmac.new(_PII_KEY, value.encode(), hashlib.sha256).hexdigest()