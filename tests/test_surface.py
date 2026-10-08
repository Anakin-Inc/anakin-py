"""
Unit tests for the v0.2 surface: batch scrape, keyless (Zero Touch) mode,
non-blocking jobs, the Wire namespace, monitors, AI visibility, webhooks,
Browser API helpers, and the hardened HTTP/error layer.

All HTTP traffic mocked via respx: no real network.
"""

from __future__ import annotations

import json as _json
from typing import Any

import httpx
import pytest
import respx

from anakin import (
    Anakin,
    AnakinError,
    AnakinPermissionError,
    ConfigurationError,
    ConflictError,
    InsufficientCreditsError,
    InvalidRequestError,
    JobFailedError,
    JobTimeoutError,
    RateLimitError,
    UnprocessableEntityError,
    WireAuthExpiredError,
    WireLoginError,
)

BASE = "https://api.anakin.io/v1"


def _client(**overrides: Any) -> Anakin:
    opts: dict[str, Any] = {
        "api_key": "ak-test",
        "base_url": BASE,
        "poll_interval": 0.001,
        "poll_max_interval": 0.01,
        "poll_timeout": 2.0,
    }
    opts.update(overrides)
    return Anakin(**opts)


def _body(request: httpx.Request) -> Any:
    return _json.loads(request.content)


# ─── scrape: models, formats, options ─────────────────────────────────────────


@respx.mock
def test_scrape_links_and_images_are_objects() -> None:
    """The API returns links as {href, text} and images as {src, alt}."""
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(202, json={"jobId": "j", "status": "pending"})
    )
    respx.get(f"{BASE}/url-scraper/j").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "j",
                "status": "completed",
                "url": "https://e.com",
                "links": [{"href": "https://e.com/about", "text": "About"}, "https://e.com/x"],
                "images": [{"src": "https://e.com/logo.png", "alt": "Logo"}],
                "generatedJson": {"data": {"price": 1}},
                "brandNewField": 42,
            },
        )
    )
    doc = _client().scrape("https://e.com", formats=["links", "images"])
    assert doc.links is not None and doc.links[0].href == "https://e.com/about"
    assert doc.links[0].text == "About"
    assert doc.links[1].href == "https://e.com/x"  # bare strings tolerated
    assert doc.images is not None and doc.images[0].alt == "Logo"
    assert doc.generated_json == {"data": {"price": 1}}
    assert doc.model_extra == {"brandNewField": 42}  # unknown fields kept, no crash


@respx.mock
def test_scrape_sends_new_options() -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(_body(request))
        return httpx.Response(202, json={"jobId": "j", "status": "pending"})

    respx.post(f"{BASE}/url-scraper").mock(side_effect=_capture)
    respx.get(f"{BASE}/url-scraper/j").mock(
        return_value=httpx.Response(200, json={"id": "j", "status": "completed"})
    )
    doc = _client().scrape(
        "https://e.com",
        output_schema={"type": "object"},
        actions=[{"type": "click", "selector": "button.more"}],
        webhook_url="https://hooks.example.com/a",
        session_name="my-login",
    )
    assert captured["outputSchema"] == {"type": "object"}
    assert captured["actions"] == [{"type": "click", "selector": "button.more"}]
    assert captured["webhook_url"] == "https://hooks.example.com/a"
    assert captured["sessionName"] == "my-login"
    assert "sessionId" not in captured  # unset optionals are not sent
    assert doc.url == "https://e.com"  # filled from the request when the API omits it


@respx.mock
def test_scrape_wait_false_returns_pending_then_get() -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(202, json={"jobId": "j9", "status": "pending"})
    )
    poll = respx.get(f"{BASE}/url-scraper/j9").mock(
        return_value=httpx.Response(
            200, json={"id": "j9", "status": "completed", "markdown": "# hi"}
        )
    )
    client = _client()
    pending = client.scrape("https://e.com", wait=False)
    assert pending.id == "j9"
    assert pending.status == "pending"
    assert not poll.called
    assert client.get_scrape("j9").markdown == "# hi"


