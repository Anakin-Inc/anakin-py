"""
Every SDK operation, written once as a sans-IO generator.

An operation yields `Call` / `Wait` commands and returns a parsed model.
`SyncTransport.run` and `AsyncTransport.run` (in `anakin._http`) execute
them, so `Anakin` and `AsyncAnakin` share request building, polling and
parsing. Internal: signatures here may change between minor versions.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any, TypeVar
from urllib.parse import quote

from pydantic import BaseModel

from anakin._http import Call, ClientConfig, Op, Wait
from anakin.errors import (
    AnakinError,
    InvalidRequestError,
    JobFailedError,
    JobTimeoutError,
    WireLoginError,
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

M = TypeVar("M", bound=BaseModel)

TERMINAL = frozenset({"completed", "failed"})
# Agentic search takes 1-5 minutes; never wait less than this by default.
AGENTIC_MIN_POLL_TIMEOUT = 600.0
AGENTIC_MIN_POLL_INTERVAL = 5.0
# The inline scrape endpoint holds the connection up to ~90s.
INLINE_SCRAPE_TIMEOUT = 120.0
MAX_BATCH_URLS = 10


# ─── helpers ──────────────────────────────────────────────────────────────────


def compact(body: Mapping[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None so optional params aren't sent."""
    return {k: v for k, v in body.items() if v is not None}


def _date(value: str | date | datetime | None) -> str | None:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _seg(value: str) -> str:
    """Percent-encode a path segment (IDs, slugs, Azure vault URLs)."""
    return quote(value, safe="")


def unwrap_list(body: Any, *keys: str) -> list[Any]:
    """
    Tolerate the response shapes Anakin uses for collections:
    ``[...]``, ``{"key": [...]}``, ``{"key": null}`` and ``{}``.
    """
    if isinstance(body, list):
        return body
    if not isinstance(body, dict):
        return []
    for key in keys:
        items = body.get(key)
        if isinstance(items, list):
            return items
    return []


def _models(model: type[M], items: Sequence[Any]) -> list[M]:
    return [model.model_validate(item) for item in items]


def require_job_id(submitted: Any) -> str:
    job_id = None
    if isinstance(submitted, dict):
        job_id = (
            submitted.get("jobId")
            or submitted.get("job_id")
            or submitted.get("id")
            or submitted.get("search_id")
        )
    if not isinstance(job_id, str) or not job_id:
        raise AnakinError(
            f"Anakin API response did not include a job id: {submitted!r}. "
            "This is likely an SDK/API version mismatch; please upgrade anakin-sdk.",
            body=submitted,
        )
    return job_id


def _is_terminal(body: Any) -> bool:
    return isinstance(body, dict) and body.get("status") in TERMINAL


def poll(
    cfg: ClientConfig,
    path: str,
    *,
    job_id: str,
    timeout: float | None = None,
    interval: float | None = None,
    is_terminal: Callable[[Any], bool] = _is_terminal,
    auth: bool = True,
) -> Op[dict[str, Any]]:
    """
    GET `path` until `is_terminal(body)`.

    Backoff starts at `interval`, x1.5 per poll, capped at `poll_max_interval`.
    A server-sent `retry_after_ms` (Wire) overrides the computed delay.
    """
    total = cfg.poll_timeout if timeout is None else timeout
    deadline = time.monotonic() + total
    wait = cfg.poll_interval if interval is None else interval
    polls = 0
    while True:
        polls += 1
        body = yield Call("GET", path, auth=auth)
        if is_terminal(body):
            return body  # type: ignore[no-any-return]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise JobTimeoutError(
                f"Job {job_id} did not finish within {total:g}s ({polls} polls). It is still "
                "running server-side; fetch it later with the matching get_* method.",
                job_id=job_id,
                body=body,
            )
        hint = body.get("retry_after_ms") if isinstance(body, dict) else None
        delay = hint / 1000 if isinstance(hint, int | float) and hint > 0 else wait
        yield Wait(min(delay, remaining))
        wait = min(wait * 1.5, cfg.poll_max_interval)


def _raise_if_failed(result: dict[str, Any], *, job_id: str, label: str) -> None:
    if result.get("status") != "failed":
        return
    error = result.get("error")
    if isinstance(error, dict):
        raise JobFailedError(
            error.get("message") or f"{label} failed",
            code=error.get("code"),
            job_id=job_id,
            body=result,
        )
    raise JobFailedError(str(error or f"{label} failed"), job_id=job_id, body=result)


