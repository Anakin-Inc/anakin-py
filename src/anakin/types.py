"""Typed request helpers (parameter literals and TypedDicts) for the Anakin SDK."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Literal

from typing_extensions import NotRequired, TypedDict

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

AuthMode = Literal["none", "optional", "required"]


class BrowserAction(TypedDict):
    """
    One step of `scrape(actions=[...])`, run in a real browser before capture.

    `type` is one of: wait (milliseconds), wait_for (selector, milliseconds?),
    click (selector), scroll (direction?, selector?), write (text), press (key).
    Max 15 actions; +1 credit; implies use_browser=True.
    """

    type: Literal["wait", "wait_for", "click", "scroll", "write", "press"]
    selector: NotRequired[str]
    milliseconds: NotRequired[int]
    direction: NotRequired[Literal["up", "down"]]
    text: NotRequired[str]
    key: NotRequired[str]


class MonitorOptions(TypedDict, total=False):
    """
    Optional settings for `monitors.create` / `monitors.update`.

    See https://anakin.io/docs/api-reference/monitoring/create-monitor.
    """

    scope: Literal["page", "site", "wire"]
    watch_mode: Literal["full_page", "specific_data"]
    watch_format: Literal["markdown", "html", "cleaned_html"]
    output_schema: Mapping[str, Any]
    ai_mode: bool
    ai_goal: str
    use_browser: bool
    country: str
    session_id: str
    is_active: bool
    expires_at: str | date | datetime
    alert_webhook_url: str
    alert_emails: str | Sequence[str]
    # site scope
    max_pages: int
    max_depth: int
    include_patterns: Sequence[str]
    exclude_patterns: Sequence[str]
    # wire scope
    wire_action_id: str
    wire_catalog_slug: str
    wire_credential_id: str
    wire_params: Mapping[str, Any]
    wire_watch_paths: Sequence[str]
