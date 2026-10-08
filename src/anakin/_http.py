"""
Internal HTTP layer.

Every SDK operation is written once as a *sans-IO generator* (see
`anakin._ops`): it yields `Call` (do an HTTP request) and `Wait` (sleep)
commands and receives the results. `SyncTransport` and `AsyncTransport`
drive those generators with httpx.Client / httpx.AsyncClient, so the sync
`Anakin` and async `AsyncAnakin` clients share all request-building,
polling and parsing logic.

Transports add:
- API key injection (optional: keyless "Zero Touch" calls send no key)
- Exponential backoff with full jitter on 429 / 5xx / network errors
- Retry-After honour on 429/503
- Error normalisation into the SDK error hierarchy

Not part of the public API. Anything imported from `anakin._http` is
internal and may change between minor versions.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx

from anakin._version import __version__
from anakin.errors import (
    AnakinError,
    AnakinPermissionError,
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    InsufficientCreditsError,
    InvalidRequestError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    UnprocessableEntityError,
    WireAuthExpiredError,
    WireAuthRequiredError,
)

logger = logging.getLogger("anakin")

DEFAULT_BASE_URL = "https://api.anakin.io/v1"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 4
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_POLL_MAX_INTERVAL = 10.0
DEFAULT_POLL_TIMEOUT = 300.0

DASHBOARD_URL = "https://anakin.io"

# Per https://anakin.io/docs/api-reference/error-responses: 429 and 5xx are transient.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
# Don't sleep longer than this on a single Retry-After; raise instead.
MAX_RETRY_AFTER = 60.0

T = TypeVar("T")


# ─── sans-IO commands ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Call:
    """Perform one HTTP request. The generator receives the parsed body."""

    method: str
    path: str
    json: Any = None
    params: dict[str, Any] | None = None
    raw: bool = False  # return response bytes instead of parsed JSON
    auth: bool = True  # False => allowed in keyless (Zero Touch) mode
    timeout: float | None = None  # per-call override (e.g. inline scrape holds ~90s)


@dataclass(frozen=True)
class Wait:
    """Sleep for `seconds`. The generator receives None."""

    seconds: float


Op = Generator[Call | Wait, Any, T]


# ─── config ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClientConfig:
    api_key: str | None
    base_url: str
    timeout: float
    max_retries: int
    poll_interval: float
    poll_max_interval: float
    poll_timeout: float

    @classmethod
    def build(
        cls,
        *,
        api_key: str | None,
        base_url: str,
        timeout: float,
        max_retries: int,
        poll_interval: float,
        poll_max_interval: float,
        poll_timeout: float,
    ) -> ClientConfig:
        resolved = api_key if api_key is not None else os.environ.get("ANAKIN_API_KEY")
        return cls(
            api_key=resolved or None,
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            max_retries=max_retries,
            poll_interval=poll_interval,
            poll_max_interval=poll_max_interval,
            poll_timeout=poll_timeout,
        )

    def headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": f"anakin-py/{__version__}",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers


def _require_key(cfg: ClientConfig, call: Call) -> None:
    if call.auth and not cfg.api_key:
        raise ConfigurationError(
            f"{call.method} {call.path} needs an Anakin API key. Pass api_key=... or set "
            f"ANAKIN_API_KEY. Get a free key (300 credits) at {DASHBOARD_URL}/signup. "
            "Without a key only scrape() and Wire discovery / zero_touch() work."
        )


def _backoff(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None and retry_after > 0:
        return retry_after
    # 0.25s, 0.5s, 1s, 2s ... with full jitter
    return random.uniform(0, 0.25 * (2 ** (attempt - 1)))


def _should_retry(response: httpx.Response, attempt: int, max_retries: int) -> float | None:
    """Return the delay before retrying, or None to stop and surface the response."""
    if response.status_code not in RETRYABLE_STATUS or attempt > max_retries:
        return None
    retry_after = _parse_retry_after(response)
    if retry_after is not None and retry_after > MAX_RETRY_AFTER:
        return None
    return _backoff(attempt, retry_after)


# ─── sync transport ───────────────────────────────────────────────────────────


class SyncTransport:
    def __init__(self, cfg: ClientConfig, client: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self._client = client or httpx.Client(
            base_url=cfg.base_url,
            timeout=httpx.Timeout(cfg.timeout),
            headers=cfg.headers(),
        )

    def close(self) -> None:
        self._client.close()

    def run(self, op: Op[T]) -> T:
        try:
            command = next(op)
            while True:
                if isinstance(command, Wait):
                    time.sleep(command.seconds)
                    result: Any = None
                else:
                    result = self.request(command)
                command = op.send(result)
        except StopIteration as stop:
            return stop.value  # type: ignore[no-any-return]
        finally:
            op.close()

    def request(self, call: Call) -> Any:
        _require_key(self.cfg, call)
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.request(
                    call.method,
                    call.path,
                    json=call.json,
                    params=_clean_params(call.params),
                    timeout=call.timeout if call.timeout is not None else httpx.USE_CLIENT_DEFAULT,
                )
            except httpx.RequestError as exc:
                if attempt > self.cfg.max_retries:
                    raise NetworkError(f"Network error after {attempt} attempts: {exc}") from exc
                time.sleep(_backoff(attempt, None))
                continue
            delay = _should_retry(response, attempt, self.cfg.max_retries)
            if delay is not None:
                logger.debug("anakin: retry attempt=%d sleep=%.2fs", attempt, delay)
                time.sleep(delay)
                continue
            return handle_response(response, call)


# ─── async transport ──────────────────────────────────────────────────────────


class AsyncTransport:
    def __init__(self, cfg: ClientConfig, client: httpx.AsyncClient | None = None) -> None:
        self.cfg = cfg
        self._client = client or httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=httpx.Timeout(cfg.timeout),
            headers=cfg.headers(),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def run(self, op: Op[T]) -> T:
        try:
            command = next(op)
            while True:
                if isinstance(command, Wait):
                    await asyncio.sleep(command.seconds)
                    result: Any = None
                else:
                    result = await self.request(command)
                command = op.send(result)
        except StopIteration as stop:
            return stop.value  # type: ignore[no-any-return]
        finally:
            op.close()

    async def request(self, call: Call) -> Any:
        _require_key(self.cfg, call)
        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._client.request(
                    call.method,
                    call.path,
                    json=call.json,
                    params=_clean_params(call.params),
                    timeout=call.timeout if call.timeout is not None else httpx.USE_CLIENT_DEFAULT,
                )
            except httpx.RequestError as exc:
                if attempt > self.cfg.max_retries:
                    raise NetworkError(f"Network error after {attempt} attempts: {exc}") from exc
                await asyncio.sleep(_backoff(attempt, None))
                continue
            delay = _should_retry(response, attempt, self.cfg.max_retries)
            if delay is not None:
                logger.debug("anakin: retry attempt=%d sleep=%.2fs", attempt, delay)
                await asyncio.sleep(delay)
                continue
            return handle_response(response, call)


# ─── response handling (pure) ─────────────────────────────────────────────────


def handle_response(response: httpx.Response, call: Call) -> Any:
    request_id = response.headers.get("X-Request-Id")

    if 200 <= response.status_code < 300:
        if call.raw:
            return response.content
        return _parse_json(response)

    body = _parse_json(response)
    message, code, err = _extract_error(body, fallback=response.reason_phrase or "Unknown error")
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
            if code == "AUTH_REQUIRED":
                connect_url = err.get("connect_url")
                if isinstance(connect_url, str) and connect_url:
                    raise WireAuthRequiredError(
                        message, connect_url=_absolute_url(connect_url), **kwargs
                    )
            if code == "AUTH_EXPIRED":
                raise WireAuthExpiredError(message, **kwargs)
            raise AuthenticationError(message, **kwargs)
        case 402:
            trial = body.get("trial") if isinstance(body, dict) else None
            trial = trial if isinstance(trial, dict) else {}
            raise InsufficientCreditsError(
                message,
                balance=_as_int(err.get("balance")),
                required=_as_int(err.get("required")),
                signup_url=trial.get("signup_url") or response.headers.get("X-Anakin-Signup"),
                trial_credits_remaining=_as_int(
                    response.headers.get("X-Trial-Credits-Remaining", trial.get("remaining_credits"))
                ),
                **kwargs,
            )
        case 403:
            raise AnakinPermissionError(message, **kwargs)
        case 404:
            raise NotFoundError(message, **kwargs)
        case 409:
            raise ConflictError(message, **kwargs)
        case 422:
            raise UnprocessableEntityError(message, **kwargs)
        case 429:
            raise RateLimitError(message, retry_after=_parse_retry_after(response), **kwargs)
        case status if 500 <= status < 600:
            raise ServerError(message, **kwargs)
        case _:
            raise AnakinError(message, **kwargs)


def _parse_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        # HTTP-date form isn't used by the Anakin API.
        return None


def _extract_error(body: Any, *, fallback: str) -> tuple[str, str | None, dict[str, Any]]:
    """
    Pull (message, code, error_object) from an error body.

    Anakin returns errors in three shapes:
      A. {"error": "code_string", "message": "..."}                (most endpoints)
      B. {"status": "error", "error": {"code": "...", "message": "...", ...}}  (Wire)
      C. {"statusCode": 400, "message": "..." | ["...", ...]}      (older validation)
    """
    if not isinstance(body, dict):
        return fallback, None, {}
    err = body.get("error")
    if isinstance(err, dict):
        return _as_message(err.get("message"), fallback), err.get("code"), err
    message = _as_message(body.get("message"), fallback)
    if isinstance(err, str):
        return message, err, {}
    return message, None, {}


def _as_message(value: Any, fallback: str) -> str:
    if isinstance(value, list):
        return "; ".join(str(v) for v in value) or fallback
    if value:
        return str(value)
    return fallback


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _absolute_url(url: str) -> str:
    return f"{DASHBOARD_URL}{url}" if url.startswith("/") else url


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        cleaned[key] = str(value).lower() if isinstance(value, bool) else value
    return cleaned or None
