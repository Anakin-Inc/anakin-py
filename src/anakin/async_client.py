"""
Anakin async client.

    from anakin import AsyncAnakin

    async with AsyncAnakin(api_key="ak-...") as client:
        doc = await client.scrape("https://example.com")
        print(doc.markdown)

GENERATED FILE: do not edit. Source: `src/anakin/client.py`;
regenerate with `python scripts/generate_async.py`.
"""

from __future__ import annotations

import builtins
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from typing_extensions import Unpack

from anakin import _ops as ops
from anakin._base import _BrowserStaticMixin, _StaticMixin, _AsyncAPI, _AsyncClientBase
from anakin._http import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLL_MAX_INTERVAL,
    DEFAULT_POLL_TIMEOUT,
    DEFAULT_TIMEOUT,
    ClientConfig,
    AsyncTransport,
)
from anakin.models import (
    AgenticSearchResult,
    AIVisibilitySearch,
    AIVisibilitySearchSummary,
    AIVisibilitySource,
    AIVisibilitySourceResult,
    AlertTestResult,
    BatchScrapeResult,
    BrowserSession,
    BrowserSessionHandle,
    CrawlResult,
    Delivery,
    Document,
    MapResult,
    Monitor,
    MonitorChange,
    MonitorRun,
    MonitorSnapshot,
    Recording,
    SearchResult,
    SnapshotContent,
    WebhookEndpoint,
    WebhookTestResult,
    WireActionMatch,
    WireBuildRequest,
    WireCatalog,
    WireCatalogDetail,
    WireCredential,
    WireIdentity,
    WireLoginResult,
    WireResult,
)
from anakin.types import AuthMode, BrowserAction, MonitorOptions, ScrapeFormat


