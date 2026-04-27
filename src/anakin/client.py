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
from anakin.models import CrawlResult, Document, MapResult

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


# ─── helpers ──────────────────────────────────────────────────────────────────


def _is_job_terminal(body: dict[str, Any]) -> bool:
    return body.get("status") in {"completed", "failed"}


def _require_job_id(submitted: dict[str, Any]) -> str:
    job_id = submitted.get("jobId") or submitted.get("job_id") or submitted.get("id")
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError(
            f"Anakin API response did not include a job id: {submitted!r}. "
            f"This is likely an SDK/API version mismatch."
        )
    return job_id
