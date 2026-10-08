"""
Response models for the Anakin SDK.

Pydantic v2. The wire format (camelCase for scraping/monitoring endpoints,
snake_case for Wire / AI Visibility) is mapped to snake_case attributes.

Models are deliberately tolerant:
- unknown fields are kept (`extra="allow"`, readable via `.model_extra`) so a
  new API field never crashes your code and is still reachable;
- `status` fields are plain strings, not closed enums, so a new status value
  doesn't raise a validation error.

Shapes follow https://anakin.io/docs/api-reference.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field

# Documented values: pending, queued (agentic search), processing, completed, failed.
JobStatus = str


class _AnakinModel(BaseModel):
    """Shared base: accept snake_case or the wire alias, keep unknown fields."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


def _alias(*names: str) -> AliasChoices:
    return AliasChoices(*names)


# ─── Trial (keyless / Zero Touch) ─────────────────────────────────────────────


class TrialInfo(_AnakinModel):
    """Free-allowance info returned on keyless (Zero Touch) calls."""

    remaining_credits: int | None = None
    signup_url: str | None = None
    message: str | None = None


# ─── Document (scrape) ────────────────────────────────────────────────────────


class Link(_AnakinModel):
    href: str
    text: str | None = None


class Image(_AnakinModel):
    src: str
    alt: str | None = None


def _coerce_links(value: Any) -> Any:
    # The API returns [{href, text}]; tolerate bare strings too.
    if isinstance(value, list):
        return [{"href": v} if isinstance(v, str) else v for v in value]
    return value


def _coerce_images(value: Any) -> Any:
    if isinstance(value, list):
        return [{"src": v} if isinstance(v, str) else v for v in value]
    return value


class Document(_AnakinModel):
    """A scraped page. Only the formats you requested are populated."""

    id: str
    url: str = ""
    status: JobStatus
    job_type: str | None = Field(None, alias="jobType")
    country: str | None = None
    cached: bool = False
    duration_ms: int = Field(0, alias="durationMs")
    created_at: datetime | None = Field(None, alias="createdAt")
    completed_at: datetime | None = Field(None, alias="completedAt")

    markdown: str | None = None
    html: str | None = None
    cleaned_html: str | None = Field(None, alias="cleanedHtml")
    links: Annotated[list[Link] | None, BeforeValidator(_coerce_links)] = None
    images: Annotated[list[Image] | None, BeforeValidator(_coerce_images)] = None
    summary: str | None = None
    generated_json: Any = Field(None, alias="generatedJson")
    screenshot_url: str | None = Field(None, alias="screenshotUrl")
    full_page_screenshot_url: str | None = Field(None, alias="fullPageScreenshotUrl")

    error: str | None = None
    trial: TrialInfo | None = None


class BatchScrapeItem(_AnakinModel):
    """One URL's outcome inside a batch scrape."""

    index: int = 0
    id: str | None = None
    url: str
    status: JobStatus
    cached: bool = False
    duration_ms: int = Field(0, alias="durationMs")
    markdown: str | None = None
    html: str | None = None
    cleaned_html: str | None = Field(None, alias="cleanedHtml")
    generated_json: Any = Field(None, alias="generatedJson")
    error: str | None = None


class BatchScrapeResult(_AnakinModel):
    """
    A batch scrape (up to 10 URLs). The batch is `completed` if any URL
    finished; check each item's `status`.
    """

    id: str
    status: JobStatus
    urls: list[str] = Field(default_factory=list)
    country: str | None = None
    results: list[BatchScrapeItem] = Field(default_factory=list)
    created_at: datetime | None = Field(None, alias="createdAt")
    completed_at: datetime | None = Field(None, alias="completedAt")
    duration_ms: int = Field(0, alias="durationMs")
    error: str | None = None


# ─── MapResult ────────────────────────────────────────────────────────────────


class MapResult(_AnakinModel):
    id: str
    url: str = ""
    status: JobStatus = "completed"
    links: list[str] = Field(default_factory=list)
    total_links: int = Field(0, alias="totalLinks")
    external_links: list[str] = Field(default_factory=list, alias="externalLinks")
    total_external_links: int = Field(0, alias="totalExternalLinks")
    created_at: datetime | None = Field(None, alias="createdAt")
    completed_at: datetime | None = Field(None, alias="completedAt")
    duration_ms: int = Field(0, alias="durationMs")
    error: str | None = None


# ─── CrawlResult ──────────────────────────────────────────────────────────────