@respx.mock
def test_scrape_batch() -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(_body(request))
        return httpx.Response(202, json={"jobId": "b1", "status": "pending"})

    respx.post(f"{BASE}/url-scraper/batch").mock(side_effect=_capture)
    respx.get(f"{BASE}/url-scraper/b1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "b1",
                "status": "completed",
                "jobType": "batch_url_scraper",
                "urls": ["https://e.com/1", "https://e.com/2"],
                "results": [
                    {"index": 0, "url": "https://e.com/1", "status": "completed", "markdown": "1"},
                    {"index": 1, "url": "https://e.com/2", "status": "failed", "error": "timeout"},
                ],
            },
        )
    )
    result = _client().scrape_batch(["https://e.com/1", "https://e.com/2"], generate_json=True)
    assert captured["urls"] == ["https://e.com/1", "https://e.com/2"]
    assert captured["generateJson"] is True
    assert result.results[0].markdown == "1"
    assert result.results[1].error == "timeout"


def test_scrape_batch_rejects_more_than_ten_urls_locally() -> None:
    with pytest.raises(InvalidRequestError, match="1-10 URLs"):
        _client().scrape_batch([f"https://e.com/{i}" for i in range(11)])


@respx.mock
def test_download_screenshot_returns_bytes() -> None:
    route = respx.get(f"{BASE}/url-scraper/j/screenshot").mock(
        return_value=httpx.Response(200, content=b"\x89PNG", headers={"Content-Type": "image/png"})
    )
    png = _client().download_screenshot("j", full_page=True)
    assert png == b"\x89PNG"
    assert route.calls.last.request.url.params["type"] == "fullpage"


# ─── keyless / Zero Touch ─────────────────────────────────────────────────────


@respx.mock
def test_keyless_scrape_uses_inline_endpoint_without_key() -> None:
    route = respx.post(f"{BASE}/url-scraper/scrape").mock(
        return_value=httpx.Response(
            200,
            json={
                "markdown": "# Example",
                "trial": {"remaining_credits": 47, "signup_url": "https://anakin.io/signup"},
            },
        )
    )
    client = Anakin(base_url=BASE)
    doc = client.scrape("https://example.com")
    assert "X-API-Key" not in route.calls.last.request.headers
    assert doc.markdown == "# Example"
    assert doc.status == "completed"
    assert doc.trial is not None and doc.trial.remaining_credits == 47


@respx.mock
def test_keyless_402_exposes_signup_url() -> None:
    respx.post(f"{BASE}/wire-run").mock(
        return_value=httpx.Response(
            402,
            headers={
                "X-Anakin-Signup": "https://anakin.io/signup?source=keyless",
                "X-Trial-Credits-Remaining": "0",
                "Retry-After": "86400",
            },
            json={
                "error": "keyless_unavailable",
                "message": "The keyless free tier is at capacity right now.",
                "trial": {"remaining_credits": 0, "signup_url": "https://anakin.io/signup"},
            },
        )
    )
    with pytest.raises(InsufficientCreditsError) as ei:
        Anakin(base_url=BASE).wire.zero_touch("hn_stories", {"limit": 2})
    assert ei.value.code == "keyless_unavailable"
    assert ei.value.signup_url == "https://anakin.io/signup"
    assert ei.value.trial_credits_remaining == 0


@respx.mock
def test_inline_scrape_falls_back_to_polling_on_202() -> None:
    respx.post(f"{BASE}/url-scraper/scrape").mock(
        return_value=httpx.Response(202, json={"id": "slow", "status": "processing"})
    )
    respx.get(f"{BASE}/url-scraper/slow").mock(
        return_value=httpx.Response(200, json={"id": "slow", "status": "completed", "markdown": "ok"})
    )
    doc = _client().scrape("https://e.com", inline=True)
    assert doc.markdown == "ok"


# ─── map / crawl / agentic ────────────────────────────────────────────────────


@respx.mock
def test_crawl_sends_session_name_and_webhook() -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(_body(request))
        return httpx.Response(202, json={"jobId": "c", "status": "pending"})

    respx.post(f"{BASE}/crawl").mock(side_effect=_capture)
    result = _client().crawl(
        "https://e.com",
        include_patterns=["/blog/*"],
        session_name="s",
        webhook_url="https://h.example.com",
        wait=False,
    )
    assert result.status == "pending"
    assert captured["includePatterns"] == ["/blog/*"]
    assert "excludePatterns" not in captured
    assert captured["sessionName"] == "s"
    assert captured["webhook_url"] == "https://h.example.com"