class AsyncAnakin(_StaticMixin, _AsyncClientBase):
    """
    Anakin SDK client (asyncio).

    Args:
        api_key: API key. Falls back to the ANAKIN_API_KEY env var. If neither
            is set the client runs in keyless "Zero Touch" mode: `scrape()`,
            `wire.discover()`, `wire.catalogs()`, `wire.catalog()` and
            `wire.zero_touch()` work on a free per-IP allowance; every other
            method raises `ConfigurationError`.
        base_url: API base URL. Override only for internal/test environments.
        timeout: HTTP request timeout in seconds.
        max_retries: Retries on 429/5xx/network errors before raising.
        poll_interval: Initial polling delay in seconds.
        poll_max_interval: Maximum polling delay (cap on exponential backoff).
        poll_timeout: Default total wait for polled jobs before
            `JobTimeoutError`. Agentic search always waits at least 600s.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        poll_max_interval: float = DEFAULT_POLL_MAX_INTERVAL,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
    ) -> None:
        cfg = ClientConfig.build(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            poll_interval=poll_interval,
            poll_max_interval=poll_max_interval,
            poll_timeout=poll_timeout,
        )
        transport = AsyncTransport(cfg)
        super().__init__(transport)
        self.wire = AsyncWireResource(transport)
        self.monitors = AsyncMonitorsResource(transport)
        self.ai_visibility = AsyncAIVisibilityResource(transport)
        self.webhooks = AsyncWebhooksResource(transport)
        self.sessions = AsyncSessionsResource(transport)
        self.browser = AsyncBrowserResource(transport)

    # ─── scrape ───────────────────────────────────────────────────────────────

    async def scrape(
        self,
        url: str,
        *,
        formats: Sequence[ScrapeFormat] = ("markdown",),
        country: str = "us",
        use_browser: bool = False,
        generate_json: bool = False,
        output_schema: dict[str, Any] | None = None,
        actions: Sequence[BrowserAction] | None = None,
        force_fresh: bool = False,
        session_id: str | None = None,
        session_name: str | None = None,
        webhook_url: str | None = None,
        inline: bool | None = None,
        wait: bool = True,
        poll_timeout: float | None = None,
    ) -> Document:
        """
        Scrape one URL.

        By default submits `POST /v1/url-scraper` and polls until done. With
        `inline=True` (the default when no API key is set) it uses
        `POST /v1/url-scraper/scrape`, which answers in one request.

        Args:
            formats: Outputs to produce (markdown, html, cleanedHtml, links,
                images, summary, screenshot, screenshotFullPage, json).
            output_schema: JSON Schema of fields to extract with AI (implies
                generate_json).
            actions: Browser steps to run before capture (click, scroll, ...).
            webhook_url: Also POST a signed `job.completed` event here.
            wait: False returns immediately with `status="pending"`; fetch
                later with `get_scrape(doc.id)`.
        """
        return await self._run(
            ops.scrape(
                self._cfg,
                url,
                formats=formats,
                country=country,
                use_browser=use_browser,
                generate_json=generate_json,
                output_schema=output_schema,
                actions=[dict(a) for a in actions] if actions is not None else None,
                force_fresh=force_fresh,
                session_id=session_id,
                session_name=session_name,
                webhook_url=webhook_url,
                inline=inline,
                wait=wait,
                poll_timeout=poll_timeout,
            )
        )

    async def scrape_batch(
        self,
        urls: Sequence[str],
        *,
        country: str = "us",
        use_browser: bool = False,
        generate_json: bool = False,
        session_id: str | None = None,
        webhook_url: str | None = None,
        wait: bool = True,
        poll_timeout: float | None = None,
    ) -> BatchScrapeResult:
        """
        Scrape 1-10 URLs in parallel in one job (`POST /v1/url-scraper/batch`).

        The batch is `completed` if any URL finished; check each
        `result.results[i].status`.
        """
        return await self._run(
            ops.scrape_batch(
                self._cfg,
                urls,
                country=country,
                use_browser=use_browser,
                generate_json=generate_json,
                session_id=session_id,
                webhook_url=webhook_url,
                wait=wait,
                poll_timeout=poll_timeout,
            )
        )

    async def get_scrape(self, job_id: str) -> Document:
        """Fetch a scrape job by ID (e.g. after `scrape(..., wait=False)` or a webhook)."""
        return await self._run(ops.get_scrape(job_id))

    async def get_scrape_batch(self, job_id: str) -> BatchScrapeResult:
        """Fetch a batch scrape job by ID."""
        return await self._run(ops.get_scrape_batch(job_id))

    async def download_screenshot(self, job_id: str, *, full_page: bool = False) -> bytes:
        """
        Download the PNG captured by a scrape that requested the `screenshot`
        (or, with `full_page=True`, `screenshotFullPage`) format.
        """
        return await self._run(ops.download_screenshot(job_id, full_page=full_page))

    # ─── map ──────────────────────────────────────────────────────────────────

    async def map(
        self,
        url: str,
        *,
        limit: int = 100,
        depth: int = 2,
        limit_per_level: int = 100,
        include_subdomains: bool = False,
        include_external_links: bool = False,
        search: str | None = None,
        use_browser: bool = False,
        session_id: str | None = None,
        webhook_url: str | None = None,
        wait: bool = True,
        poll_timeout: float | None = None,
    ) -> MapResult:
        """Discover URLs on a website (`POST /v1/map`). `limit` max 5000, `depth` max 5."""
        return await self._run(
            ops.map_site(
                self._cfg,
                url,
                limit=limit,
                depth=depth,
                limit_per_level=limit_per_level,
                include_subdomains=include_subdomains,
                include_external_links=include_external_links,
                search=search,
                use_browser=use_browser,
                session_id=session_id,
                webhook_url=webhook_url,
                wait=wait,
                poll_timeout=poll_timeout,
            )
        )

    async def get_map(self, job_id: str) -> MapResult:
        """Fetch a map job by ID."""
        return await self._run(ops.get_map(job_id))

    # ─── crawl ────────────────────────────────────────────────────────────────

    async def crawl(
        self,
        url: str,
        *,
        max_pages: int = 10,
        depth: int = 1,
        include_patterns: Sequence[str] = (),
        exclude_patterns: Sequence[str] = (),
        country: str = "us",
        use_browser: bool = False,
        session_id: str | None = None,
        session_name: str | None = None,
        webhook_url: str | None = None,
        wait: bool = True,
        poll_timeout: float | None = None,
    ) -> CrawlResult:
        """Crawl a website and return each page's markdown (`POST /v1/crawl`)."""
        return await self._run(
            ops.crawl(
                self._cfg,
                url,
                max_pages=max_pages,
                depth=depth,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                country=country,
                use_browser=use_browser,
                session_id=session_id,
                session_name=session_name,
                webhook_url=webhook_url,
                wait=wait,
                poll_timeout=poll_timeout,
            )
        )

    async def get_crawl(self, job_id: str) -> CrawlResult:
        """Fetch a crawl job by ID."""
        return await self._run(ops.get_crawl(job_id))

    # ─── search ───────────────────────────────────────────────────────────────

    async def search(self, prompt: str, *, limit: int = 5) -> SearchResult:
        """AI web search. Synchronous, no polling. `limit` max 20."""
        return await self._run(ops.search(prompt, limit=limit))

    async def agentic_search(
        self,
        prompt: str,
        *,
        use_browser: bool = True,
        schema: dict[str, Any] | None = None,
        webhook_url: str | None = None,
        wait: bool = True,
        poll_timeout: float | None = None,
    ) -> AgenticSearchResult:
        """
        Multi-stage research: search, scrape citations, structure the answer.

        Typically takes 1-5 minutes; waits at least 600s unless you pass
        `poll_timeout`. Returns a summary plus `structured_data` matching
        `schema` (inferred when omitted).
        """
        return await self._run(
            ops.agentic_search(
                self._cfg,
                prompt,
                use_browser=use_browser,
                schema=schema,
                webhook_url=webhook_url,
                wait=wait,
                poll_timeout=poll_timeout,
            )
        )

    async def get_agentic_search(self, job_id: str) -> AgenticSearchResult:
        """Fetch an agentic search job by ID."""
        return await self._run(ops.get_agentic_search(job_id))