class CrawlPage(_AnakinModel):
    url: str
    status: JobStatus
    markdown: str | None = None
    html: str | None = None
    duration_ms: int = Field(0, alias="durationMs")
    error: str | None = None


class CrawlResult(_AnakinModel):
    id: str
    url: str = ""
    status: JobStatus = "completed"
    total_pages: int = Field(0, alias="totalPages")
    completed_pages: int = Field(0, alias="completedPages")
    pages: list[CrawlPage] = Field(default_factory=list, alias="results")
    created_at: datetime | None = Field(None, alias="createdAt")
    completed_at: datetime | None = Field(None, alias="completedAt")
    duration_ms: int = Field(0, alias="durationMs")
    error: str | None = None


# ─── SearchResult (sync) ──────────────────────────────────────────────────────


class SearchResultItem(_AnakinModel):
    url: str
    title: str | None = None
    snippet: str | None = None
    date: str | None = None
    last_updated: str | None = None


class SearchResult(_AnakinModel):
    id: str
    results: list[SearchResultItem] = Field(default_factory=list)


# ─── AgenticSearchResult ──────────────────────────────────────────────────────


class AgenticSearchData(_AnakinModel):
    """The `generatedJson` payload from an agentic-search job."""

    summary: str | None = None
    structured_data: Any = None
    data_schema: dict[str, Any] | None = None


class AgenticSearchResult(_AnakinModel):
    id: str = Field(validation_alias=_alias("id", "job_id"))
    status: JobStatus
    job_type: str = Field("agentic_search", alias="jobType")
    generated_json: AgenticSearchData | None = Field(None, alias="generatedJson")
    cached: bool = False
    created_at: datetime | None = Field(None, validation_alias=_alias("createdAt", "created_at"))
    completed_at: datetime | None = Field(None, alias="completedAt")
    duration_ms: int = Field(0, alias="durationMs")
    error: str | None = None


# ─── Wire: jobs ───────────────────────────────────────────────────────────────


class WireError(_AnakinModel):
    code: str | None = None
    message: str = ""


class WireFile(_AnakinModel):
    """A file produced by a Wire job. Fetch bytes with `client.wire.download(job_id, file=name)`."""

    name: str
    content_type: str | None = None
    size_bytes: int | None = None


class WireResult(_AnakinModel):
    """Result of a Wire action run (`client.wire.run` / `client.wire(...)`)."""

    job_id: str | None = None
    status: JobStatus
    data: Any = None
    files: list[WireFile] = Field(default_factory=list)
    credits_used: int = 0
    execution_ms: int = 0
    retry_after_ms: int | None = None
    error: WireError | None = None
    trial: TrialInfo | None = None


# ─── Wire: catalog & discovery ────────────────────────────────────────────────


class WireCatalog(_AnakinModel):
    """A website in the Wire catalog."""

    id: str
    slug: str
    name: str
    url: str | None = None
    domain: str | None = None
    category: str | None = None
    description: str | None = None
    logo_url: str | None = None
    auth_required: bool = False
    auth_type: str | None = None
    auth_types: list[str] = Field(default_factory=list)
    auth_login_url: str | None = None
    supported_sources: list[str] = Field(default_factory=list)
    status: str | None = None
    action_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WireAction(_AnakinModel):
    """One action inside a catalog (from `wire.catalog(slug)`)."""

    action_id: str
    id: str | None = None
    catalog_id: str | None = None
    name: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    type: str | None = None  # "read" | "write"
    mode: str | None = None  # "async" | "sync"
    auth_mode: str | None = None  # "none" | "optional" | "required"
    auth_required: bool = False
    parameters: Any = None
    credits_per_call: int | None = None
    status: str | None = None
    owner_user_id: str | None = None


class WireCatalogDetail(_AnakinModel):
    catalog: WireCatalog
    actions: list[WireAction] = Field(default_factory=list)
    login_input_schema: list[dict[str, Any]] = Field(default_factory=list)


class WireActionMatch(_AnakinModel):
    """A candidate action returned by `wire.discover(...)`."""

    action_id: str
    catalog_slug: str | None = Field(None, validation_alias=_alias("catalog_slug", "catalog"))
    catalog_name: str | None = None
    name: str | None = None
    description: str | None = None
    mode: str | None = None
    auth_mode: str | None = None
    auth_required: bool = False
    auth_satisfied: bool | None = None
    connected: bool | None = None
    params: Any = None
    credits: int | None = None


# ─── Wire: identities & login ─────────────────────────────────────────────────


