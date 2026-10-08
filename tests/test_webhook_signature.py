"""Tests for anakin.verify_webhook_signature."""

from __future__ import annotations

import hashlib
import hmac
import time

from anakin import verify_webhook_signature

SECRET = "whsec_test"
BODY = b'{"id":"evt_1","type":"job.completed","data":{}}'


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature() -> None:
    assert verify_webhook_signature(BODY, _sign(BODY), SECRET)
    assert verify_webhook_signature(BODY.decode(), _sign(BODY), SECRET)


def test_tampered_body_or_wrong_secret_fails() -> None:
    assert not verify_webhook_signature(BODY + b" ", _sign(BODY), SECRET)
    assert not verify_webhook_signature(BODY, _sign(BODY, "whsec_other"), SECRET)
    assert not verify_webhook_signature(BODY, None, SECRET)
    assert not verify_webhook_signature(BODY, "", SECRET)


def test_timestamp_tolerance() -> None:
    now = int(time.time())
    sig = _sign(BODY)
    assert verify_webhook_signature(BODY, sig, SECRET, timestamp=str(now), tolerance=300)
    assert not verify_webhook_signature(BODY, sig, SECRET, timestamp=now - 3600, tolerance=300)
    assert not verify_webhook_signature(BODY, sig, SECRET, timestamp=None, tolerance=300)
    assert not verify_webhook_signature(BODY, sig, SECRET, timestamp="garbage", tolerance=300)