def _job(
    cfg: ClientConfig,
    *,
    submit_path: str,
    poll_path: str,
    body: dict[str, Any],
    model: type[M],
    label: str,
    wait: bool,
    poll_timeout: float | None,
    seed: dict[str, Any] | None = None,
    min_timeout: float | None = None,
    min_interval: float | None = None,
) -> Op[M]:
    """Submit an async job, then (optionally) poll it to a terminal state."""
    submitted = yield Call("POST", submit_path, json=body)
    job_id = require_job_id(submitted)
    if not wait:
        status = submitted.get("status", "pending") if isinstance(submitted, dict) else "pending"
        return model.model_validate({**(seed or {}), "id": job_id, "status": status})
    timeout = poll_timeout
    if timeout is None:
        timeout = cfg.poll_timeout
        if min_timeout is not None:
            timeout = max(timeout, min_timeout)
    interval = cfg.poll_interval
    if min_interval is not None:
        interval = max(interval, min_interval)
    result = yield from poll(
        cfg, f"{poll_path}/{job_id}", job_id=job_id, timeout=timeout, interval=interval
    )
    _raise_if_failed(result, job_id=job_id, label=label)
    return model.model_validate({**(seed or {}), **result})


def _get(path: str, model: type[M], *, key: str | None = None, auth: bool = True) -> Op[M]:
    body = yield Call("GET", path, auth=auth)
    if key is not None and isinstance(body, dict) and isinstance(body.get(key), dict):
        body = body[key]
    return model.model_validate(body)


def _list(
    path: str,
    model: type[M],
    *keys: str,
    params: dict[str, Any] | None = None,
    auth: bool = True,
) -> Op[list[M]]:
    body = yield Call("GET", path, params=params, auth=auth)
    return _models(model, unwrap_list(body, *keys))


def _call(
    method: str,
    path: str,
    *,
    json: Any = None,
    params: dict[str, Any] | None = None,
) -> Op[Any]:
    return (yield Call(method, path, json=json, params=params))


# ─── scrape / map / crawl / search / agentic search ───────────────────────────


def scrape(
    cfg: ClientConfig,
    url: str,
    *,
    formats: Sequence[str],
    country: str,
    use_browser: bool,
    generate_json: bool,
    output_schema: dict[str, Any] | None,
    actions: Sequence[dict[str, Any]] | None,
    force_fresh: bool,
    session_id: str | None,
    session_name: str | None,
    webhook_url: str | None,
    inline: bool | None,
    wait: bool,
    poll_timeout: float | None,
) -> Op[Document]:
    body = compact(
        {
            "url": url,
            "formats": list(formats),
            "country": country,
            "useBrowser": use_browser,
            "generateJson": generate_json,
            "outputSchema": output_schema,
            "actions": list(actions) if actions is not None else None,
            "forceFresh": force_fresh,
            "sessionId": session_id,
            "sessionName": session_name,
            "webhook_url": webhook_url,
        }
    )
    # Keyless on the hosted API -> the inline (Zero Touch) endpoint.
    use_inline = (not cfg.api_key and cfg.is_hosted) if inline is None else inline
    if not use_inline:
        return (
            yield from _job(
                cfg,
                submit_path="/url-scraper",
                poll_path="/url-scraper",
                body=body,
                model=Document,
                label="Scrape job",
                wait=wait,
                poll_timeout=poll_timeout,
                seed={"url": url},
            )
        )

    # Inline endpoint: blocks up to ~90s, works without an API key (Zero Touch).
    result = yield Call(
        "POST",
        "/url-scraper/scrape",
        json=body,
        auth=False,
        timeout=max(cfg.timeout, INLINE_SCRAPE_TIMEOUT),
    )
    if not isinstance(result, dict):
        result = {}
    result.setdefault("url", url)
    result.setdefault("id", "")
    result.setdefault("status", "completed")
    if result["status"] not in TERMINAL and wait and result["id"]:
        # 202 fallback: the inline wait budget ran out, keep polling.
        job_id = result["id"]
        polled = yield from poll(
            cfg, f"/url-scraper/{_seg(job_id)}", job_id=job_id, timeout=poll_timeout, auth=False
        )
        result = {**result, **polled}
    _raise_if_failed(result, job_id=result["id"], label="Scrape job")
    return Document.model_validate(result)


