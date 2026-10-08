"""
Unit tests for the Anakin client.

All HTTP traffic mocked via respx — no real network calls. These tests pin
the contract: method signatures, request bodies, polling behaviour, error
mapping, and response model shape.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from anakin import (
    Anakin,
    AuthenticationError,
    ConfigurationError,
    InsufficientCreditsError,
    InvalidRequestError,
    JobFailedError,
    JobTimeoutError,
    RateLimitError,
)

BASE = "https://api.anakin.io/v1"


def _make_client(**overrides: object) -> Anakin:
    return Anakin(
        api_key="ak-test",
        base_url=BASE,
        poll_interval=0.001,
        poll_max_interval=0.01,
        poll_timeout=2.0,
        **overrides,  # type: ignore[arg-type]
    )


# ─── Construction ─────────────────────────────────────────────────────────────


def test_construct_without_key_is_keyless_mode() -> None:
    """No key = Zero Touch mode: construction works, keyed calls fail fast locally."""
    client = Anakin(base_url=BASE)
    assert client.api_key_configured is False
    with pytest.raises(ConfigurationError, match="needs an Anakin API key"):
        client.crawl("https://e.com")
    client.close()


def test_construct_with_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANAKIN_API_KEY", "ak-env")
    client = Anakin(base_url=BASE)
    assert client._cfg.api_key == "ak-env"
    client.close()


def test_explicit_key_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANAKIN_API_KEY", "ak-env")
    client = Anakin(api_key="ak-explicit", base_url=BASE)
    assert client._cfg.api_key == "ak-explicit"
    client.close()


# ─── scrape ───────────────────────────────────────────────────────────────────


@respx.mock
def test_scrape_happy_path() -> None:
    submit = respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(202, json={"jobId": "job-1", "status": "pending"})
    )
    poll = respx.get(f"{BASE}/url-scraper/job-1").mock(
        side_effect=[
            httpx.Response(200, json={"id": "job-1", "status": "processing"}),
            httpx.Response(
                200,
                json={
                    "id": "job-1",
                    "url": "https://example.com",
                    "status": "completed",
                    "cached": False,
                    "durationMs": 1500,
                    "markdown": "# Example",
                },
            ),
        ]
    )
    client = _make_client()
    doc = client.scrape("https://example.com", formats=["markdown"])
    assert submit.called
    assert poll.call_count == 2
    assert doc.id == "job-1"
    assert doc.status == "completed"
    assert doc.markdown == "# Example"
    assert doc.duration_ms == 1500


@respx.mock
def test_scrape_request_body_matches_contract() -> None:
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured.update(_json.loads(request.content))
        return httpx.Response(202, json={"jobId": "j", "status": "pending"})

    respx.post(f"{BASE}/url-scraper").mock(side_effect=_capture)
    respx.get(f"{BASE}/url-scraper/j").mock(
        return_value=httpx.Response(
            200,
            json={"id": "j", "url": "https://e.com", "status": "completed", "cached": False},
        )
    )

    client = _make_client()
    client.scrape(
        "https://e.com",
        formats=["markdown", "html"],
        country="us",
        use_browser=True,
        generate_json=True,
        force_fresh=True,
    )

    assert captured["url"] == "https://e.com"
    assert captured["formats"] == ["markdown", "html"]
    assert captured["country"] == "us"
    assert captured["useBrowser"] is True
    assert captured["generateJson"] is True
    assert captured["forceFresh"] is True


@respx.mock
def test_scrape_failed_job_raises_job_failed() -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(202, json={"jobId": "j", "status": "pending"})
    )
    respx.get(f"{BASE}/url-scraper/j").mock(
        return_value=httpx.Response(
            200,
            json={"id": "j", "url": "https://e.com", "status": "failed", "error": "timeout"},
        )
    )
    client = _make_client()
    with pytest.raises(JobFailedError) as ei:
        client.scrape("https://e.com")
    assert "timeout" in str(ei.value)


# ─── map ──────────────────────────────────────────────────────────────────────


@respx.mock
def test_map_happy_path() -> None:
    respx.post(f"{BASE}/map").mock(
        return_value=httpx.Response(202, json={"jobId": "m1", "status": "pending"})
    )
    respx.get(f"{BASE}/map/m1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m1",
                "url": "https://e.com",
                "status": "completed",
                "links": ["https://e.com/a", "https://e.com/b"],
                "totalLinks": 2,
            },
        )
    )
    client = _make_client()
    result = client.map("https://e.com", limit=200)
    assert len(result.links) == 2
    assert result.total_links == 2


# ─── crawl ────────────────────────────────────────────────────────────────────


@respx.mock
def test_crawl_happy_path() -> None:
    respx.post(f"{BASE}/crawl").mock(
        return_value=httpx.Response(202, json={"jobId": "c1", "status": "pending"})
    )
    respx.get(f"{BASE}/crawl/c1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c1",
                "url": "https://e.com",
                "status": "completed",
                "totalPages": 2,
                "completedPages": 2,
                "results": [
                    {
                        "url": "https://e.com/a",
                        "status": "completed",
                        "markdown": "# a",
                        "durationMs": 100,
                    },
                    {
                        "url": "https://e.com/b",
                        "status": "failed",
                        "error": "404",
                        "durationMs": 200,
                    },
                ],
            },
        )
    )
    client = _make_client()
    result = client.crawl("https://e.com", max_pages=5)
    assert result.total_pages == 2
    assert result.completed_pages == 2
    assert len(result.pages) == 2
    assert result.pages[0].markdown == "# a"
    assert result.pages[1].error == "404"


# ─── error mapping ────────────────────────────────────────────────────────────


@respx.mock
def test_401_raises_authentication_error() -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized", "message": "bad key"})
    )
    client = _make_client()
    with pytest.raises(AuthenticationError) as ei:
        client.scrape("https://e.com")
    assert ei.value.status_code == 401


@respx.mock
def test_402_raises_insufficient_credits() -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(
            402,
            json={
                "status": "error",
                "error": {
                    "code": "INSUFFICIENT_CREDITS",
                    "message": "You need 5 credits. Current balance: 2",
                    "balance": 2,
                    "required": 5,
                },
            },
        )
    )
    client = _make_client()
    with pytest.raises(InsufficientCreditsError) as ei:
        client.scrape("https://e.com")
    assert ei.value.balance == 2
    assert ei.value.required == 5


@respx.mock
def test_400_raises_invalid_request() -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(400, json={"error": "invalid_url", "message": "bad url"})
    )
    client = _make_client()
    with pytest.raises(InvalidRequestError):
        client.scrape("not-a-url")


@respx.mock
def test_429_retries_then_succeeds() -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(202, json={"jobId": "ok", "status": "pending"}),
        ]
    )
    respx.get(f"{BASE}/url-scraper/ok").mock(
        return_value=httpx.Response(
            200,
            json={"id": "ok", "url": "https://e.com", "status": "completed", "cached": False},
        )
    )
    client = _make_client()
    doc = client.scrape("https://e.com")
    assert doc.id == "ok"


@respx.mock
def test_429_after_retries_raises_rate_limit() -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )
    client = Anakin(api_key="ak-test", base_url=BASE, max_retries=1)
    with pytest.raises(RateLimitError):
        client.scrape("https://e.com")
    client.close()


# ─── polling timeout ──────────────────────────────────────────────────────────


@respx.mock
def test_poll_timeout_raises() -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(202, json={"jobId": "j", "status": "pending"})
    )
    respx.get(f"{BASE}/url-scraper/j").mock(
        return_value=httpx.Response(200, json={"id": "j", "status": "processing"})
    )
    client = Anakin(
        api_key="ak-test",
        base_url=BASE,
        poll_interval=0.01,
        poll_max_interval=0.01,
        poll_timeout=0.05,
    )
    with pytest.raises(JobTimeoutError):
        client.scrape("https://e.com")
    client.close()
