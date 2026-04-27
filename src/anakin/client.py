"""
Anakin client — public entry point.

Quickstart:
    from anakin import Anakin
    client = Anakin(api_key="ak-...")
    doc = client.scrape("https://example.com")
    print(doc.markdown)

Surface defined in docs/SDK_API_CONTRACT.md (Anakin SDK contract v0.1).
"""

from __future__ import annotations

from typing import Any, Literal

from anakin._http import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLL_MAX_INTERVAL,
    DEFAULT_POLL_TIMEOUT,
    DEFAULT_TIMEOUT,
    HttpClient,
)
from anakin.errors import JobFailedError
from anakin.models import (
    ActivitySummary,
    AgenticSearchResult,
    BrowserSession,
    BrowserSessionHandle,
    Country,
    CrawlResult,
    Document,
    MapResult,
    Recording,
    SearchResult,
    WireResult,
)

ScrapeFormat = Literal[
    "markdown",
    "html",
    "cleanedHtml",
    "json",
    "links",
    "images",
    "screenshot",
    "screenshotFullPage",
    "summary",
]


class Anakin:
    """
    Anakin SDK client.

    Args:
        api_key: API key. If omitted, falls back to ANAKIN_API_KEY env var.
        base_url: API base URL. Default https://api.anakin.io/v1; override only
            for internal/test environments.
        timeout: HTTP request timeout in seconds.
        max_retries: Retries on 429/5xx/network errors before raising.
        poll_interval: Initial polling delay in seconds.
        poll_max_interval: Maximum polling delay (cap on exponential backoff).
        poll_timeout: Total wait time for polling jobs, in seconds, before
            raising JobTimeoutError.
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
        self._http = HttpClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._poll_interval = poll_interval
        self._poll_max_interval = poll_max_interval
        self._poll_timeout = poll_timeout

        # Sub-namespaces
        self.sessions = SessionsClient(self._http)
        self.recordings = RecordingsClient(self._http)
        self.activity = ActivityClient(self._http)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> Anakin:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ─── scrape ───────────────────────────────────────────────────────────────

    def scrape(
        self,
        url: str,
        *,
        formats: list[ScrapeFormat] | tuple[ScrapeFormat, ...] = ("markdown",),
        country: str = "us",
        use_browser: bool = False,
        generate_json: bool = False,
        force_fresh: bool = False,
        session_id: str | None = None,
        session_name: str | None = None,
        poll_timeout: float | None = None,
    ) -> Document:
        """
        Scrape a single URL and return the result.

        Submits to POST /v1/url-scraper, then polls /v1/url-scraper/:id until
        the job reaches a terminal state (completed or failed).
        """
        body: dict[str, Any] = {
            "url": url,
            "country": country,
            "formats": list(formats),
            "useBrowser": use_browser,
            "generateJson": generate_json,
            "forceFresh": force_fresh,
        }
        if session_id is not None:
            body["sessionId"] = session_id
        if session_name is not None:
            body["sessionName"] = session_name

        submitted = self._http.post("/url-scraper", json=body)
        job_id = _require_job_id(submitted)
        result = self._http.poll(
            f"/url-scraper/{job_id}",
            is_terminal=_is_job_terminal,
            poll_interval=self._poll_interval,
            poll_max_interval=self._poll_max_interval,
            poll_timeout=poll_timeout if poll_timeout is not None else self._poll_timeout,
        )
        if result.get("status") == "failed":
            raise JobFailedError(
                result.get("error") or "Scrape job failed",
                status_code=None,
                code=None,
                body=result,
            )
        return Document.model_validate(result)

    # ─── map ──────────────────────────────────────────────────────────────────

    def map(
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
        poll_timeout: float | None = None,
    ) -> MapResult:
        """
        Discover URLs on a website (sitemap + link traversal).

        Submits to POST /v1/map, polls /v1/map/:id until done.
        """
        body: dict[str, Any] = {
            "url": url,
            "limit": limit,
            "depth": depth,
            "limitPerLevel": limit_per_level,
            "includeSubdomains": include_subdomains,
            "includeExternalLinks": include_external_links,
            "useBrowser": use_browser,
        }
        if search is not None:
            body["search"] = search
        if session_id is not None:
            body["sessionId"] = session_id

        submitted = self._http.post("/map", json=body)
        job_id = _require_job_id(submitted)
        result = self._http.poll(
            f"/map/{job_id}",
            is_terminal=_is_job_terminal,
            poll_interval=self._poll_interval,
            poll_max_interval=self._poll_max_interval,
            poll_timeout=poll_timeout if poll_timeout is not None else self._poll_timeout,
        )
        if result.get("status") == "failed":
            raise JobFailedError(
                result.get("error") or "Map job failed",
                status_code=None,
                code=None,
                body=result,
            )
        return MapResult.model_validate(result)

    # ─── crawl ────────────────────────────────────────────────────────────────

    def crawl(
        self,
        url: str,
        *,
        max_pages: int = 10,
        depth: int = 1,
        include_patterns: list[str] | tuple[str, ...] = (),
        exclude_patterns: list[str] | tuple[str, ...] = (),
        country: str = "us",
        use_browser: bool = False,
        session_id: str | None = None,
        poll_timeout: float | None = None,
    ) -> CrawlResult:
        """
        Crawl a website and return the scraped pages.

        Submits to POST /v1/crawl, polls /v1/crawl/:id until done.
        """
        body: dict[str, Any] = {
            "url": url,
            "maxPages": max_pages,
            "depth": depth,
            "country": country,
            "useBrowser": use_browser,
        }
        if include_patterns:
            body["includePatterns"] = list(include_patterns)
        if exclude_patterns:
            body["excludePatterns"] = list(exclude_patterns)
        if session_id is not None:
            body["sessionId"] = session_id

        submitted = self._http.post("/crawl", json=body)
        job_id = _require_job_id(submitted)
        result = self._http.poll(
            f"/crawl/{job_id}",
            is_terminal=_is_job_terminal,
            poll_interval=self._poll_interval,
            poll_max_interval=self._poll_max_interval,
            poll_timeout=poll_timeout if poll_timeout is not None else self._poll_timeout,
        )
        if result.get("status") == "failed":
            raise JobFailedError(
                result.get("error") or "Crawl job failed",
                status_code=None,
                code=None,
                body=result,
            )
        return CrawlResult.model_validate(result)

    # ─── web_scrape (custom scraper) ──────────────────────────────────────────

    def web_scrape(
        self,
        url: str,
        *,
        scraper_code: str,
        scraper_scope: str = "GLOBAL",
        scraper_params: dict[str, Any] | None = None,
        action_type: str = "scrape_data",
        poll_timeout: float | None = None,
    ) -> Document:
        """
        Run a custom scraper against a URL.

        Submits to POST /v1/web-scraper, polls /v1/web-scraper/:id. Returns the
        same `Document` shape as `scrape()` once the underlying scraper finishes.
        """
        body: dict[str, Any] = {
            "url": url,
            "scraper_code": scraper_code,
            "scraper_scope": scraper_scope,
            "scraper_params": scraper_params or {},
            "action_type": action_type,
        }
        submitted = self._http.post("/web-scraper", json=body)
        job_id = _require_job_id(submitted)
        result = self._http.poll(
            f"/web-scraper/{job_id}",
            is_terminal=_is_job_terminal,
            poll_interval=self._poll_interval,
            poll_max_interval=self._poll_max_interval,
            poll_timeout=poll_timeout if poll_timeout is not None else self._poll_timeout,
        )
        if result.get("status") == "failed":
            raise JobFailedError(
                result.get("error") or "Web-scrape job failed",
                status_code=None,
                code=None,
                body=result,
            )
        return Document.model_validate(result)

    # ─── search (synchronous) ─────────────────────────────────────────────────

    def search(self, prompt: str, *, limit: int = 5) -> SearchResult:
        """
        AI-powered web search. Synchronous — returns directly, no polling.

        Costs 3 credits per call.
        """
        body = {"prompt": prompt, "limit": limit}
        result = self._http.post("/search", json=body)
        return SearchResult.model_validate(result)

    # ─── agentic_search ──────────────────────────────────────────────────────

    def agentic_search(
        self,
        prompt: str,
        *,
        use_browser: bool = True,
        schema: dict[str, Any] | None = None,
        poll_timeout: float | None = None,
    ) -> AgenticSearchResult:
        """
        Multi-stage AI research pipeline. Returns AI-generated summary plus
        structured data matching the optional `schema`.

        Submits to POST /v1/agentic-search, polls /v1/agentic-search/:id.
        Costs 10 credits.
        """
        body: dict[str, Any] = {"prompt": prompt, "useBrowser": use_browser}
        if schema is not None:
            body["schema"] = schema
        submitted = self._http.post("/agentic-search", json=body)
        job_id = _require_job_id(submitted)
        result = self._http.poll(
            f"/agentic-search/{job_id}",
            is_terminal=_is_job_terminal,
            poll_interval=self._poll_interval,
            poll_max_interval=self._poll_max_interval,
            poll_timeout=poll_timeout if poll_timeout is not None else self._poll_timeout,
        )
        if result.get("status") == "failed":
            raise JobFailedError(
                result.get("error") or "Agentic-search job failed",
                status_code=None,
                code=None,
                body=result,
            )
        return AgenticSearchResult.model_validate(result)

    # ─── wire (pre-built actions, /v1/holocron/) ──────────────────────────────

    def wire(
        self,
        action_id: str,
        params: dict[str, Any],
        *,
        poll_timeout: float | None = None,
    ) -> WireResult:
        """
        Run a pre-built Wire action. Find action IDs in the Wire dashboard.

        Submits to POST /v1/holocron/task, polls /v1/holocron/jobs/:id.
        Note the polling path differs from the submit path — the API returns a
        `job_id` (snake_case here) which is used as the path segment.

        Raises `WireAuthRequiredError` if the action requires the user to first
        connect a third-party account (e.g. LinkedIn) — caller can read
        `error.connect_url` and direct the user there.
        """
        body = {"action_id": action_id, "params": params}
        submitted = self._http.post("/holocron/task", json=body)
        job_id = _require_job_id(submitted)

        # Wire uses /v1/holocron/jobs/:id for polling, not /v1/holocron/task/:id.
        result = self._http.poll(
            f"/holocron/jobs/{job_id}",
            is_terminal=_is_wire_terminal,
            poll_interval=self._poll_interval,
            poll_max_interval=self._poll_max_interval,
            poll_timeout=poll_timeout if poll_timeout is not None else self._poll_timeout,
        )
        # Wire poll responses don't always echo the job_id; inject it for the model.
        if "job_id" not in result:
            result["job_id"] = job_id
        wire_result = WireResult.model_validate(result)
        if wire_result.status == "failed":
            err_msg = wire_result.error.message if wire_result.error else "Wire action failed"
            raise JobFailedError(err_msg, status_code=None, code=None, body=result)
        return wire_result

    # ─── countries (static — no network call) ─────────────────────────────────

    def countries(self) -> list[Country]:
        """
        Return the list of supported proxy countries.

        Backed by a static list bundled with the SDK (`anakin.countries`) — no
        network round-trip. Regenerated from the live API at SDK release time.
        Use `anakin.SUPPORTED_COUNTRIES` directly for module-level access.
        """
        from anakin.countries import SUPPORTED_COUNTRIES

        return list(SUPPORTED_COUNTRIES)


# ─── Sub-namespace clients ────────────────────────────────────────────────────


class SessionsClient:
    """Browser-session CRUD. Accessible as `client.sessions.*`."""

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(self, *, domain: str | None = None) -> list[BrowserSession]:
        params = {"domain": domain} if domain else None
        body = self._http.get("/sessions", params=params)
        items = _unwrap_list(body, "sessions")
        return [BrowserSession.model_validate(s) for s in items]

    def create(
        self,
        *,
        website_url: str,
        name: str,
        record: bool = False,
        session_type: str = "manual",
    ) -> BrowserSessionHandle:
        """
        Start an interactive browser session with noVNC access. Returns a
        handle containing the noVNC URL the user opens to log in / navigate.
        """
        body = {
            "websiteUrl": website_url,
            "name": name,
            "record": record,
            "sessionType": session_type,
        }
        result = self._http.post("/sessions/manual-start", json=body)
        return BrowserSessionHandle.model_validate(result)

    def save(self, browser_instance_id: str) -> BrowserSession:
        """Save the session state (cookies/storage) after the user has finished."""
        body = {"browserInstanceId": browser_instance_id}
        result = self._http.post("/sessions/manual-save", json=body)
        return BrowserSession.model_validate(result)

    def update(self, session_id: str, *, name: str) -> BrowserSession:
        result = self._http.patch(f"/sessions/{session_id}", json={"name": name})
        return BrowserSession.model_validate(result)

    def delete(self, session_id: str) -> None:
        self._http.delete(f"/sessions/{session_id}")


class RecordingsClient:
    """Browser-session recordings. Accessible as `client.recordings.*`."""

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(self) -> list[Recording]:
        body = self._http.get("/recordings")
        items = _unwrap_list(body, "recordings")
        return [Recording.model_validate(r) for r in items]

    def get(self, conn_id: str) -> Recording:
        body = self._http.get(f"/recordings/{conn_id}")
        return Recording.model_validate(body)


class ActivityClient:
    """Telemetry activity. Accessible as `client.activity.*`."""

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def summary(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> ActivitySummary:
        params: dict[str, Any] = {}
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date
        body = self._http.get("/telemetry/activity/summary", params=params or None)
        return ActivitySummary.from_response(body)


# ─── helpers ──────────────────────────────────────────────────────────────────


def _unwrap_list(body: Any, key: str) -> list[Any]:
    """
    Tolerate the three response shapes Anakin returns for collection endpoints:

    - ``[item, item, ...]``           (plain list)
    - ``{"key": [item, item, ...]}``   (wrapped, populated)
    - ``{"key": null}`` or ``{}``      (wrapped, empty)
    """
    if isinstance(body, list):
        return body
    if not isinstance(body, dict):
        return []
    items = body.get(key)
    if items is None:
        return []
    if isinstance(items, list):
        return items
    return []


def _is_job_terminal(body: dict[str, Any]) -> bool:
    return body.get("status") in {"completed", "failed"}


def _is_wire_terminal(body: dict[str, Any]) -> bool:
    """Wire uses {processing, completed, failed} (no `pending`)."""
    return body.get("status") in {"completed", "failed"}


def _require_job_id(submitted: dict[str, Any]) -> str:
    job_id = submitted.get("jobId") or submitted.get("job_id") or submitted.get("id")
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError(
            f"Anakin API response did not include a job id: {submitted!r}. "
            f"This is likely an SDK/API version mismatch."
        )
    return job_id