@respx.mock
def test_map_failed_raises_with_job_id() -> None:
    respx.post(f"{BASE}/map").mock(
        return_value=httpx.Response(202, json={"jobId": "m", "status": "pending"})
    )
    respx.get(f"{BASE}/map/m").mock(
        return_value=httpx.Response(200, json={"id": "m", "status": "failed", "error": "DNS"})
    )
    with pytest.raises(JobFailedError) as ei:
        _client().map("https://e.com")
    assert ei.value.job_id == "m"


@respx.mock
def test_job_timeout_carries_job_id() -> None:
    respx.post(f"{BASE}/crawl").mock(
        return_value=httpx.Response(202, json={"jobId": "slow", "status": "pending"})
    )
    respx.get(f"{BASE}/crawl/slow").mock(
        return_value=httpx.Response(200, json={"id": "slow", "status": "processing"})
    )
    with pytest.raises(JobTimeoutError) as ei:
        _client(poll_timeout=0.02).crawl("https://e.com")
    assert ei.value.job_id == "slow"


def test_agentic_search_waits_at_least_600s_by_default() -> None:
    from anakin import _ops
    from anakin._http import Call, Wait

    client = _client(poll_timeout=5.0)
    op = _ops.agentic_search(
        client._cfg, "q", use_browser=True, schema=None, webhook_url=None, wait=True,
        poll_timeout=None,
    )
    assert isinstance(next(op), Call)
    op.send({"job_id": "a", "status": "pending"})  # -> first poll Call
    command = op.send({"job_id": "a", "status": "queued"})
    assert isinstance(command, Wait)
    assert command.seconds >= _ops.AGENTIC_MIN_POLL_INTERVAL
    op.close()


# ─── Wire ─────────────────────────────────────────────────────────────────────


@respx.mock
def test_wire_run_with_credential_and_files() -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(_body(request))
        return httpx.Response(202, json={"status": "processing", "job_id": "w"})

    respx.post(f"{BASE}/wire/task").mock(side_effect=_capture)
    respx.get(f"{BASE}/wire/jobs/w").mock(
        side_effect=[
            httpx.Response(200, json={"status": "processing", "retry_after_ms": 1}),
            httpx.Response(
                200,
                json={
                    "status": "completed",
                    "data": None,
                    "files": [{"name": "s.pdf", "content_type": "application/pdf", "size_bytes": 3}],
                    "credits_used": 1,
                },
            ),
        ]
    )
    respx.get(f"{BASE}/wire/jobs/w/download").mock(return_value=httpx.Response(200, content=b"PDF"))
    client = _client()
    result = client.wire.run("bank_statement", {"month": "07"}, credential_id="cred-1")
    assert captured["credential_id"] == "cred-1"
    assert result.job_id == "w"
    assert result.files[0].name == "s.pdf"
    assert client.wire.download("w", file="s.pdf") == b"PDF"


@respx.mock
def test_wire_sync_mode_answers_inline() -> None:
    respx.post(f"{BASE}/wire/task").mock(
        return_value=httpx.Response(200, json={"status": "completed", "data": [1, 2, 3]})
    )
    poll = respx.get(url__regex=rf"{BASE}/wire/jobs/.*")
    result = _client().wire("quick_action")
    assert result.data == [1, 2, 3]
    assert not poll.called


@respx.mock
def test_wire_auth_expired() -> None:
    respx.post(f"{BASE}/wire/task").mock(
        return_value=httpx.Response(
            401,
            json={
                "status": "error",
                "error": {"code": "AUTH_EXPIRED", "message": "Credential is no longer active."},
            },
        )
    )
    with pytest.raises(WireAuthExpiredError):
        _client().wire.run("li_profile_scrape", credential_id="old")


@respx.mock
def test_wire_discover_tolerates_live_shape_without_key() -> None:
    """Live /resolve returns `catalog` (not catalog_slug) and params as {required, optional}."""
    route = respx.get(f"{BASE}/wire/resolve").mock(
        return_value=httpx.Response(
            200,
            json={
                "next": "POST /v1/wire/task with {action_id, params}",
                "results": [
                    {
                        "action_id": "hn_stories",
                        "auth_required": False,
                        "auth_satisfied": None,
                        "catalog": "hackernews",
                        "credits": 2,
                        "params": {"optional": [{"name": "limit", "type": "integer"}], "required": []},
                    },
                    {"action_id": "hn_search", "catalog_slug": "hackernews", "credits": 1},
                ],
            },
        )
    )
    matches = Anakin(base_url=BASE).wire.discover("hacker news", auth_mode="none", limit=1)
    assert len(matches) == 1
    assert matches[0].catalog_slug == "hackernews"
    assert matches[0].credits == 2
    assert route.calls.last.request.url.params["auth_mode"] == "none"
    assert "X-API-Key" not in route.calls.last.request.headers


