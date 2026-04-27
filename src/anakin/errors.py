"""
Anakin SDK error hierarchy.

All SDK errors inherit from `AnakinError`. Catch the base class to handle
any failure originating from the SDK; catch specific subclasses for
fine-grained control.

The hierarchy mirrors the API contract documented at
docs/SDK_API_CONTRACT.md, section 6.
"""

from __future__ import annotations

from typing import Any


class AnakinError(Exception):
    """Base class for every error raised by the Anakin SDK."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        code: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.code = code
        self.body = body

    def __str__(self) -> str:
        bits = [self.message]
        if self.status_code is not None:
            bits.append(f"status={self.status_code}")
        if self.code:
            bits.append(f"code={self.code}")
        if self.request_id:
            bits.append(f"request_id={self.request_id}")
        return " | ".join(bits)


class ConfigurationError(AnakinError):
    """Raised when the SDK cannot start (missing API key, bad base_url)."""


class AuthenticationError(AnakinError):
    """401 — bad or missing API key."""


class WireAuthRequiredError(AuthenticationError):
    """
    Wire action needs the user to first connect a third-party account.

    The API returns 401 with `code="AUTH_REQUIRED"` and a `connect_url`
    pointing the user at the connect flow (e.g. LinkedIn). Distinct from a
    plain `AuthenticationError` because the resolution is "open this URL",
    not "fix your API key".
    """

    def __init__(
        self,
        message: str,
        *,
        connect_url: str,
        status_code: int | None = None,
        request_id: str | None = None,
        code: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            request_id=request_id,
            code=code,
            body=body,
        )
        self.connect_url = connect_url


class PermissionError(AnakinError):
    """403 — authenticated but not authorised for this resource."""


class NotFoundError(AnakinError):
    """404 — resource does not exist."""


class InvalidRequestError(AnakinError):
    """400 — request validation failed (bad params, malformed URL, etc.)."""


class InsufficientCreditsError(AnakinError):
    """402 — caller does not have enough credits to run this job."""

    def __init__(
        self,
        message: str,
        *,
        balance: int | None = None,
        required: int | None = None,
        status_code: int | None = None,
        request_id: str | None = None,
        code: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            request_id=request_id,
            code=code,
            body=body,
        )
        self.balance = balance
        self.required = required


class RateLimitError(AnakinError):
    """429 — too many requests. `retry_after` (seconds) honoured by SDK retry."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        status_code: int | None = None,
        request_id: str | None = None,
        code: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            request_id=request_id,
            code=code,
            body=body,
        )
        self.retry_after = retry_after


class ServerError(AnakinError):
    """5xx — server-side error. SDK retries by default; raised after retries exhausted."""


class JobFailedError(AnakinError):
    """An async job came back with `status="failed"`. Distinct from HTTP errors."""


class JobTimeoutError(AnakinError):
    """`poll_timeout` exceeded while waiting for a job to complete."""


class NetworkError(AnakinError):
    """DNS, connection, or read-timeout failure. Wraps the underlying httpx exception."""
