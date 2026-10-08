"""
Live end-to-end test of the SDK against the real api.anakin.io.

Spends a small number of credits. Creates its own monitor and webhook
endpoint and deletes them at the end; never touches existing resources and
never rotates the signing secret.

Usage:
    ANAKIN_API_KEY=ak-... python scripts/live_test.py              # standard run
    ANAKIN_API_KEY=ak-... python scripts/live_test.py --expensive  # + agentic search
    ANAKIN_API_KEY=ak-... python scripts/live_test.py --only wire  # one section

Exits non-zero if any check fails. Run examples/smoke_test.py first.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any

from anakin import (
    Anakin,
    AnakinError,
    AsyncAnakin,
    NotFoundError,
    WireAuthRequiredError,
)

RESULTS: list[tuple[str, bool, str]] = []
CLEANUP: list[tuple[str, Callable[[], Any]]] = []


def check(name: str) -> Callable[[Callable[[], str | None]], None]:
    """Run the decorated function immediately and record pass/fail."""

    def run(fn: Callable[[], str | None]) -> None:
        section = name.split(":")[0]
        if ONLY and section != ONLY:
            return
        t0 = time.monotonic()
        try:
            detail = fn() or ""
            RESULTS.append((name, True, detail))
            print(f"  PASS  {name}  ({time.monotonic() - t0:.1f}s) {detail}")
        except Exception as exc:
            RESULTS.append((name, False, repr(exc)))
            print(f"  FAIL  {name}: {exc!r}")
            traceback.print_exc(limit=2)

    return run


ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
EXPENSIVE = "--expensive" in sys.argv


def main() -> int:
    if not os.environ.get("ANAKIN_API_KEY"):
        print("ANAKIN_API_KEY not set", file=sys.stderr)
        return 2
    client = Anakin(poll_timeout=180)

    # ─── scrape ───────────────────────────────────────────────────────────────
    print("\n== scrape ==")
    state: dict[str, Any] = {}

    @check("scrape: links/images/summary/screenshot formats")
    def _() -> str:
        doc = client.scrape(
            "https://www.python.org",
            formats=["markdown", "links", "images", "summary", "screenshot"],
        )
        assert doc.status == "completed", doc.status
        assert doc.links and doc.links[0].href, "links should be [{href, text}]"
        state["screenshot_job"] = doc.id
        return f"links={len(doc.links)} images={len(doc.images or [])} summary={bool(doc.summary)}"

    @check("scrape: download_screenshot")
    def _() -> str:
        png = client.download_screenshot(state["screenshot_job"])
        assert png[:4] == b"\x89PNG", png[:8]
        return f"{len(png)} bytes"

    @check("scrape: wait=False then get_scrape")
    def _() -> str:
        pending = client.scrape("https://example.com", wait=False, force_fresh=True)
        assert pending.status in {"pending", "processing"}, pending.status
        for _ in range(30):
            doc = client.get_scrape(pending.id)
            if doc.status in {"completed", "failed"}:
                return f"{pending.id} -> {doc.status}"
            time.sleep(2)
        raise AssertionError("job did not finish in 60s")

    @check("scrape: output_schema + browser actions")
    def _() -> str:
        doc = client.scrape(
            "https://books.toscrape.com",
            output_schema={
                "type": "object",
                "properties": {"first_book_title": {"type": "string"}},
            },
            actions=[{"type": "wait_for", "selector": "article.product_pod"}],
        )
        assert doc.generated_json, "expected AI-extracted JSON"
        return str(doc.generated_json)[:80]

    @check("scrape: inline endpoint")
    def _() -> str:
        doc = client.scrape("https://example.com", inline=True)
        assert doc.markdown, "no markdown"
        return f"status={doc.status}"

    @check("scrape: scrape_batch")
    def _() -> str:
        batch = client.scrape_batch(["https://example.com", "https://example.org"])
        statuses = [r.status for r in batch.results]
        assert len(batch.results) == 2, statuses
        return f"{batch.status} {statuses}"

    # ─── map / crawl ──────────────────────────────────────────────────────────
    print("\n== map/crawl ==")

    @check("map: real site")
    def _() -> str:
        result = client.map("https://docs.python.org/3/", limit=20, depth=1)
        assert result.links, "no links"
        return f"total_links={result.total_links}"

    @check("crawl: wait=False then get_crawl")
    def _() -> str:
        job = client.crawl("https://example.com", max_pages=1, wait=False)
        for _ in range(30):
            result = client.get_crawl(job.id)
            if result.status in {"completed", "failed"}:
                return f"{job.id} -> {result.status}, pages={len(result.pages)}"
            time.sleep(2)
        raise AssertionError("crawl did not finish in 60s")

    # ─── wire ─────────────────────────────────────────────────────────────────
    print("\n== wire ==")

    @check("wire: catalog detail")
    def _() -> str:
        detail = client.wire.catalog("hackernews")
        assert detail.actions, "no actions"
        return f"{detail.catalog.name}: {[a.action_id for a in detail.actions]}"

    @check("wire: run (read action)")
    def _() -> str:
        result = client.wire.run("hn_stories", {"limit": 2})
        assert result.status == "completed", result.status
        state["wire_job"] = result.job_id
        return f"credits={result.credits_used} data={str(result.data)[:80]}"

    @check("wire: get_job")
    def _() -> str:
        job = client.wire.get_job(state["wire_job"])
        assert job.status == "completed", job.status
        return job.status

    @check("wire: callable shorthand + wait=False")
    def _() -> str:
        pending = client.wire("hn_search", {"query": "python"}, wait=False)
        return f"job_id={pending.job_id} status={pending.status}"

    @check("wire: identities")
    def _() -> str:
        identities = client.wire.identities()
        return f"{len(identities)} identities"

    @check("wire: auth-required action raises WireAuthRequiredError (or runs)")
    def _() -> str:
        candidates = client.wire.discover("linkedin profile", auth_mode="required", limit=1)
        if not candidates:
            return "skipped: no auth-required action found"
        try:
            client.wire.run(candidates[0].action_id, {}, wait=False)
        except WireAuthRequiredError as err:
            return f"connect_url={err.connect_url}"
        except AnakinError as err:
            return f"other error (acceptable, account may be connected): {err.code}"
        return "ran (account already connected)"

    @check("wire: builds list")
    def _() -> str:
        return f"{len(client.wire.builds(limit=5))} recent builds"

    # ─── ai visibility ────────────────────────────────────────────────────────
    print("\n== ai_visibility ==")

    @check("ai_visibility: search (1 source)")
    def _() -> str:
        result = client.ai_visibility.search("What is anakin.io?", sources=["chatgpt"])
        state["ai_search"] = result.search_id
        return f"{result.status} {[(r.source, r.status) for r in result.results]}"

    @check("ai_visibility: get + list")
    def _() -> str:
        got = client.ai_visibility.get(state["ai_search"])
        recent = client.ai_visibility.list()
        assert any(s.search_id == got.search_id for s in recent)
        return f"recent={len(recent)}"

    # ─── monitors (created inactive; one billed check via run_now) ────────────
    print("\n== monitors ==")

    @check("monitors: create (inactive)")
    def _() -> str:
        monitor = client.monitors.create(
            "https://example.com", 1440, is_active=False, watch_format="markdown"
        )
        state["monitor"] = monitor.id
        CLEANUP.append(("delete monitor", lambda: client.monitors.delete(monitor.id)))
        return f"id={monitor.id} cost/run={monitor.credit_cost_per_run}"

    @check("monitors: get/update/pause/resume/pause")
    def _() -> str:
        mid = state["monitor"]
        assert client.monitors.get(mid).id == mid
        updated = client.monitors.update(mid, "https://example.com", 720, is_active=False)
        assert updated.interval_minutes == 720, updated.interval_minutes
        assert client.monitors.resume(mid).is_active is True
        assert client.monitors.pause(mid).is_active is False
        return "ok"

    @check("monitors: run_now + snapshots/changes/deliveries")
    def _() -> str:
        mid = state["monitor"]
        run = client.monitors.run_now(mid)
        time.sleep(15)
        snaps = client.monitors.snapshots(mid)
        changes = client.monitors.changes(mid)
        deliveries = client.monitors.deliveries(mid)
        return (
            f"job={run.job_id} snapshots={len(snaps)} changes={len(changes)} "
            f"deliveries={len(deliveries)}"
        )

    # ─── webhooks (own endpoint only; never rotates the secret) ───────────────
    print("\n== webhooks ==")

    @check("webhooks: create/list/update")
    def _() -> str:
        endpoint = client.webhooks.create(
            "https://example.com/anakin-sdk-live-test",
            description="anakin-sdk live test (safe to delete)",
            events=["webhook.test"],
        )
        state["webhook"] = endpoint.id
        CLEANUP.append(("delete webhook", lambda: client.webhooks.delete(endpoint.id)))
        assert endpoint.secret, "secret should be returned on create"
        assert any(e.id == endpoint.id for e in client.webhooks.list())
        updated = client.webhooks.update(endpoint.id, is_active=False)
        return f"id={endpoint.id} active={updated.is_active}"

    @check("webhooks: test + deliveries + signing_secret")
    def _() -> str:
        result = client.webhooks.test(state["webhook"])
        deliveries = client.webhooks.deliveries(endpoint_id=state["webhook"], limit=5)
        secret = client.webhooks.signing_secret()
        assert secret.startswith("whsec_"), "unexpected secret format"
        return f"test_http={result.http_status} deliveries={len(deliveries)}"

    # ─── browser ──────────────────────────────────────────────────────────────
    print("\n== browser ==")

    @check("browser: recordings list")
    def _() -> str:
        return f"{len(client.browser.recordings.list())} recordings"

    # ─── errors ───────────────────────────────────────────────────────────────
    print("\n== errors ==")

    @check("errors: unknown job -> NotFoundError")
    def _() -> str:
        try:
            client.get_scrape("00000000-0000-0000-0000-000000000000")
        except NotFoundError as err:
            return f"request_id={err.request_id}"
        except AnakinError as err:
            raise AssertionError(f"expected NotFoundError, got {type(err).__name__}") from err
        raise AssertionError("no error raised")

    # ─── async ────────────────────────────────────────────────────────────────
    print("\n== async ==")

    @check("async: concurrent scrape + search")
    def _() -> str:
        async def go() -> str:
            async with AsyncAnakin() as aclient:
                doc, results = await asyncio.gather(
                    aclient.scrape("https://example.com"),
                    aclient.search("anakin web scraping api", limit=2),
                )
            return f"markdown={len(doc.markdown or '')} results={len(results.results)}"

        return asyncio.run(go())

    # ─── expensive (opt-in) ───────────────────────────────────────────────────
    if EXPENSIVE:
        print("\n== expensive ==")

        @check("agentic: agentic_search with schema")
        def _() -> str:
            result = client.agentic_search(
                "List 3 popular Python HTTP client libraries",
                schema={
                    "type": "object",
                    "properties": {"libraries": {"type": "array", "items": {"type": "string"}}},
                },
            )
            assert result.generated_json, "no generated_json"
            return str(result.generated_json.structured_data)[:100]

    # ─── cleanup + summary ────────────────────────────────────────────────────
    print("\n== cleanup ==")
    for label, fn in CLEANUP:
        try:
            fn()
            print(f"  ok    {label}")
        except Exception as exc:
            print(f"  FAIL  {label}: {exc!r}  <- delete it manually")
    client.close()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    for name, _, detail in failed:
        print(f"  FAILED: {name}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