@respx.mock
def test_wire_catalogs_and_catalog_detail() -> None:
    respx.get(f"{BASE}/wire/catalog").mock(
        return_value=httpx.Response(
            200, json={"catalog": [{"id": "c1", "slug": "airbnb", "name": "Airbnb", "action_count": 4}]}
        )
    )
    respx.get(f"{BASE}/wire/catalog/airbnb").mock(
        return_value=httpx.Response(
            200,
            json={
                "catalog": {"id": "c1", "slug": "airbnb", "name": "Airbnb"},
                "actions": [
                    {
                        "action_id": "ab_search_listings",
                        "type": "read",
                        "auth_mode": "none",
                        "credits_per_call": 1,
                        "parameters": [{"name": "query", "type": "string", "required": True}],
                    }
                ],
                "login_input_schema": [{"name": "email", "type": "string", "required": True}],
            },
        )
    )
    client = _client()
    assert client.wire.catalogs()[0].slug == "airbnb"
    detail = client.wire.catalog("airbnb")
    assert detail.actions[0].action_id == "ab_search_listings"
    assert detail.login_input_schema[0]["name"] == "email"


@respx.mock
def test_wire_identities_and_login() -> None:
    respx.get(f"{BASE}/wire/identities").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ok",
                "identities": [
                    {
                        "id": "i1",
                        "name": "Personal",
                        "credentials": [{"id": "cred-1", "status": "expired"}],
                    }
                ],
            },
        )
    )
    respx.post(f"{BASE}/wire/login").mock(
        return_value=httpx.Response(
            201,
            json={
                "status": "verified",
                "identity_id": "i1",
                "identity_name": "a@b.com",
                "credential_id": "cred-2",
                "catalog_slug": "neb",
                "expires_at": "2026-05-29T08:09:23Z",
            },
        )
    )
    client = _client()
    identities = client.wire.identities()
    assert identities[0].credentials[0].status == "expired"
    login = client.wire.login("neb", {"email": "a@b.com", "password": "x"})
    assert login.credential_id == "cred-2"


@respx.mock
def test_wire_login_200_with_error_status_raises() -> None:
    respx.post(f"{BASE}/wire/login").mock(
        return_value=httpx.Response(
            200,
            json={"status": "error", "error": {"code": "BAD_PASSWORD", "message": "Rejected"}},
        )
    )
    with pytest.raises(WireLoginError) as ei:
        _client().wire.login("neb", {"email": "a", "password": "b"})
    assert ei.value.code == "BAD_PASSWORD"


@respx.mock
def test_wire_build_and_action_exists_conflict() -> None:
    respx.post(f"{BASE}/wire/build-request").mock(
        side_effect=[
            httpx.Response(
                201,
                json={
                    "status": "ok",
                    "build_request": {"id": "b1", "status": "pending", "credits_charged": 25},
                },
            ),
            httpx.Response(
                409,
                json={
                    "status": "error",
                    "error": {
                        "code": "ACTION_EXISTS",
                        "message": "Similar actions already exist.",
                        "existing_actions": [{"action_id": "x"}],
                    },
                },
            ),
        ]
    )
    client = _client()
    build = client.wire.build("https://example.com", "Extract prices", actions=["get price"])
    assert build.id == "b1" and build.credits_charged == 25
    with pytest.raises(ConflictError) as ei:
        client.wire.build("https://example.com", "Extract prices")
    assert ei.value.code == "ACTION_EXISTS"
    assert ei.value.body["error"]["existing_actions"][0]["action_id"] == "x"


@respx.mock
def test_wire_identity_source_entries_percent_encodes_container() -> None:
    route = respx.get(url__regex=rf"{BASE}/wire/identity-sources/s1/containers/.+/entries").mock(
        return_value=httpx.Response(200, json={"entries": [{"id": "e1", "title": "Acme"}]})
    )
    entries = _client().wire.sources.entries("s1", "https://my-vault.vault.azure.net", domain="acme")
    assert entries[0]["id"] == "e1"
    assert "https%3A%2F%2Fmy-vault.vault.azure.net" in str(route.calls.last.request.url)