# ─── Wire ─────────────────────────────────────────────────────────────────────


class AsyncWireSourcesResource(_AsyncAPI):
    """
    Identity sources: connect 1Password / Azure Key Vault so `wire.login`
    can read credentials from your vault. Accessible as `client.wire.sources`.
    Responses are plain dicts (provider-specific shapes).
    """

    async def providers(self) -> Any:
        """Connectable providers and the fields each one needs."""
        return await self._run(ops.sources_providers())

    async def list(self) -> builtins.list[dict[str, Any]]:
        return await self._run(ops.sources_list())

    async def get(self, source_id: str) -> Any:
        return await self._run(ops.sources_get(source_id))

    async def create(
        self, provider: str, display_name: str, *, auth_method: str | None = None, **fields: Any
    ) -> Any:
        """Connect a vault. `fields` are the provider's connect fields (e.g. token=...)."""
        return await self._run(ops.sources_create(provider, display_name, auth_method, fields))

    async def update(
        self,
        source_id: str,
        *,
        display_name: str | None = None,
        auth_method: str | None = None,
        **fields: Any,
    ) -> Any:
        """Rename a source and/or rotate its credential."""
        return await self._run(ops.sources_update(source_id, display_name, auth_method, fields))

    async def verify(self, source_id: str) -> Any:
        return await self._run(ops.sources_verify(source_id))

    async def delete(self, source_id: str, *, delete_identities: bool = False) -> Any:
        return await self._run(ops.sources_delete(source_id, delete_identities))

    async def identities(self, source_id: str) -> builtins.list[WireIdentity]:
        return await self._run(ops.sources_identities(source_id))

    async def containers(self, source_id: str) -> builtins.list[dict[str, Any]]:
        return await self._run(ops.sources_containers(source_id))

    async def entries(
        self, source_id: str, container_id: str, *, domain: str | None = None
    ) -> builtins.list[dict[str, Any]]:
        return await self._run(ops.sources_entries(source_id, container_id, domain))


