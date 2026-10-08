"""
Tests for AsyncAnakin and the generated async client.

The async client shares every operation with the sync one (see
`anakin._ops`), so these focus on the async driver, lifecycle, and that the
generated file is in sync with `client.py`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx

from anakin import AsyncAnakin, JobFailedError, RateLimitError

BASE = "https://api.anakin.io/v1"
ROOT = Path(__file__).resolve().parent.parent


def _client() -> AsyncAnakin:
    return AsyncAnakin(
        api_key="ak-test",
        base_url=BASE,
        poll_interval=0.001,
        poll_max_interval=0.01,
        poll_timeout=2.0,
    )


@respx.mock
async def test_async_scrape_polls_to_completion() -> None:
    respx.post(f"{BASE}/url-scraper").mock(
        return_value=httpx.Response(202, json={"jobId": "j", "status": "pending"})
    )
    respx.get(f"{BASE}/url-scraper/j").mock(
        side_effect=[
            httpx.Response(200, json={"id": "j", "status": "processing"}),
            httpx.Response(200, json={"id": "j", "status": "completed", "markdown": "# a"}),
        ]
    )
    async with _client() as client:
        doc = await client.scrape("https://e.com")
    assert doc.markdown == "# a"


@respx.mock
async def test_async_wire_namespace_and_callable() -> None:
    respx.post(f"{BASE}/wire/task").mock(
        return_value=httpx.Response(202, json={"status": "processing", "job_id": "w"})
    )
    respx.get(f"{BASE}/wire/jobs/w").mock(
        return_value=httpx.Response(
            200, json={"status": "failed", "error": {"code": "EXECUTION_FAILED", "message": "down"}}
        )
    )
    async with _client() as client:
        with pytest.raises(JobFailedError) as ei:
            await client.wire("act", {"q": 1})
    assert ei.value.code == "EXECUTION_FAILED"
    assert ei.value.job_id == "w"


@respx.mock
async def test_async_retries_then_raises() -> None:
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )
    client = AsyncAnakin(api_key="ak", base_url=BASE, max_retries=1)
    with pytest.raises(RateLimitError):
        await client.search("q")
    await client.close()


async def test_async_static_helpers_are_not_coroutines() -> None:
    client = _client()
    assert len(client.countries()) > 200
    assert client.browser.connect_url().startswith("wss://")
    await client.close()


def test_generated_async_client_is_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_async.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