class WireCredential(_AnakinModel):
    id: str
    identity_id: str | None = None
    credential_type: str | None = None
    status: str | None = None  # "active" | "expired"
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_id: str | None = None
    source_ref: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WireIdentity(_AnakinModel):
    id: str
    user_id: str | None = None
    catalog_id: str | None = None
    name: str | None = None
    is_default: bool = False
    credentials: list[WireCredential] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WireLoginResult(_AnakinModel):
    """Successful `wire.login(...)`. Pass `credential_id` to `wire.run(...)`."""

    status: str
    identity_id: str
    identity_name: str | None = None
    credential_id: str
    catalog_id: str | None = None
    catalog_slug: str | None = None
    expires_at: datetime | None = None


class WireBuildRequest(_AnakinModel):
    """A request to build a new Wire action (`wire.build(...)`)."""

    id: str
    status: str  # pending -> processing -> success | failed
    website_url: str | None = None
    domain: str | None = None
    goal: str | None = None
    visibility: str | None = None
    credits_charged: int | None = None
    action_id: str | None = None
    catalog_slug: str | None = None
    skipped: list[Any] = Field(default_factory=list)
    error: str | None = None
    error_type: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ─── Monitors ─────────────────────────────────────────────────────────────────


class Monitor(_AnakinModel):
    id: str
    url: str
    scope: str = "page"
    watch_mode: str | None = Field(None, alias="watchMode")
    watch_format: str | None = Field(None, alias="watchFormat")
    interval_minutes: int | None = Field(None, alias="intervalMinutes")
    is_active: bool = Field(True, alias="isActive")
    use_browser: bool = Field(False, alias="useBrowser")
    country: str | None = None
    session_id: str | None = Field(None, alias="sessionId")
    session_expired: bool = Field(False, alias="sessionExpired")
    output_schema: dict[str, Any] | None = Field(None, alias="outputSchema")
    ai_mode: bool = Field(False, alias="aiMode")
    ai_goal: str | None = Field(None, alias="aiGoal")
    max_pages: int | None = Field(None, alias="maxPages")
    max_depth: int | None = Field(None, alias="maxDepth")
    include_patterns: list[str] = Field(default_factory=list, alias="includePatterns")
    exclude_patterns: list[str] = Field(default_factory=list, alias="excludePatterns")
    excluded_urls: list[str] = Field(default_factory=list, alias="excludedUrls")
    wire_action_id: str | None = Field(None, alias="wireActionId")
    wire_catalog_slug: str | None = Field(None, alias="wireCatalogSlug")
    wire_credential_id: str | None = Field(None, alias="wireCredentialId")
    wire_params: dict[str, Any] | None = Field(None, alias="wireParams")
    wire_watch_paths: list[str] | None = Field(None, alias="wireWatchPaths")
    expires_at: datetime | None = Field(None, alias="expiresAt")
    expired: bool = False
    next_run_at: datetime | None = Field(None, alias="nextRunAt")
    last_checked_at: datetime | None = Field(None, alias="lastCheckedAt")
    credit_cost_per_run: int | None = Field(None, alias="creditCostPerRun")
    alert_webhook_url: str | None = Field(None, alias="alertWebhookUrl")
    alert_webhook_secret: str | None = Field(None, alias="alertWebhookSecret")
    alert_emails: str | None = Field(None, alias="alertEmails")
    last_alerted_at: datetime | None = Field(None, alias="lastAlertedAt")
    created_at: datetime | None = Field(None, alias="createdAt")
    updated_at: datetime | None = Field(None, alias="updatedAt")


class MonitorChange(_AnakinModel):
    id: str
    monitor_id: str | None = Field(None, alias="monitorId")
    snapshot_id: str | None = Field(None, alias="snapshotId")
    changed_at: datetime | None = Field(None, alias="changedAt")
    summary: str | None = None
    diff: dict[str, Any] = Field(default_factory=dict, alias="diffJson")
    created_at: datetime | None = Field(None, alias="createdAt")


class MonitorSnapshot(_AnakinModel):
    id: str
    monitor_id: str | None = Field(None, alias="monitorId")
    captured_at: datetime | None = Field(None, alias="capturedAt")
    content_hash: str | None = Field(None, alias="contentHash")
    extracted_data: Any = Field(None, alias="extractedData")
    created_at: datetime | None = Field(None, alias="createdAt")


