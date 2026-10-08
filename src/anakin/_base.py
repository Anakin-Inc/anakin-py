"""
Hand-written base classes shared by the sync and async clients.

`client.py` holds every network method once (sync); `async_client.py` is
generated from it by `scripts/generate_async.py`. Anything that differs
between the two flavours (lifecycle, how an op is driven) or that never
touches the network lives here, so the generator stays a few regexes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import urlencode

from anakin._http import AsyncTransport, ClientConfig, Op, SyncTransport

if TYPE_CHECKING:
    from types import TracebackType

    from anakin.models import Country

T = TypeVar("T")


class _SyncAPI:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport
        self._cfg: ClientConfig = transport.cfg

    def _run(self, op: Op[T]) -> T:
        return self._transport.run(op)


class _AsyncAPI:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport
        self._cfg: ClientConfig = transport.cfg

    async def _run(self, op: Op[T]) -> T:
        return await self._transport.run(op)


class _StaticMixin:
    """Methods that never hit the network; identical on both clients."""

    _cfg: ClientConfig

    @property
    def api_key_configured(self) -> bool:
        """False in keyless (Zero Touch) mode."""
        return self._cfg.api_key is not None

    def countries(self) -> list[Country]:
        """
        Supported proxy countries (bundled with the SDK, no network call).

        Use `anakin.SUPPORTED_COUNTRIES` / `SUPPORTED_COUNTRY_CODES` for
        module-level access.
        """
        from anakin.countries import SUPPORTED_COUNTRIES

        return list(SUPPORTED_COUNTRIES)


class _BrowserStaticMixin:
    _cfg: ClientConfig

    def connect_url(
        self,
        *,
        country: str | None = None,
        session_id: str | None = None,
        session_name: str | None = None,
        save_session: str | None = None,
        save_url: str | None = None,
        record: bool = False,
    ) -> str:
        """
        WebSocket URL for the Browser API (Playwright `connect_over_cdp`, Puppeteer `connect`).

        Pass `headers=client.browser.headers()` when connecting so the API key
        travels in a header rather than the URL (and your logs).

            browser = await p.chromium.connect_over_cdp(
                client.browser.connect_url(country="gb", session_name="my-login"),
                headers=client.browser.headers(),
            )
        """
        base = self._cfg.base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        query: dict[str, Any] = {
            "country": country.upper() if country else None,
            "session_id": session_id,
            "session_name": session_name,
            "save_session": save_session,
            "save_url": save_url,
            "record": "true" if record else None,
        }
        params = {k: v for k, v in query.items() if v is not None}
        url = f"{base}/browser-connect"
        return f"{url}?{urlencode(params)}" if params else url

    def headers(self) -> dict[str, str]:
        """Auth headers for the Browser API WebSocket connection."""
        return {"X-API-Key": self._cfg.api_key} if self._cfg.api_key else {}


class _SyncClientBase(_SyncAPI):
    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._transport.close()

    def __enter__(self: T) -> T:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class _AsyncClientBase(_AsyncAPI):
    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._transport.close()

    async def __aenter__(self: T) -> T:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()