class AsyncWireResource(_AsyncAPI):
    """
    Wire: pre-built actions on hundreds of sites. Accessible as `client.wire`.

    Typical flow::

        matches = await client.wire.discover("top phones on walmart")
        result = await client.wire.run(matches[0].action_id, {"query": "phones"})

    `client.wire(action_id, params)` is shorthand for `client.wire.run(...)`.
    """

    def __init__(self, transport: Any) -> None:
        super().__init__(transport)
        self.sources = AsyncWireSourcesResource(transport)

    async def __call__(
        self,
        action_id: str,
        params: Mapping[str, Any] | None = None,
        *,
        credential_id: str | None = None,
        identity_id: str | None = None,
        webhook_url: str | None = None,
        wait: bool = True,
        poll_timeout: float | None = None,
    ) -> WireResult:
        """Shorthand for `run(...)`."""
        return await self._run(
            ops.wire_run(
                self._cfg,
                action_id,
                params,
                credential_id=credential_id,
                identity_id=identity_id,
                webhook_url=webhook_url,
                wait=wait,
                poll_timeout=poll_timeout,
            )
        )

    async def run(
        self,
        action_id: str,
        params: Mapping[str, Any] | None = None,
        *,
        credential_id: str | None = None,
        identity_id: str | None = None,
        webhook_url: str | None = None,
        wait: bool = True,
        poll_timeout: float | None = None,
    ) -> WireResult:
        """
        Run a Wire action (read or write) via `POST /v1/wire/task`.

        Args:
            credential_id: Required when the action's auth_mode is "required"
                (get one from `identities()` or `login()`).
            wait: False returns immediately; fetch later with `get_job(job_id)`.

        Raises:
            WireAuthRequiredError: connect the account at `err.connect_url`.
            WireAuthExpiredError: the credential's session expired; log in again.
            JobFailedError: the action ran and failed (credits are refunded).
        """
        return await self._run(
            ops.wire_run(
                self._cfg,
                action_id,
                params,
                credential_id=credential_id,
                identity_id=identity_id,
                webhook_url=webhook_url,
                wait=wait,
                poll_timeout=poll_timeout,
            )
        )

    async def zero_touch(self, action_id: str, params: Mapping[str, Any] | None = None) -> WireResult:
        """
        Run a read-only action synchronously with no API key (`POST /v1/wire-run`).

        Metered by a free per-IP allowance; raises `InsufficientCreditsError`
        (with `.signup_url`) when it is used up.
        """
        return await self._run(ops.wire_zero_touch(action_id, params))

    async def get_job(self, job_id: str) -> WireResult:
        """Fetch a Wire job's status/result."""
        return await self._run(ops.wire_get_job(job_id))

    async def download(self, job_id: str, *, file: str | None = None) -> bytes:
        """Download a file produced by a Wire job (see `WireResult.files`)."""
        return await self._run(ops.wire_download(job_id, file))

    async def discover(
        self,
        q: str | None = None,
        *,
        catalog: str | None = None,
        category: str | None = None,
        auth_mode: AuthMode | None = None,
        limit: int | None = None,
    ) -> builtins.list[WireActionMatch]:
        """Find actions by natural-language intent (`GET /v1/wire/resolve`). No key needed."""
        return await self._run(
            ops.wire_discover(
                q, catalog=catalog, category=category, auth_mode=auth_mode, limit=limit
            )
        )

    async def catalogs(self, *, scope: str | None = None) -> builtins.list[WireCatalog]:
        """List every supported website. `scope="my"` = only catalogs with your private actions."""
        return await self._run(ops.wire_catalogs(scope))

    async def catalog(self, slug: str) -> WireCatalogDetail:
        """One site's actions with parameter schemas, credit costs and login fields."""
        return await self._run(ops.wire_catalog(slug))

    async def identities(self, *, catalog_id: str | None = None) -> builtins.list[WireIdentity]:
        """Your saved site accounts. Each `credentials[i].id` is a `credential_id`."""
        return await self._run(ops.wire_identities(catalog_id))

    async def identity(self, identity_id: str) -> WireIdentity:
        return await self._run(ops.wire_identity(identity_id))

    async def login(
        self,
        catalog_slug: str,
        params: Mapping[str, Any] | None = None,
        *,
        identity_name: str | None = None,
        source_id: str | None = None,
        source_ref: Mapping[str, Any] | None = None,
    ) -> WireLoginResult:
        """
        Sign in to a credentials-mode site and get a `credential_id`.

        Pass the fields from `catalog(slug).login_input_schema` as `params`, or
        a vault locator (`source_id` + `source_ref` + `identity_name`). The
        password is never stored. Raises `WireLoginError` if sign-in fails.
        """
        return await self._run(
            ops.wire_login(
                catalog_slug,
                params,
                identity_name=identity_name,
                source_id=source_id,
                source_ref=source_ref,
            )
        )

    async def verify_credential(
        self, identity_id: str, params: Mapping[str, Any] | None = None
    ) -> WireCredential:
        """Re-run sign-in for an existing identity and refresh its session."""
        return await self._run(ops.wire_verify_credential(identity_id, params))

    async def build(
        self,
        website_url: str,
        goal: str,
        *,
        actions: Sequence[str] | None = None,
        catalog_id: str | None = None,
        country: str | None = None,
        credential: Mapping[str, Any] | None = None,
        visibility: str | None = None,
        force: bool = False,
    ) -> WireBuildRequest:
        """
        Request new Wire actions for a site that isn't in the catalog yet.

        Charges credits up front (refunded if the build fails). Track it with
        `get_build(build.id)`. Check `discover()` / `catalogs()` first.
        """
        return await self._run(
            ops.wire_build(
                website_url,
                goal,
                actions=actions,
                catalog_id=catalog_id,
                country=country,
                credential=credential,
                visibility=visibility,
                force=force,
            )
        )

    async def builds(
        self, *, status: str | None = None, page: int | None = None, limit: int | None = None
    ) -> builtins.list[WireBuildRequest]:
        """Your recent build requests."""
        return await self._run(ops.wire_builds(status, page, limit))

    async def get_build(self, build_id: str) -> WireBuildRequest:
        """One build request: status, published `action_id`, and `skipped` capabilities."""
        return await self._run(ops.wire_get_build(build_id))


