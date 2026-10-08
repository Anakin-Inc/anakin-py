"""
Unit tests for search, agentic_search, wire, the sessions namespace, and
countries().

All HTTP traffic mocked via respx — no real network.
"""

from __future__ import annotations

import json as _json

import httpx
import pytest
import respx

from anakin import (
    Anakin,
    JobFailedError,
    WireAuthRequiredError,
)

BASE = "https://api.anakin.io/v1"


def _make_client() -> Anakin:
    return Anakin(
        api_key="ak-test",
        base_url=BASE,
        poll_interval=0.001,
        poll_max_interval=0.01,
        poll_timeout=2.0,
    )


# ─── search (sync) ───────────────────────────────────────────────────────────


@respx.mock
def test_search_sync() -> None:
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "s1",
                "results": [
                    {
                        "url": "https://x.com/a",
                        "title": "A",
                        "snippet": "snippet a",
                    },
                    {
                        "url": "https://x.com/b",
                        "title": "B",
                        "snippet": "snippet b",
                    },
                ],
            },
        )
    )
    client = _make_client()
    result = client.search("test query", limit=2)
    assert result.id == "s1"
    assert len(result.results) == 2
    assert result.results[0].title == "A"


# ─── agentic_search ──────────────────────────────────────────────────────────


@respx.mock
def test_agentic_search_with_schema() -> None:
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(_json.loads(request.content))
        return httpx.Response(
            202,
            json={"job_id": "as1", "status": "pending", "message": "queued"},
        )

    respx.post(f"{BASE}/agentic-search").mock(side_effect=_capture)
    respx.get(f"{BASE}/agentic-search/as1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "as1",
                "status": "completed",
                "jobType": "agentic_search",
                "generatedJson": {
                    "summary": "summary text",
                    "structured_data": {"items": [{"a": 1}]},
                    "data_schema": {"description": "test"},
                },
                "durationMs": 5000,
            },
        )
    )
    client = _make_client()
    result = client.agentic_search(
        "find AI companies",
        schema={"type": "object"},
    )
    assert result.id == "as1"
    assert result.status == "completed"
    assert result.generated_json is not None
    assert result.generated_json.summary == "summary text"
    assert captured["prompt"] == "find AI companies"
    assert captured["schema"] == {"type": "object"}
    assert captured["useBrowser"] is True


# ─── wire ─────────────────────────────────────────────────────────


@respx.mock
def test_wire_happy_path() -> None:
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(_json.loads(request.content))
        return httpx.Response(
            202,
            json={
                "status": "processing",
                "job_id": "w1",
                "poll_url": "/v1/wire/jobs/w1",
            },
        )

    respx.post(f"{BASE}/wire/task").mock(side_effect=_capture)
    # Note: wire polls /v1/wire/jobs/:id, not /v1/wire/task/:id
    respx.get(f"{BASE}/wire/jobs/w1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "completed",
                "data": {"name": "Jane Doe", "headline": "Engineer"},
                "credits_used": 2,
                "execution_ms": 8420,
            },
        )
    )

    client = _make_client()
    result = client.wire(
        "li_profile_scrape",
        {"profile_url": "https://www.linkedin.com/in/example"},
    )
    assert result.status == "completed"
    assert result.data is not None
    assert result.data["name"] == "Jane Doe"
    assert result.credits_used == 2
    assert captured["action_id"] == "li_profile_scrape"
    assert captured["params"]["profile_url"] == "https://www.linkedin.com/in/example"


@respx.mock
def test_wire_auth_required_raises_special_error() -> None:
    respx.post(f"{BASE}/wire/task").mock(
        return_value=httpx.Response(
            401,
            json={
                "status": "error",
                "error": {
                    "code": "AUTH_REQUIRED",
                    "message": "This action requires a LinkedIn connection.",
                    "connect_url": "/products/wire/linkedin/connect",
                },
            },
        )
    )
    client = _make_client()
    with pytest.raises(WireAuthRequiredError) as ei:
        client.wire("li_profile_scrape", {"profile_url": "x"})
    assert ei.value.connect_url == "https://anakin.io/products/wire/linkedin/connect"


@respx.mock
def test_wire_failed_job_raises() -> None:
    respx.post(f"{BASE}/wire/task").mock(
        return_value=httpx.Response(
            202, json={"status": "processing", "job_id": "wf1"}
        )
    )
    respx.get(f"{BASE}/wire/jobs/wf1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "failed",
                "error": {"code": "EXECUTION_FAILED", "message": "page down"},
                "credits_used": 0,
            },
        )
    )
    client = _make_client()
    with pytest.raises(JobFailedError):
        client.wire("li_profile_scrape", {"profile_url": "x"})


# ─── sessions sub-namespace ──────────────────────────────────────────────────


@respx.mock
def test_sessions_list() -> None:
    respx.get(f"{BASE}/sessions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "sessionId": "s-1",
                    "name": "linkedin",
                    "websiteUrl": "https://www.linkedin.com",
                    "websiteDomain": "linkedin.com",
                    "isActive": True,
                }
            ],
        )
    )
    client = _make_client()
    sessions = client.sessions.list()
    assert len(sessions) == 1
    assert sessions[0].id == "s-1"


@respx.mock
def test_sessions_create() -> None:
    respx.post(f"{BASE}/sessions/manual-start").mock(
        return_value=httpx.Response(
            201,
            json={
                "sessionId": "s-new",
                "novncUrl": "https://novnc.example.com/?token=...",
                "accessToken": "tok",
                "expiresIn": 3600,
                "wsUrl": "wss://...",
            },
        )
    )
    client = _make_client()
    handle = client.sessions.create(
        website_url="https://www.linkedin.com",
        name="li-test",
    )
    assert handle.session_id == "s-new"
    assert handle.novnc_url is not None


@respx.mock
def test_sessions_update_and_delete() -> None:
    respx.patch(f"{BASE}/sessions/s-1").mock(
        return_value=httpx.Response(
            200, json={"sessionId": "s-1", "name": "renamed"}
        )
    )
    respx.delete(f"{BASE}/sessions/s-1").mock(return_value=httpx.Response(204))
    client = _make_client()
    updated = client.sessions.update("s-1", name="renamed")
    assert updated.name == "renamed"
    client.sessions.delete("s-1")  # no return; just shouldn't raise


# ─── countries (static, no network call) ─────────────────────────────────────


def test_countries_static_list_no_network() -> None:
    """countries() returns a bundled static list — no network round-trip."""
    client = _make_client()
    countries = client.countries()
    # Should be 200+ countries based on the seeded list
    assert len(countries) > 200
    # Common countries must be present
    codes = {c.code for c in countries}
    assert {"us", "gb", "in", "de"}.issubset(codes)


def test_supported_country_codes_constant() -> None:
    from anakin import SUPPORTED_COUNTRIES, SUPPORTED_COUNTRY_CODES

    assert "us" in SUPPORTED_COUNTRY_CODES
    assert "gb" in SUPPORTED_COUNTRY_CODES
    assert "xx" not in SUPPORTED_COUNTRY_CODES
    # Constants should agree
    assert {c.code for c in SUPPORTED_COUNTRIES} == SUPPORTED_COUNTRY_CODES


# ─── unwrap_list null tolerance ──────────────────────────────────────────────


@respx.mock
def test_sessions_list_null_response() -> None:
    """Anakin returns {"sessions": null} when there are no sessions."""
    respx.get(f"{BASE}/sessions").mock(
        return_value=httpx.Response(200, json={"sessions": None})
    )
    client = _make_client()
    assert client.sessions.list() == []