def scrape_batch(
    cfg: ClientConfig,
    urls: Sequence[str],
    *,
    country: str,
    use_browser: bool,
    generate_json: bool,
    session_id: str | None,
    webhook_url: str | None,
    wait: bool,
    poll_timeout: float | None,
) -> Op[BatchScrapeResult]:
    urls = list(urls)
    if not 1 <= len(urls) <= MAX_BATCH_URLS:
        raise InvalidRequestError(
            f"scrape_batch accepts 1-{MAX_BATCH_URLS} URLs, got {len(urls)}. "
            "Split larger lists into chunks, or use crawl() for whole sites."
        )
    body = compact(
        {
            "urls": urls,
            "country": country,
            "useBrowser": use_browser,
            "generateJson": generate_json,
            "sessionId": session_id,
            "webhook_url": webhook_url,
        }
    )
    return (
        yield from _job(
            cfg,
            submit_path="/url-scraper/batch",
            poll_path="/url-scraper",
            body=body,
            model=BatchScrapeResult,
            label="Batch scrape job",
            wait=wait,
            poll_timeout=poll_timeout,
            seed={"urls": urls},
        )
    )


def get_scrape(job_id: str) -> Op[Document]:
    return (yield from _get(f"/url-scraper/{_seg(job_id)}", Document))


def get_scrape_batch(job_id: str) -> Op[BatchScrapeResult]:
    return (yield from _get(f"/url-scraper/{_seg(job_id)}", BatchScrapeResult))


def download_screenshot(job_id: str, *, full_page: bool) -> Op[bytes]:
    params = {"type": "fullpage" if full_page else "viewport"}
    content = yield Call("GET", f"/url-scraper/{_seg(job_id)}/screenshot", params=params, raw=True)
    return bytes(content)


def map_site(
    cfg: ClientConfig,
    url: str,
    *,
    limit: int,
    depth: int,
    limit_per_level: int,
    include_subdomains: bool,
    include_external_links: bool,
    search: str | None,
    use_browser: bool,
    session_id: str | None,
    webhook_url: str | None,
    wait: bool,
    poll_timeout: float | None,
) -> Op[MapResult]:
    body = compact(
        {
            "url": url,
            "limit": limit,
            "depth": depth,
            "limitPerLevel": limit_per_level,
            "includeSubdomains": include_subdomains,
            "includeExternalLinks": include_external_links,
            "search": search,
            "useBrowser": use_browser,
            "sessionId": session_id,
            "webhook_url": webhook_url,
        }
    )
    return (
        yield from _job(
            cfg,
            submit_path="/map",
            poll_path="/map",
            body=body,
            model=MapResult,
            label="Map job",
            wait=wait,
            poll_timeout=poll_timeout,
            seed={"url": url},
        )
    )


def get_map(job_id: str) -> Op[MapResult]:
    return (yield from _get(f"/map/{_seg(job_id)}", MapResult))


def crawl(
    cfg: ClientConfig,
    url: str,
    *,
    max_pages: int,
    depth: int,
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
    country: str,
    use_browser: bool,
    session_id: str | None,
    session_name: str | None,
    webhook_url: str | None,
    wait: bool,
    poll_timeout: float | None,
) -> Op[CrawlResult]:
    body = compact(
        {
            "url": url,
            "maxPages": max_pages,
            "depth": depth,
            "includePatterns": list(include_patterns) or None,
            "excludePatterns": list(exclude_patterns) or None,
            "country": country,
            "useBrowser": use_browser,
            "sessionId": session_id,
            "sessionName": session_name,
            "webhook_url": webhook_url,
        }
    )
    return (
        yield from _job(
            cfg,
            submit_path="/crawl",
            poll_path="/crawl",
            body=body,
            model=CrawlResult,
            label="Crawl job",
            wait=wait,
            poll_timeout=poll_timeout,
            seed={"url": url},
        )
    )


def get_crawl(job_id: str) -> Op[CrawlResult]:
    return (yield from _get(f"/crawl/{_seg(job_id)}", CrawlResult))


def search(prompt: str, *, limit: int) -> Op[SearchResult]:
    result = yield Call("POST", "/search", json={"prompt": prompt, "limit": limit})
    return SearchResult.model_validate(result)


