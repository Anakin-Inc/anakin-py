"""
Response models for Anakin SDK.

Pydantic v2. Wire format (camelCase from API) is mapped to snake_case
field names via `populate_by_name` and per-field aliases.

Shape source: docs/SDK_API_CONTRACT.md, section 5.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["pending", "processing", "completed", "failed"]
TerminalStatus = Literal["completed", "failed"]


class _AnakinModel(BaseModel):
    """Shared base — accept either snake_case or camelCase from the wire."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",  # tolerate new fields on the API side without crashing
    )


# ─── Document (scrape, scrape_batch[i], web_scrape) ────────────────────────────


class Document(_AnakinModel):
    id: str
    url: str
    status: TerminalStatus
    cached: bool = False
    duration_ms: int = Field(0, alias="durationMs")
    created_at: datetime | None = Field(None, alias="createdAt")
    completed_at: datetime | None = Field(None, alias="completedAt")

    # Content (only the formats requested are populated)
    markdown: str | None = None
    html: str | None = None
    cleaned_html: str | None = Field(None, alias="cleanedHtml")
    links: list[str] | None = None
    images: list[str] | None = None
    summary: str | None = None
    generated_json: dict[str, Any] | None = Field(None, alias="generatedJson")
    screenshot_url: str | None = Field(None, alias="screenshotUrl")
    full_page_screenshot_url: str | None = Field(None, alias="fullPageScreenshotUrl")

    # On failure
    error: str | None = None


# ─── MapResult ────────────────────────────────────────────────────────────────


class MapResult(_AnakinModel):
    id: str
    url: str
    links: list[str] = Field(default_factory=list)
    total_links: int = Field(0, alias="totalLinks")
    external_links: list[str] = Field(default_factory=list, alias="externalLinks")
    total_external_links: int = Field(0, alias="totalExternalLinks")
    duration_ms: int = Field(0, alias="durationMs")


# ─── CrawlResult ──────────────────────────────────────────────────────────────


class CrawlPage(_AnakinModel):
    url: str
    status: TerminalStatus
    markdown: str | None = None
    html: str | None = None
    duration_ms: int = Field(0, alias="durationMs")
    error: str | None = None


class CrawlResult(_AnakinModel):
    id: str
    url: str
    total_pages: int = Field(0, alias="totalPages")
    completed_pages: int = Field(0, alias="completedPages")
    pages: list[CrawlPage] = Field(default_factory=list, alias="results")
    duration_ms: int = Field(0, alias="durationMs")


# ─── WireResult (Holocron task) ───────────────────────────────────────────────


class WireError(_AnakinModel):
    code: str
    message: str


class WireResult(_AnakinModel):
    job_id: str
    status: TerminalStatus
    data: dict[str, Any] | None = None
    credits_used: int = 0
    execution_ms: int = 0
    error: WireError | None = None