# ─── Monitors ─────────────────────────────────────────────────────────────────


class AsyncMonitorsResource(_AsyncAPI):
    """Website monitoring (`/v1/monitors`). Accessible as `client.monitors`."""

    async def create(
        self, url: str, interval_minutes: int, **options: Unpack[MonitorOptions]
    ) -> Monitor:
        """
        Watch a page, site, or Wire action every `interval_minutes` (min 15).

        Store `monitor.alert_webhook_secret` when you set `alert_webhook_url`;
        it is only returned here.
        """
        return await self._run(ops.monitors_create(ops.monitor_body(url, interval_minutes, options)))

    async def update(
        self, monitor_id: str, url: str, interval_minutes: int, **options: Unpack[MonitorOptions]
    ) -> Monitor:
        """Replace a monitor's configuration (full update, same fields as `create`)."""
        return await self._run(
            ops.monitors_update(monitor_id, ops.monitor_body(url, interval_minutes, options))
        )

    async def list(self) -> builtins.list[Monitor]:
        return await self._run(ops.monitors_list())

    async def get(self, monitor_id: str) -> Monitor:
        return await self._run(ops.monitors_get(monitor_id))

    async def delete(self, monitor_id: str) -> None:
        """Permanently delete a monitor and its history."""
        await self._run(ops.monitors_delete(monitor_id))

    async def pause(self, monitor_id: str) -> Monitor:
        return await self._run(ops.monitors_pause(monitor_id))

    async def resume(
        self, monitor_id: str, *, expires_at: str | date | datetime | None = None
    ) -> Monitor:
        return await self._run(ops.monitors_resume(monitor_id, expires_at))

    async def set_expiry(self, monitor_id: str, expires_at: str | date | datetime | None) -> Monitor:
        """Change (or with None, remove) a monitor's end date."""
        return await self._run(ops.monitors_set_expiry(monitor_id, expires_at))

    async def run_now(self, monitor_id: str) -> MonitorRun:
        """Queue an immediate check (billed like a scheduled one)."""
        return await self._run(ops.monitors_run_now(monitor_id))

    async def changes(self, monitor_id: str) -> builtins.list[MonitorChange]:
        """Detected changes, newest first (up to 200)."""
        return await self._run(ops.monitors_changes(monitor_id))

    async def snapshots(self, monitor_id: str) -> builtins.list[MonitorSnapshot]:
        return await self._run(ops.monitors_snapshots(monitor_id))

    async def snapshot_content(self, monitor_id: str, snapshot_id: str) -> SnapshotContent:
        return await self._run(ops.monitors_snapshot_content(monitor_id, snapshot_id))

    async def content(self, monitor_id: str, content_hash: str) -> SnapshotContent:
        """Site monitors: a tracked page's stored body by content hash."""
        return await self._run(ops.monitors_content(monitor_id, content_hash))

    async def runs(self, monitor_id: str) -> builtins.list[dict[str, Any]]:
        """Site monitors: per-run summaries."""
        return await self._run(ops.monitors_runs(monitor_id))

    async def pages(self, monitor_id: str) -> builtins.list[dict[str, Any]]:
        """Site monitors: tracked pages."""
        return await self._run(ops.monitors_pages(monitor_id))

    async def remove_page(self, monitor_id: str, url: str) -> None:
        await self._run(ops.monitors_remove_page(monitor_id, url))

    async def restore_page(self, monitor_id: str, url: str) -> None:
        await self._run(ops.monitors_restore_page(monitor_id, url))

    async def test_alert(self, monitor_id: str) -> AlertTestResult:
        """Send a sample alert to the configured webhook/email."""
        return await self._run(ops.monitors_test_alert(monitor_id))

    async def deliveries(self, monitor_id: str) -> builtins.list[Delivery]:
        return await self._run(ops.monitors_deliveries(monitor_id))

    async def retry_delivery(self, monitor_id: str, delivery_id: str) -> None:
        await self._run(ops.monitors_retry_delivery(monitor_id, delivery_id))