def agentic_search(
    cfg: ClientConfig,
    prompt: str,
    *,
    use_browser: bool,
    schema: dict[str, Any] | None,
    webhook_url: str | None,
    wait: bool,
    poll_timeout: float | None,
) -> Op[AgenticSearchResult]:
    body = compact(
        {
            "prompt": prompt,
            "useBrowser": use_browser,
            "schema": schema,
            "webhook_url": webhook_url,
        }
    )
    return (
        yield from _job(
            cfg,
            submit_path="/agentic-search",
            poll_path="/agentic-search",
            body=body,
            model=AgenticSearchResult,
            label="Agentic search job",
            wait=wait,
            poll_timeout=poll_timeout,
            min_timeout=AGENTIC_MIN_POLL_TIMEOUT,
            min_interval=AGENTIC_MIN_POLL_INTERVAL,
        )
    )


def get_agentic_search(job_id: str) -> Op[AgenticSearchResult]:
    return (yield from _get(f"/agentic-search/{_seg(job_id)}", AgenticSearchResult))


# ─── Wire ─────────────────────────────────────────────────────────────────────


def _wire_result(body: Any, job_id: str | None) -> WireResult:
    data = dict(body) if isinstance(body, dict) else {"data": body}
    if job_id and not data.get("job_id"):
        data["job_id"] = job_id
    data.setdefault("status", "completed")
    return WireResult.model_validate(data)


def _raise_if_wire_failed(result: WireResult) -> None:
    if result.status == "failed":
        message = result.error.message if result.error and result.error.message else None
        raise JobFailedError(
            message or "Wire action failed",
            code=result.error.code if result.error else None,
            job_id=result.job_id,
            body=result.model_dump(),
        )


def wire_run(
    cfg: ClientConfig,
    action_id: str,
    params: Mapping[str, Any] | None,
    *,
    credential_id: str | None,
    identity_id: str | None,
    webhook_url: str | None,
    wait: bool,
    poll_timeout: float | None,
) -> Op[WireResult]:
    body = compact(
        {
            "action_id": action_id,
            "params": dict(params or {}),
            "credential_id": credential_id,
            "identity_id": identity_id,
            "webhook_url": webhook_url,
        }
    )
    submitted = yield Call("POST", "/wire/task", json=body)
    if _is_terminal(submitted):
        # `mode: "sync"` actions answer inline.
        result = _wire_result(submitted, submitted.get("job_id"))
        _raise_if_wire_failed(result)
        return result
    job_id = require_job_id(submitted)
    if not wait:
        return _wire_result({"status": submitted.get("status", "processing")}, job_id)
    polled = yield from poll(
        cfg, f"/wire/jobs/{_seg(job_id)}", job_id=job_id, timeout=poll_timeout
    )
    result = _wire_result(polled, job_id)
    _raise_if_wire_failed(result)
    return result


def wire_zero_touch(action_id: str, params: Mapping[str, Any] | None) -> Op[WireResult]:
    body = yield Call(
        "POST",
        "/wire-run",
        json={"action_id": action_id, "params": dict(params or {})},
        auth=False,
        timeout=INLINE_SCRAPE_TIMEOUT,
    )
    if isinstance(body, dict) and "status" not in body and "data" not in body:
        trial = body.get("trial")
        body = {"data": {k: v for k, v in body.items() if k != "trial"}, "trial": trial}
    result = _wire_result(body, None)
    _raise_if_wire_failed(result)
    return result


def wire_get_job(job_id: str) -> Op[WireResult]:
    body = yield Call("GET", f"/wire/jobs/{_seg(job_id)}")
    return _wire_result(body, job_id)


def wire_download(job_id: str, file: str | None) -> Op[bytes]:
    content = yield Call(
        "GET", f"/wire/jobs/{_seg(job_id)}/download", params={"file": file}, raw=True
    )
    return bytes(content)


def wire_discover(
    q: str | None,
    *,
    catalog: str | None,
    category: str | None,
    auth_mode: str | None,
    limit: int | None,
) -> Op[list[WireActionMatch]]:
    params = {"q": q, "catalog": catalog, "category": category, "auth_mode": auth_mode}
    matches = yield from _list("/wire/resolve", WireActionMatch, "results", params=params, auth=False)
    return matches[:limit] if limit is not None else matches


def wire_catalogs(scope: str | None) -> Op[list[WireCatalog]]:
    return (
        yield from _list("/wire/catalog", WireCatalog, "catalog", params={"scope": scope}, auth=False)
    )


def wire_catalog(slug: str) -> Op[WireCatalogDetail]:
    return (yield from _get(f"/wire/catalog/{_seg(slug)}", WireCatalogDetail, auth=False))


