"""
Verify signed webhook deliveries from Anakin.

Every delivery (job/batch/wire/ai-search events and monitor alerts) carries
`X-Anakin-Signature: sha256=<hex HMAC-SHA256(secret, raw_body)>`.

    from anakin import verify_webhook_signature

    @app.post("/anakin-webhook")
    def webhook():
        ok = verify_webhook_signature(
            request.get_data(),                         # raw bytes, not parsed JSON
            request.headers.get("X-Anakin-Signature", ""),
            os.environ["ANAKIN_WEBHOOK_SECRET"],
            timestamp=request.headers.get("X-Anakin-Timestamp"),
            tolerance=300,
        )
        if not ok:
            abort(401)

Which secret: a registered endpoint's own `whsec_...` secret, the account
default (`client.webhooks.signing_secret()`) for per-request `webhook_url`
deliveries, or the monitor's `alert_webhook_secret` for monitor alerts.
"""

from __future__ import annotations

import hashlib
import hmac
import time

__all__ = ["verify_webhook_signature"]


def verify_webhook_signature(
    payload: bytes | str,
    signature: str | None,
    secret: str,
    *,
    timestamp: str | int | None = None,
    tolerance: float | None = None,
) -> bool:
    """
    Return True if `signature` is a valid Anakin signature for `payload`.

    Args:
        payload: The exact raw request body. Re-serialised JSON will not match.
        signature: The `X-Anakin-Signature` header value.
        secret: The signing secret for this delivery.
        timestamp: The `X-Anakin-Timestamp` header (Unix seconds). Only used
            with `tolerance`.
        tolerance: If set, reject deliveries whose timestamp is more than this
            many seconds away from now (replay protection).
    """
    if not signature or not secret:
        return False
    if tolerance is not None:
        try:
            sent = float(timestamp) if timestamp is not None else None
        except ValueError:
            return False
        if sent is None or abs(time.time() - sent) > tolerance:
            return False
    raw = payload.encode() if isinstance(payload, str) else payload
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())