# ─── AI Visibility ────────────────────────────────────────────────────────────


class AsyncAIVisibilityResource(_AsyncAPI):
    """Ask ChatGPT, Gemini and Google AI Overview the same question. `client.ai_visibility`."""

    async def search(
        self,
        query: str,
        *,
        sources: Sequence[str] | None = None,
        country: str = "us",
        wait: bool = True,
        poll_timeout: float | None = None,
    ) -> AIVisibilitySearch:
        """
        Fan `query` out to AI answer engines and compare answers.

        `sources` defaults to every enabled engine (see `sources()`). Billed per
        completed source; failed sources are free.
        """
        return await self._run(
            ops.ai_visibility_search(
                self._cfg,
                query,
                sources=sources,
                country=country,
                wait=wait,
                poll_timeout=poll_timeout,
            )
        )

    async def get(self, search_id: str) -> AIVisibilitySearch:
        return await self._run(ops.ai_visibility_get(search_id))

    async def list(self) -> builtins.list[AIVisibilitySearchSummary]:
        """Your 20 most recent searches."""
        return await self._run(ops.ai_visibility_list())

    async def sources(self) -> builtins.list[AIVisibilitySource]:
        """Engines you can pass as `sources`."""
        return await self._run(ops.ai_visibility_sources())

    async def retry(self, search_id: str, source: str) -> AIVisibilitySourceResult:
        """Re-run one failed source of an existing search."""
        return await self._run(ops.ai_visibility_retry(search_id, source))


# ─── Webhooks ─────────────────────────────────────────────────────────────────