def wire_identities(catalog_id: str | None) -> Op[list[WireIdentity]]:
    return (
        yield from _list(
            "/wire/identities", WireIdentity, "identities", params={"catalog_id": catalog_id}
        )
    )


def wire_identity(identity_id: str) -> Op[WireIdentity]:
    return (yield from _get(f"/wire/identities/{_seg(identity_id)}", WireIdentity, key="identity"))


def _check_verified(body: Any) -> dict[str, Any]:
    if isinstance(body, dict) and body.get("status") == "verified":
        return body
    err = body.get("error") if isinstance(body, dict) else None
    err = err if isinstance(err, dict) else {}
    raise WireLoginError(
        err.get("message") or "Wire sign-in failed",
        code=err.get("code") or "LOGIN_FAILED",
        body=body,
    )


def wire_login(
    catalog_slug: str,
    params: Mapping[str, Any] | None,
    *,
    identity_name: str | None,
    source_id: str | None,
    source_ref: Mapping[str, Any] | None,
) -> Op[WireLoginResult]:
    body = compact(
        {
            "catalog_slug": catalog_slug,
            "params": dict(params) if params is not None else None,
            "identity_name": identity_name,
            "source_id": source_id,
            "source_ref": dict(source_ref) if source_ref is not None else None,
        }
    )
    result = yield Call("POST", "/wire/login", json=body)
    return WireLoginResult.model_validate(_check_verified(result))


def wire_verify_credential(
    identity_id: str, params: Mapping[str, Any] | None
) -> Op[WireCredential]:
    body = {"identity_id": identity_id, "params": dict(params or {})}
    result = _check_verified((yield Call("POST", "/wire/credentials/verify", json=body)))
    return WireCredential.model_validate(result.get("credential", {}))


def wire_build(
    website_url: str,
    goal: str,
    *,
    actions: Sequence[str] | None,
    catalog_id: str | None,
    country: str | None,
    credential: Mapping[str, Any] | None,
    visibility: str | None,
    force: bool,
) -> Op[WireBuildRequest]:
    body = compact(
        {
            "website_url": website_url,
            "goal": goal,
            "actions": list(actions) if actions is not None else None,
            "catalog_id": catalog_id,
            "country": country,
            "credential": dict(credential) if credential is not None else None,
            "visibility": visibility,
            "force": force or None,
        }
    )
    return _build_request((yield Call("POST", "/wire/build-request", json=body)))


def _build_request(body: Any) -> WireBuildRequest:
    if isinstance(body, dict) and isinstance(body.get("build_request"), dict):
        body = body["build_request"]
    return WireBuildRequest.model_validate(body)


def wire_builds(status: str | None, page: int | None, limit: int | None) -> Op[list[WireBuildRequest]]:
    params = {"status": status, "page": page, "limit": limit}
    return (
        yield from _list(
            "/wire/build-requests",
            WireBuildRequest,
            "build_requests",
            "builds",
            "data",
            params=params,
        )
    )


def wire_get_build(build_id: str) -> Op[WireBuildRequest]:
    return _build_request((yield Call("GET", f"/wire/build-requests/{_seg(build_id)}")))


# Identity sources (1Password / Azure Key Vault). Returned as plain dicts: the
# shapes are provider-specific and mostly consumed by dashboards.

_SOURCES = "/wire/identity-sources"


def sources_providers() -> Op[Any]:
    return (yield from _call("GET", f"{_SOURCES}/providers"))


def sources_list() -> Op[list[dict[str, Any]]]:
    body = yield Call("GET", _SOURCES)
    return unwrap_list(body, "sources", "identity_sources", "data")


def sources_get(source_id: str) -> Op[Any]:
    return (yield from _call("GET", f"{_SOURCES}/{_seg(source_id)}"))


def sources_create(
    provider: str, display_name: str, auth_method: str | None, fields: Mapping[str, Any]
) -> Op[Any]:
    body = compact(
        {"provider": provider, "display_name": display_name, "auth_method": auth_method, **fields}
    )
    return (yield from _call("POST", _SOURCES, json=body))


def sources_update(
    source_id: str, display_name: str | None, auth_method: str | None, fields: Mapping[str, Any]
) -> Op[Any]:
    body = compact({"display_name": display_name, "auth_method": auth_method, **fields})
    return (yield from _call("PATCH", f"{_SOURCES}/{_seg(source_id)}", json=body))