# ─── Monitors ─────────────────────────────────────────────────────────────────


@respx.mock
def test_monitor_create_maps_snake_case_to_api() -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(_body(request))
        return httpx.Response(
            201,
            json={
                "id": "mon1",
                "url": "https://e.com/p",
                "watchMode": "specific_data",
                "intervalMinutes": 60,
                "creditCostPerRun": 4,
                "alertWebhookSecret": "whsec_abc",
            },
        )

    respx.post(f"{BASE}/monitors").mock(side_effect=_capture)
    monitor = _client().monitors.create(
        "https://e.com/p",
        60,
        watch_mode="specific_data",
        output_schema={"type": "object"},
        ai_mode=True,
        alert_emails=["a@x.com", "b@x.com"],
        alert_webhook_url="https://h.example.com",
        expires_at="2026-12-31",
    )
    assert captured == {
        "url": "https://e.com/p",
        "intervalMinutes": 60,
        "watchMode": "specific_data",
        "outputSchema": {"type": "object"},
        "aiMode": True,
        "alertEmails": "a@x.com,b@x.com",
        "alertWebhookUrl": "https://h.example.com",
        "expiresAt": "2026-12-31",
    }
    assert monitor.alert_webhook_secret == "whsec_abc"
    assert monitor.credit_cost_per_run == 4


def test_monitor_create_rejects_unknown_option() -> None:
    with pytest.raises(TypeError, match="Unknown monitor option"):
        _client().monitors.create("https://e.com", 60, watchMode="full_page")  # type: ignore[call-arg]


@respx.mock
def test_monitor_controls_and_changes() -> None:
    respx.post(f"{BASE}/monitors/m1/pause").mock(
        return_value=httpx.Response(200, json={"id": "m1", "url": "u", "isActive": False})
    )
    respx.post(f"{BASE}/monitors/m1/run").mock(
        return_value=httpx.Response(200, json={"success": True, "jobId": "job_1"})
    )
    respx.get(f"{BASE}/monitors/m1/changes").mock(
        return_value=httpx.Response(
            200,
            json={
                "changes": [
                    {
                        "id": "c1",
                        "summary": "Price dropped",
                        "diffJson": {"type": "fields", "changedFields": ["price"]},
                    }
                ]
            },
        )
    )
    respx.delete(f"{BASE}/monitors/m1").mock(return_value=httpx.Response(200, json={"success": True}))
    client = _client()
    assert client.monitors.pause("m1").is_active is False
    assert client.monitors.run_now("m1").job_id == "job_1"
    assert client.monitors.changes("m1")[0].diff["changedFields"] == ["price"]
    client.monitors.delete("m1")


@respx.mock
def test_monitor_session_expired_is_conflict() -> None:
    respx.post(f"{BASE}/monitors/m1/run").mock(
        return_value=httpx.Response(409, json={"error": "session_expired", "message": "re-auth"})
    )
    with pytest.raises(ConflictError):
        _client().monitors.run_now("m1")


# ─── AI Visibility ────────────────────────────────────────────────────────────


@respx.mock
def test_ai_visibility_search_polls_until_completed() -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.update(_body(request))
        return httpx.Response(
            200, json={"search_id": "s1", "status": "running", "results": [], "country": "in"}
        )

    respx.post(f"{BASE}/ai-visibility/search").mock(side_effect=_capture)
    respx.get(f"{BASE}/ai-visibility/search/s1").mock(
        side_effect=[
            httpx.Response(200, json={"search_id": "s1", "status": "running", "results": []}),
            httpx.Response(
                200,
                json={
                    "search_id": "s1",
                    "status": "completed",
                    "synthesis": "They agree.",
                    "results": [
                        {"source": "chatgpt", "status": "completed", "summary": "A", "credits_used": 1},
                        {"source": "gemini", "status": "failed", "error": "timeout"},
                    ],
                },
            ),
        ]
    )
    result = _client().ai_visibility.search("best scraping api", sources=["chatgpt", "gemini"], country="in")
    assert captured == {"query": "best scraping api", "sources": ["chatgpt", "gemini"], "country": "in"}
    assert result.synthesis == "They agree."
    assert result.query == "best scraping api"
    assert [r.status for r in result.results] == ["completed", "failed"]