class AsyncWebhooksResource(_AsyncAPI):
    """
    Registered webhook endpoints and the delivery log. `client.webhooks`.

    To verify incoming deliveries use `anakin.verify_webhook_signature`.
    """

    async def create(
        self,
        url: str,
        *,
        description: str | None = None,
        events: Sequence[str] | None = None,
    ) -> WebhookEndpoint:
        """Register an endpoint. Store `endpoint.secret`; it's only returned here."""
        return await self._run(ops.webhooks_create(url, description, events))

    async def list(self) -> builtins.list[WebhookEndpoint]:
        return await self._run(ops.webhooks_list())

    async def update(
        self,
        endpoint_id: str,
        *,
        url: str | None = None,
        description: str | None = None,
        events: Sequence[str] | None = None,
        is_active: bool | None = None,
    ) -> WebhookEndpoint:
        return await self._run(
            ops.webhooks_update(
                endpoint_id, url=url, description=description, events=events, is_active=is_active
            )
        )

    async def delete(self, endpoint_id: str) -> None:
        await self._run(ops.webhooks_delete(endpoint_id))

    async def test(self, endpoint_id: str) -> WebhookTestResult:
        """Send a `webhook.test` event to the endpoint."""
        return await self._run(ops.webhooks_test(endpoint_id))

    async def deliveries(
        self,
        *,
        endpoint_id: str | None = None,
        event: str | None = None,
        status: str | None = None,
        job_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Delivery]:
        """Account-wide delivery log (30-day retention), newest first."""
        return await self._run(
            ops.webhooks_deliveries(
                endpoint_id=endpoint_id, event=event, status=status, job_id=job_id, limit=limit
            )
        )

    async def resend(self, delivery_id: str) -> None:
        """Resend a failed/exhausted delivery (byte-identical body and signature)."""
        await self._run(ops.webhooks_resend(delivery_id))

    async def signing_secret(self) -> str:
        """The default secret that signs per-request `webhook_url` deliveries."""
        return await self._run(ops.webhooks_signing_secret())

    async def rotate_signing_secret(self) -> str:
        return await self._run(ops.webhooks_rotate_signing_secret())

    async def events(self) -> builtins.list[str]:
        """Every event type you can subscribe to."""
        return await self._run(ops.webhooks_events())


# ─── Browser sessions & Browser API ───────────────────────────────────────────


class AsyncSessionsResource(_AsyncAPI):
    """Saved browser sessions (logged-in states). Accessible as `client.sessions`."""

    async def list(self, *, domain: str | None = None) -> builtins.list[BrowserSession]:
        return await self._run(ops.sessions_list(domain))

    async def create(
        self,
        *,
        website_url: str,
        name: str,
        record: bool = False,
        session_type: str = "manual",
    ) -> BrowserSessionHandle:
        """
        Start an interactive browser session. Open `handle.novnc_url`, log in,
        then call `save(...)`.
        """
        return await self._run(ops.sessions_create(website_url, name, record, session_type))

    async def save(self, browser_instance_id: str) -> BrowserSession:
        """Save the session state (cookies/storage) after the user has finished."""
        return await self._run(ops.sessions_save(browser_instance_id))

    async def update(self, session_id: str, *, name: str) -> BrowserSession:
        return await self._run(ops.sessions_update(session_id, name))

    async def delete(self, session_id: str) -> None:
        await self._run(ops.sessions_delete(session_id))


class AsyncRecordingsResource(_AsyncAPI):
    """Browser API session recordings (`connect_url(record=True)`)."""

    async def list(self) -> builtins.list[Recording]:
        return await self._run(ops.recordings_list())

    async def get(self, recording_id: str) -> Recording:
        """Includes `video_url`, presigned for 1 hour."""
        return await self._run(ops.recordings_get(recording_id))


class AsyncBrowserResource(_BrowserStaticMixin, _AsyncAPI):
    """Browser API helpers. Accessible as `client.browser`."""

    def __init__(self, transport: Any) -> None:
        super().__init__(transport)
        self.recordings = AsyncRecordingsResource(transport)
