"""
Anakin SDK error hierarchy.

All SDK errors inherit from `AnakinError`. Catch the base class to handle
any failure originating from the SDK; catch specific subclasses for
fine-grained control.

The HTTP status mapping follows https://anakin.io/docs/api-reference/error-responses.
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
        body: Any = None,
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
    """
    The SDK cannot make this call as configured.

    Most commonly: the method needs an API key and none was provided. Keyless
    (Zero Touch) mode only covers `scrape`, `wire.discover`, `wire.catalogs`,
    `wire.catalog` and `wire.zero_touch`.
    """


class AuthenticationError(AnakinError):
    """401: bad or missing API key."""


class WireAuthRequiredError(AuthenticationError):
    """
    A Wire action needs a connected third-party account and you have none.

    The API returns 401 with `code="AUTH_REQUIRED"` and a `connect_url`
    pointing at the connect flow (e.g. LinkedIn). Distinct from a plain
    `AuthenticationError` because the fix is "open this URL", not "fix your
    API key". `connect_url` is made absolute (https://anakin.io/...).
    """

    def __init__(self, message: str, *, connect_url: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.connect_url = connect_url


class WireAuthExpiredError(AuthenticationError):
    """
    401 `AUTH_EXPIRED`: the `credential_id` exists but its session is no longer valid.

    Re-run `client.wire.login(...)` / `client.wire.verify_credential(...)`, or
    reconnect the account in the dashboard. Your API key is fine.
    """


class WireLoginError(AnakinError):
    """
    `wire.login` / `wire.verify_credential` ran the site's sign-in but it failed.

    The API answers HTTP 200 with `status: "error"`; `code` is one of
    `BAD_PASSWORD`, `MFA_REQUIRED`, `CAPTCHA_REQUIRED`, `ACCOUNT_LOCKED`,
    `LOGIN_TIMEOUT`, `LOGIN_PAGE_CHANGED`, `LOGIN_NO_COOKIES`,
    `LOGIN_INFRASTRUCTURE_ERROR` or `LOGIN_FAILED`.
    """


class AnakinPermissionError(AnakinError):
    """403: authenticated, but the resource belongs to someone else."""


# Backwards-compatible alias (v0.1). Not exported via `__all__` so that
# `from anakin import *` does not shadow Python's builtin PermissionError.
PermissionError = AnakinPermissionError


class NotFoundError(AnakinError):
    """404: resource does not exist."""


class ConflictError(AnakinError):
    """
    409: the resource is locked or already exists.

    Examples: `session_in_use`, `duplicate_name`, Wire `ACTION_EXISTS`
    (inspect `.body` for `existing_actions`), monitor `session_expired`.
    """


class UnprocessableEntityError(AnakinError):
    """422: the request is valid but a prerequisite isn't met (e.g. `session_not_saved`)."""


class InvalidRequestError(AnakinError):
    """400: request validation failed (bad params, malformed URL, etc.)."""


class InsufficientCreditsError(AnakinError):
    """
    402: not enough credits, or the keyless free allowance is used up.

    `balance` / `required` are set when the API reports them. In keyless
    (Zero Touch) mode `signup_url` points at the signup page and
    `trial_credits_remaining` mirrors the `X-Trial-Credits-Remaining` header.
    """

    def __init__(
        self,
        message: str,
        *,
        balance: int | None = None,
        required: int | None = None,
        signup_url: str | None = None,
        trial_credits_remaining: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.balance = balance
        self.required = required
        self.signup_url = signup_url
        self.trial_credits_remaining = trial_credits_remaining


class RateLimitError(AnakinError):
    """429: too many requests. `retry_after` (seconds) is honoured by SDK retries."""

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(AnakinError):
    """5xx: server-side error. The SDK retries these; raised after retries are exhausted."""


class JobFailedError(AnakinError):
    """An async job came back with `status="failed"`. Distinct from HTTP errors."""

    def __init__(self, message: str, *, job_id: str | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.job_id = job_id


class JobTimeoutError(AnakinError):
    """
    `poll_timeout` exceeded while waiting for a job to complete.

    The job keeps running server-side. `job_id` lets you pick it up later with
    the matching `get_*` method (e.g. `client.get_crawl(err.job_id)`).
    """

    def __init__(self, message: str, *, job_id: str | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.job_id = job_id


class NetworkError(AnakinError):
    """DNS, connection, or read-timeout failure. Wraps the underlying httpx exception."""