@respx.mock
def test_ai_visibility_sources() -> None:
    respx.get(f"{BASE}/ai-visibility/sources").mock(
        return_value=httpx.Response(200, json={"sources": [{"slug": "chatgpt", "label": "ChatGPT"}]})
    )
    assert _client().ai_visibility.sources()[0].slug == "chatgpt"


# ─── Webhooks ─────────────────────────────────────────────────────────────────


@respx.mock
def test_webhooks_crud_and_secret() -> None:
    respx.post(f"{BASE}/webhooks").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "w1",
                "url": "https://h.example.com",
                "events": ["job.completed"],
                "isActive": True,
                "secret": "whsec_1",
            },
        )
    )
    respx.get(f"{BASE}/webhooks/signing-secret").mock(
        return_value=httpx.Response(200, json={"secret": "whsec_default"})
    )
    deliveries = respx.get(f"{BASE}/webhooks/deliveries").mock(
        return_value=httpx.Response(
            200, json={"deliveries": [{"id": "d1", "status": "failed", "attempts": 6}]}
        )
    )
    client = _client()
    endpoint = client.webhooks.create("https://h.example.com", events=["job.completed"])
    assert endpoint.secret == "whsec_1"
    assert client.webhooks.signing_secret() == "whsec_default"
    assert client.webhooks.deliveries(status="failed", job_id="j1")[0].attempts == 6
    params = deliveries.calls.last.request.url.params
    assert params["status"] == "failed" and params["jobId"] == "j1"


# ─── Browser API ──────────────────────────────────────────────────────────────


def test_browser_connect_url_and_headers() -> None:
    client = _client()
    url = client.browser.connect_url(country="gb", session_name="my-login", record=True)
    assert url == (
        "wss://api.anakin.io/v1/browser-connect?country=GB&session_name=my-login&record=true"
    )
    assert client.browser.headers() == {"X-API-Key": "ak-test"}
    assert "ak-test" not in url


@respx.mock
def test_recordings_get() -> None:
    respx.get(f"{BASE}/recordings/rec-1").mock(
        return_value=httpx.Response(
            200, json={"id": "abc", "connId": "rec-1", "videoUrl": "https://s3/x.webm"}
        )
    )
    assert _client().browser.recordings.get("rec-1").video_url == "https://s3/x.webm"


# ─── HTTP layer ───────────────────────────────────────────────────────────────


@respx.mock
def test_500_is_retried() -> None:
    respx.post(f"{BASE}/search").mock(
        side_effect=[
            httpx.Response(500, json={"error": "queue_error", "message": "retry"}),
            httpx.Response(200, json={"id": "s", "results": []}),
        ]
    )
    assert _client().search("q").id == "s"


@respx.mock
def test_huge_retry_after_is_not_slept_on() -> None:
    route = respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "86400"}, json={"error": "rate_limit_exceeded"})
    )
    with pytest.raises(RateLimitError) as ei:
        _client().search("q")
    assert route.call_count == 1
    assert ei.value.retry_after == 86400


@pytest.mark.parametrize(
    ("status", "error_cls"),
    [(403, AnakinPermissionError), (409, ConflictError), (422, UnprocessableEntityError)],
)
@respx.mock
def test_status_mapping(status: int, error_cls: type[AnakinError]) -> None:
    respx.get(f"{BASE}/sessions").mock(
        return_value=httpx.Response(status, json={"error": "x", "message": "nope"})
    )
    with pytest.raises(error_cls):
        _client().sessions.list()


@respx.mock
def test_legacy_status_code_error_shape() -> None:
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(400, json={"statusCode": 400, "message": ["limit must be <= 20"]})
    )
    with pytest.raises(InvalidRequestError, match="limit must be <= 20"):
        _client().search("q", limit=50)


@respx.mock
def test_missing_job_id_raises_anakin_error() -> None:
    respx.post(f"{BASE}/map").mock(return_value=httpx.Response(202, json={"status": "pending"}))
    with pytest.raises(AnakinError, match="did not include a job id"):
        _client().map("https://e.com")


def test_keyless_monitor_call_fails_fast() -> None:
    with pytest.raises(ConfigurationError, match=r"anakin\.io/signup"):
        Anakin(base_url=BASE).monitors.list()


def test_permission_error_alias_is_backwards_compatible() -> None:
    import anakin

    assert anakin.PermissionError is AnakinPermissionError
    assert "PermissionError" not in anakin.__all__