def sources_verify(source_id: str) -> Op[Any]:
    return (yield from _call("POST", f"{_SOURCES}/{_seg(source_id)}/verify"))


def sources_delete(source_id: str, delete_identities: bool) -> Op[Any]:
    params = {"delete_identities": "true"} if delete_identities else None
    return (yield from _call("DELETE", f"{_SOURCES}/{_seg(source_id)}", params=params))


def sources_identities(source_id: str) -> Op[list[WireIdentity]]:
    return (
        yield from _list(f"{_SOURCES}/{_seg(source_id)}/identities", WireIdentity, "identities")
    )


def sources_containers(source_id: str) -> Op[list[dict[str, Any]]]:
    body = yield Call("GET", f"{_SOURCES}/{_seg(source_id)}/containers")
    return unwrap_list(body, "containers")


def sources_entries(source_id: str, container_id: str, domain: str | None) -> Op[list[dict[str, Any]]]:
    body = yield Call(
        "GET",
        f"{_SOURCES}/{_seg(source_id)}/containers/{_seg(container_id)}/entries",
        params={"domain": domain},
    )
    return unwrap_list(body, "entries")


# ─── Monitors ─────────────────────────────────────────────────────────────────

_MONITOR_FIELDS = {
    "scope": "scope",
    "watch_mode": "watchMode",
    "watch_format": "watchFormat",
    "output_schema": "outputSchema",
    "ai_mode": "aiMode",
    "ai_goal": "aiGoal",
    "use_browser": "useBrowser",
    "country": "country",
    "session_id": "sessionId",
    "is_active": "isActive",
    "expires_at": "expiresAt",
    "alert_webhook_url": "alertWebhookUrl",
    "alert_emails": "alertEmails",
    "max_pages": "maxPages",
    "max_depth": "maxDepth",
    "include_patterns": "includePatterns",
    "exclude_patterns": "excludePatterns",
    "wire_action_id": "wireActionId",
    "wire_catalog_slug": "wireCatalogSlug",
    "wire_credential_id": "wireCredentialId",
    "wire_params": "wireParams",
    "wire_watch_paths": "wireWatchPaths",
}


