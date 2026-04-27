"""
Internal HTTP layer.

Wraps httpx.Client with:
- API key injection
- Exponential backoff with jitter on 429 / 5xx / network errors
- Retry-After honour on 429
- Error normalisation into the SDK error hierarchy
- Polling helper that exponentially backs off until terminal state

Not part of the public API. Anything imported from `anakin._http` is
internal and may change between minor versions.
"""

from __future__ import annotations

import logging
import os
import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from anakin._version import __version__
from anakin.errors import (
    AnakinError,
    AuthenticationError,
    ConfigurationError,
    InsufficientCreditsError,
    InvalidRequestError,
    JobTimeoutError,
    NetworkError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
    WireAuthRequiredError,
)

logger = logging.getLogger("anakin")

DEFAULT_BASE_URL = "https://api.anakin.io/v1"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 4
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_POLL_MAX_INTERVAL = 10.0
DEFAULT_POLL_TIMEOUT = 300.0

RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


class HttpClient:
    """Internal HTTP wrapper. One instance per Anakin client."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get("ANAKIN_API_KEY")
        if not resolved_key:
            raise ConfigurationError(
                "Anakin API key not provided. Pass api_key=... or set ANAKIN_API_KEY env var."
            )
        self._api_key = resolved_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "X-API-Key": self._api_key,
                "User-Agent": f"anakin-py/{__version__}",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ─── Public-ish (still internal to package) request helpers ────────────────

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", path, json=json)

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def patch(self, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("PATCH", path, json=json)

    def delete(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", path)

    # ─── Polling ──────────────────────────────────────────────────────────────

    def poll(
        self,
        path: str,
        *,
        is_terminal: Callable[[dict[str, Any]], bool],
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        poll_max_interval: float = DEFAULT_POLL_MAX_INTERVAL,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
    ) -> dict[str, Any]:
        """
        Poll `path` until `is_terminal(body)` returns True.

        Backoff: starts at `poll_interval`, multiplied by 1.5 each iteration,
        capped at `poll_max_interval`. Total wall time bounded by `poll_timeout`.
        """
        deadline = time.monotonic() + poll_timeout
        wait = poll_interval
        attempts = 0
        while True:
            attempts += 1
            body = self.get(path)
            if is_terminal(body):
                return body
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                raise JobTimeoutError(
                    f"Polling {path} did not reach terminal state within {poll_timeout}s "
                    f"({attempts} polls)."
                )
            sleep_for = min(wait, remaining)
            time.sleep(sleep_for)
            wait = min(wait * 1.5, poll_max_interval)

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                )
            except httpx.RequestError as exc:
                if attempt > self._max_retries:
                    raise NetworkError(f"Network error after {attempt} attempts: {exc}") from exc
                self._sleep_with_backoff(attempt, retry_after=None)
                continue

            if response.status_code in RETRYABLE_STATUS and attempt <= self._max_retries:
                retry_after = _parse_retry_after(response)
                self._sleep_with_backoff(attempt, retry_after=retry_after)
                continue

            return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        body: dict[str, Any]
        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}
        request_id = response.headers.get("X-Request-Id")

        if 200 <= response.status_code < 300:
            return body

        # Map HTTP error → SDK error class
        message, code = _extract_error(body, fallback=response.reason_phrase or "Unknown error")
        kwargs: dict[str, Any] = {
            "status_code": response.status_code,
            "request_id": request_id,
            "code": code,
            "body": body,
        }

        match response.status_code:
            case 400:
                raise InvalidRequestError(message, **kwargs)
            case 401:
                # Wire AUTH_REQUIRED is a special-case 401 with a connect_url
                if code == "AUTH_REQUIRED":
                    err_obj = body.get("error", {}) if isinstance(body, dict) else {}
                    connect_url = (
                        err_obj.get("connect_url") if isinstance(err_obj, dict) else None
                    )
                    if connect_url:
                        raise WireAuthRequiredError(
                            message, connect_url=connect_url, **kwargs
                        )
                raise AuthenticationError(message, **kwargs)
            case 402:
                err_obj = body.get("error", {}) if isinstance(body, dict) else {}
                balance = err_obj.get("balance") if isinstance(err_obj, dict) else None
                required = err_obj.get("required") if isinstance(err_obj, dict) else None
                raise InsufficientCreditsError(
                    message, balance=balance, required=required, **kwargs
                )
            case 403:
                raise PermissionError(message, **kwargs)
            case 404:
                raise NotFoundError(message, **kwargs)
            case 429:
                raise RateLimitError(
                    message,
                    retry_after=_parse_retry_after(response),
                    **kwargs,
                )
            case status if 500 <= status < 600:
                raise ServerError(message, **kwargs)
            case _:
                raise AnakinError(message, **kwargs)

    def _sleep_with_backoff(self, attempt: int, *, retry_after: float | None) -> None:
        if retry_after is not None and retry_after > 0:
            delay = retry_after
        else:
            # 0.25s, 0.5s, 1s, 2s with full jitter
            base = 0.25 * (2 ** (attempt - 1))
            delay = random.uniform(0, base)
        logger.debug("anakin: retry attempt=%d sleep=%.2fs", attempt, delay)
        time.sleep(delay)


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        # HTTP-date form is rare for our API; ignore for v0.1
        return None


def _extract_error(body: dict[str, Any], *, fallback: str) -> tuple[str, str | None]:
    """
    Pull (message, code) from an error body.

    Anakin returns errors in two shapes today:
      A. {"error": "code_string", "message": "..."}
      B. {"status": "error", "error": {"code": "...", "message": "..."}}
    Tolerate both.
    """
    if not isinstance(body, dict):
        return fallback, None
    err = body.get("error")
    if isinstance(err, dict):
        return err.get("message", fallback), err.get("code")
    if isinstance(err, str):
        return body.get("message", fallback), err
    return body.get("message", fallback), None
