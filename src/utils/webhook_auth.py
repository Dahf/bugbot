"""HMAC-SHA256 webhook signature validation."""

import hashlib
import hmac


def validate_webhook_signature(
    body: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """Validate an HMAC-SHA256 webhook signature.

    Args:
        body: Raw request body bytes.
        signature_header: Value from the webhook signature header.
        secret: Shared secret string used to compute the expected signature.

    Returns:
        ``True`` if the signature is valid, ``False`` otherwise.

    Uses ``hmac.compare_digest`` for timing-safe comparison to prevent
    timing attacks.
    """
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature_header, expected)