def monitor_body(url: str, interval_minutes: int, options: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(options) - set(_MONITOR_FIELDS)
    if unknown:
        raise TypeError(f"Unknown monitor option(s): {', '.join(sorted(unknown))}")
    body: dict[str, Any] = {"url": url, "intervalMinutes": interval_minutes}
    for key, value in options.items():
        if value is None:
            continue
        if key == "alert_emails" and not isinstance(value, str):
            value = ",".join(value)
        if key == "expires_at":
            value = _date(value)
        if isinstance(value, tuple):
            value = list(value)
        body[_MONITOR_FIELDS[key]] = value
    return body


def _monitor(path: str, method: str = "GET", json: Any = None) -> Op[Monitor]:
    body = yield Call(method, path, json=json)
    if isinstance(body, dict) and isinstance(body.get("monitor"), dict):
        body = body["monitor"]
    return Monitor.model_validate(body)


def monitors_create(body: dict[str, Any]) -> Op[Monitor]:
    return (yield from _monitor("/monitors", "POST", body))


def monitors_update(monitor_id: str, body: dict[str, Any]) -> Op[Monitor]:
    return (yield from _monitor(f"/monitors/{_seg(monitor_id)}", "PUT", body))


def monitors_list() -> Op[list[Monitor]]:
    return (yield from _list("/monitors", Monitor, "monitors"))


def monitors_get(monitor_id: str) -> Op[Monitor]:
    return (yield from _monitor(f"/monitors/{_seg(monitor_id)}"))


def monitors_delete(monitor_id: str) -> Op[None]:
    yield Call("DELETE", f"/monitors/{_seg(monitor_id)}")


def monitors_pause(monitor_id: str) -> Op[Monitor]:
    return (yield from _monitor(f"/monitors/{_seg(monitor_id)}/pause", "POST"))


def monitors_resume(monitor_id: str, expires_at: str | date | datetime | None) -> Op[Monitor]:
    body = {"expiresAt": _date(expires_at)} if expires_at is not None else None
    return (yield from _monitor(f"/monitors/{_seg(monitor_id)}/resume", "POST", body))


def monitors_set_expiry(monitor_id: str, expires_at: str | date | datetime | None) -> Op[Monitor]:
    body = {"expiresAt": _date(expires_at)}
    return (yield from _monitor(f"/monitors/{_seg(monitor_id)}/expiry", "POST", body))


def monitors_run_now(monitor_id: str) -> Op[MonitorRun]:
    body = yield Call("POST", f"/monitors/{_seg(monitor_id)}/run")
    return MonitorRun.model_validate(body)


def monitors_changes(monitor_id: str) -> Op[list[MonitorChange]]:
    return (yield from _list(f"/monitors/{_seg(monitor_id)}/changes", MonitorChange, "changes"))


def monitors_snapshots(monitor_id: str) -> Op[list[MonitorSnapshot]]:
    return (
        yield from _list(f"/monitors/{_seg(monitor_id)}/snapshots", MonitorSnapshot, "snapshots")
    )


def monitors_snapshot_content(monitor_id: str, snapshot_id: str) -> Op[SnapshotContent]:
    path = f"/monitors/{_seg(monitor_id)}/snapshots/{_seg(snapshot_id)}/content"
    return (yield from _get(path, SnapshotContent))


def monitors_content(monitor_id: str, content_hash: str) -> Op[SnapshotContent]:
    body = yield Call("GET", f"/monitors/{_seg(monitor_id)}/content", params={"hash": content_hash})
    return SnapshotContent.model_validate(body)


def monitors_runs(monitor_id: str) -> Op[list[dict[str, Any]]]:
    body = yield Call("GET", f"/monitors/{_seg(monitor_id)}/runs")
    return unwrap_list(body, "runs")


def monitors_pages(monitor_id: str) -> Op[list[dict[str, Any]]]:
    body = yield Call("GET", f"/monitors/{_seg(monitor_id)}/pages")
    return unwrap_list(body, "pages")


def monitors_remove_page(monitor_id: str, url: str) -> Op[None]:
    yield Call("DELETE", f"/monitors/{_seg(monitor_id)}/pages", params={"url": url})


def monitors_restore_page(monitor_id: str, url: str) -> Op[None]:
    yield Call("POST", f"/monitors/{_seg(monitor_id)}/pages/restore", params={"url": url})


def monitors_test_alert(monitor_id: str) -> Op[AlertTestResult]:
    body = yield Call("POST", f"/monitors/{_seg(monitor_id)}/test-alert")
    return AlertTestResult.model_validate(body)


def monitors_deliveries(monitor_id: str) -> Op[list[Delivery]]:
    return (yield from _list(f"/monitors/{_seg(monitor_id)}/deliveries", Delivery, "deliveries"))


def monitors_retry_delivery(monitor_id: str, delivery_id: str) -> Op[None]:
    yield Call("POST", f"/monitors/{_seg(monitor_id)}/deliveries/{_seg(delivery_id)}/retry")


# ─── AI Visibility ────────────────────────────────────────────────────────────


def _ai_search_terminal(body: Any) -> bool:
    return isinstance(body, dict) and body.get("status") in {"completed", "failed"}


def ai_visibility_search(
    cfg: ClientConfig,
    query: str,
    *,
    sources: Sequence[str] | None,
    country: str,
    wait: bool,
    poll_timeout: float | None,
) -> Op[AIVisibilitySearch]:
    body = compact(
        {
            "query": query,
            "sources": list(sources) if sources is not None else None,
            "country": country,
        }
    )
    submitted = yield Call("POST", "/ai-visibility/search", json=body)
    search_id = require_job_id(submitted)
    if not wait:
        return AIVisibilitySearch.model_validate({**submitted, "search_id": search_id, "query": query})
    result = yield from poll(
        cfg,
        f"/ai-visibility/search/{_seg(search_id)}",
        job_id=search_id,
        timeout=poll_timeout,
        is_terminal=_ai_search_terminal,
    )
    if result.get("status") == "failed":
        raise JobFailedError(
            "Every AI Visibility source failed", job_id=search_id, body=result
        )
    return AIVisibilitySearch.model_validate({"query": query, **result})


def ai_visibility_get(search_id: str) -> Op[AIVisibilitySearch]:
    return (yield from _get(f"/ai-visibility/search/{_seg(search_id)}", AIVisibilitySearch))


def ai_visibility_list() -> Op[list[AIVisibilitySearchSummary]]:
    return (yield from _list("/ai-visibility/searches", AIVisibilitySearchSummary, "searches"))


def ai_visibility_sources() -> Op[list[AIVisibilitySource]]:
    return (yield from _list("/ai-visibility/sources", AIVisibilitySource, "sources"))


def ai_visibility_retry(search_id: str, source: str) -> Op[AIVisibilitySourceResult]:
    body = yield Call(
        "POST", f"/ai-visibility/search/{_seg(search_id)}/retry", json={"source": source}
    )
    return AIVisibilitySourceResult.model_validate(body)


# ─── Webhooks ─────────────────────────────────────────────────────────────────


def webhooks_create(
    url: str, description: str | None, events: Sequence[str] | None
) -> Op[WebhookEndpoint]:
    body = compact(
        {
            "url": url,
            "description": description,
            "events": list(events) if events is not None else None,
        }
    )
    result = yield Call("POST", "/webhooks", json=body)
    return WebhookEndpoint.model_validate(result)


def webhooks_list() -> Op[list[WebhookEndpoint]]:
    return (yield from _list("/webhooks", WebhookEndpoint, "endpoints"))


def webhooks_update(
    endpoint_id: str,
    *,
    url: str | None,
    description: str | None,
    events: Sequence[str] | None,
    is_active: bool | None,
) -> Op[WebhookEndpoint]:
    body = compact(
        {
            "url": url,
            "description": description,
            "events": list(events) if events is not None else None,
            "isActive": is_active,
        }
    )
    result = yield Call("PATCH", f"/webhooks/{_seg(endpoint_id)}", json=body)
    return WebhookEndpoint.model_validate(result)


def webhooks_delete(endpoint_id: str) -> Op[None]:
    yield Call("DELETE", f"/webhooks/{_seg(endpoint_id)}")


def webhooks_test(endpoint_id: str) -> Op[WebhookTestResult]:
    result = yield Call("POST", f"/webhooks/{_seg(endpoint_id)}/test")
    return WebhookTestResult.model_validate(result)


def webhooks_deliveries(
    *,
    endpoint_id: str | None,
    event: str | None,
    status: str | None,
    job_id: str | None,
    limit: int | None,
) -> Op[list[Delivery]]:
    params = {
        "endpointId": endpoint_id,
        "event": event,
        "status": status,
        "jobId": job_id,
        "limit": limit,
    }
    return (yield from _list("/webhooks/deliveries", Delivery, "deliveries", params=params))


def webhooks_resend(delivery_id: str) -> Op[None]:
    yield Call("POST", f"/webhooks/deliveries/{_seg(delivery_id)}/resend")


def _secret(body: Any) -> str:
    return str(body.get("secret", "")) if isinstance(body, dict) else ""


def webhooks_signing_secret() -> Op[str]:
    return _secret((yield Call("GET", "/webhooks/signing-secret")))


def webhooks_rotate_signing_secret() -> Op[str]:
    return _secret((yield Call("POST", "/webhooks/signing-secret/rotate")))


def webhooks_events() -> Op[list[str]]:
    body = yield Call("GET", "/webhooks/events")
    return [str(e) for e in unwrap_list(body, "events")]


# ─── Browser sessions & recordings ────────────────────────────────────────────


def sessions_list(domain: str | None) -> Op[list[BrowserSession]]:
    return (yield from _list("/sessions", BrowserSession, "sessions", params={"domain": domain}))


def sessions_create(
    website_url: str, name: str, record: bool, session_type: str
) -> Op[BrowserSessionHandle]:
    body = {
        "websiteUrl": website_url,
        "name": name,
        "record": record,
        "sessionType": session_type,
    }
    result = yield Call("POST", "/sessions/manual-start", json=body)
    return BrowserSessionHandle.model_validate(result)


def sessions_save(browser_instance_id: str) -> Op[BrowserSession]:
    result = yield Call(
        "POST", "/sessions/manual-save", json={"browserInstanceId": browser_instance_id}
    )
    return BrowserSession.model_validate(result)


def sessions_update(session_id: str, name: str) -> Op[BrowserSession]:
    result = yield Call("PATCH", f"/sessions/{_seg(session_id)}", json={"name": name})
    return BrowserSession.model_validate(result)


def sessions_delete(session_id: str) -> Op[None]:
    yield Call("DELETE", f"/sessions/{_seg(session_id)}")


def recordings_list() -> Op[list[Recording]]:
    return (yield from _list("/recordings", Recording, "recordings"))


def recordings_get(recording_id: str) -> Op[Recording]:
    return (yield from _get(f"/recordings/{_seg(recording_id)}", Recording))

