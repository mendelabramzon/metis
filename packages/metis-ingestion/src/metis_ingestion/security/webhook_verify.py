"""Inbound webhook signature verification (HMAC), so a connector push is authenticated before use.

Stage 11 refuses an unverified webhook payload; this produces that verdict. It computes an
HMAC-SHA256 over ``v0:{timestamp}:{body}`` (Slack-style), compares in constant time, and rejects a
stale timestamp (replay defense). Treat every webhook body as untrusted until this passes — then the
verdict feeds ``build_webhook_job(verified=...)``.
"""

from __future__ import annotations

import hashlib
import hmac


def sign(secret: str, *, body: bytes, timestamp: str) -> str:
    """The expected ``v0=<hex>`` signature for a body + timestamp."""
    mac = hmac.new(
        secret.encode("utf-8"), b"v0:" + timestamp.encode("utf-8") + b":" + body, hashlib.sha256
    )
    return "v0=" + mac.hexdigest()


def verify_webhook(
    *,
    secret: str,
    body: bytes,
    timestamp: str,
    signature: str,
    now: int,
    max_age_seconds: int = 300,
) -> bool:
    """True iff ``signature`` is a fresh, valid HMAC over ``(timestamp, body)`` under ``secret``."""
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(now - sent_at) > max_age_seconds:
        return False  # stale timestamp -> replay defense
    return hmac.compare_digest(sign(secret, body=body, timestamp=timestamp), signature)