class SnapshotContent(_AnakinModel):
    available: bool = False
    content: str = ""
    captured_at: datetime | None = Field(None, alias="capturedAt")
    content_hash: str | None = Field(None, alias="contentHash")


class MonitorRun(_AnakinModel):
    """Result of `monitors.run_now(...)`. `job_id` is absent for Wire monitors."""

    success: bool = True
    job_id: str | None = Field(None, alias="jobId")
    message: str | None = None


class AlertTestResult(_AnakinModel):
    success: bool = False
    status: int | None = None
    message: str | None = None


class Delivery(_AnakinModel):
    """One webhook / email delivery attempt (monitor alerts or webhook endpoints)."""

    id: str
    monitor_id: str | None = Field(None, alias="monitorId")
    endpoint_id: str | None = Field(None, alias="endpointId")
    change_id: str | None = Field(None, alias="changeId")
    job_id: str | None = Field(None, alias="jobId")
    event: str | None = None
    channel: str | None = None
    url: str | None = None
    status: str | None = None  # pending | success | failed | exhausted
    http_status: int | None = Field(None, alias="httpStatus")
    attempts: int = 0
    error: str | None = None
    next_attempt_at: datetime | None = Field(None, alias="nextAttemptAt")
    created_at: datetime | None = Field(None, alias="createdAt")


# ─── AI Visibility ────────────────────────────────────────────────────────────


class AIVisibilitySource(_AnakinModel):
    slug: str
    label: str | None = None


class AIVisibilitySourceResult(_AnakinModel):
    source: str
    status: str  # completed | failed | timed_out
    summary: str | None = None
    full_content: str | None = None
    latency_ms: int | None = None
    verdict: str | None = None  # consensus | outlier
    credits_used: int = 0
    error: str | None = None


class AIVisibilitySearch(_AnakinModel):
    search_id: str
    status: str  # running -> completed | failed
    query: str | None = None
    country: str | None = None
    synthesis: str | None = None
    results: list[AIVisibilitySourceResult] = Field(default_factory=list)


class AIVisibilitySearchSummary(_AnakinModel):
    """An entry from `ai_visibility.list()` (your 20 most recent runs)."""

    search_id: str
    query: str | None = None
    status: str
    created_at: str | None = None
    credits_used: int = 0
    sources: list[dict[str, Any]] = Field(default_factory=list)


# ─── Webhooks ─────────────────────────────────────────────────────────────────


class WebhookEndpoint(_AnakinModel):
    id: str
    url: str
    description: str | None = None
    events: list[str] = Field(default_factory=list)
    is_active: bool = Field(True, alias="isActive")
    secret: str | None = None  # only returned on create
    created_at: datetime | None = Field(None, alias="createdAt")


class WebhookTestResult(_AnakinModel):
    delivery_id: str | None = Field(None, alias="deliveryId")
    http_status: int | None = Field(None, alias="httpStatus")
    success: bool = False


# ─── Browser sessions & recordings ────────────────────────────────────────────


class BrowserSession(_AnakinModel):
    id: str = Field(..., validation_alias=_alias("sessionId", "id"))
    name: str | None = None
    website_url: str | None = Field(None, alias="websiteUrl")
    website_domain: str | None = Field(None, alias="websiteDomain")
    is_active: bool = Field(True, alias="isActive")
    created_at: datetime | None = Field(None, alias="createdAt")
    last_used_at: datetime | None = Field(None, alias="lastUsedAt")
    expires_at: datetime | None = Field(None, alias="expiresAt")
    cookie_count: int | None = Field(None, alias="cookieCount")
    storage_item_count: int | None = Field(None, alias="storageItemCount")


class BrowserSessionHandle(_AnakinModel):
    """Returned by sessions.create: contains the noVNC URL for interactive setup."""

    session_id: str = Field(..., alias="sessionId")
    novnc_url: str | None = Field(None, alias="novncUrl")
    access_token: str | None = Field(None, alias="accessToken")
    expires_in: int | None = Field(None, alias="expiresIn")
    ws_url: str | None = Field(None, alias="wsUrl")


class Recording(_AnakinModel):
    """A Browser API session recording (WebM). `video_url` is presigned for 1 hour."""

    id: str
    conn_id: str | None = Field(None, alias="connId")
    duration: float | None = None
    file_size: int | None = Field(None, alias="fileSize")
    status: str | None = None
    video_url: str | None = Field(None, alias="videoUrl")
    created_at: datetime | None = Field(None, alias="createdAt")


class Country(_AnakinModel):
    code: str
    name: str | None = None
