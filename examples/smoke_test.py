"""
Smoke test: runs the core methods against the real api.anakin.io.

Usage:
    ANAKIN_API_KEY=ak-... python examples/smoke_test.py

Prints minimal output and exits 0 on success, non-zero on first failure.
Designed to be run manually before a release; not part of `pytest` suite.
"""

from __future__ import annotations

import os
import sys
import time

from anakin import Anakin


def banner(msg: str) -> None:
    print(f"\n=== {msg} ===")


def main() -> int:
    if not os.environ.get("ANAKIN_API_KEY"):
        print("ANAKIN_API_KEY not set", file=sys.stderr)
        return 2

    client = Anakin()  # picks up env var

    # ─── 1. scrape ──────────────────────────────────────────────────────────
    banner("scrape https://example.com (markdown)")
    t0 = time.monotonic()
    doc = client.scrape("https://example.com", formats=["markdown"])
    dt = time.monotonic() - t0
    print(f"  status={doc.status}  cached={doc.cached}  duration_ms={doc.duration_ms}  wall={dt:.1f}s")
    print(f"  markdown[:80]={(doc.markdown or '')[:80]!r}")
    assert doc.status == "completed", f"expected completed, got {doc.status}"
    assert doc.markdown, "no markdown returned"

    # ─── 2. map ─────────────────────────────────────────────────────────────
    banner("map https://example.com (limit=10)")
    t0 = time.monotonic()
    sitemap = client.map("https://example.com", limit=10, depth=1)
    dt = time.monotonic() - t0
    print(f"  total_links={sitemap.total_links}  links={len(sitemap.links)}  wall={dt:.1f}s")
    print(f"  first 3: {sitemap.links[:3]}")
    assert sitemap.total_links >= 0, "total_links should be non-negative"

    # ─── 3. crawl ───────────────────────────────────────────────────────────
    banner("crawl https://example.com (max_pages=2)")
    t0 = time.monotonic()
    crawl = client.crawl("https://example.com", max_pages=2, depth=1)
    dt = time.monotonic() - t0
    print(
        f"  total_pages={crawl.total_pages}  completed={crawl.completed_pages}  wall={dt:.1f}s"
    )
    for i, page in enumerate(crawl.pages[:3]):
        md_len = len(page.markdown or "")
        print(f"  page[{i}] status={page.status} url={page.url} markdown_len={md_len}")
    assert crawl.total_pages > 0, "expected at least one page"

    # ─── 4. countries (static, in-memory) ───────────────────────────────────
    banner("countries() (static)")
    countries = client.countries()
    print(f"  total={len(countries)}  first 5={[c.code for c in countries[:5]]}")
    assert len(countries) > 200, "static country list should ship 200+ codes"

    # ─── 5. sessions.list (free, GET) ───────────────────────────────────────
    banner("sessions.list()")
    sessions = client.sessions.list()
    print(f"  total_sessions={len(sessions)}")
    print(f"  first 3 names: {[s.name for s in sessions[:3]]}")

    # ─── 6. search (3 credits, sync) ────────────────────────────────────────
    banner("search('python sdk best practices', limit=3)")
    t0 = time.monotonic()
    s_result = client.search("python sdk best practices", limit=3)
    dt = time.monotonic() - t0
    print(f"  id={s_result.id}  results={len(s_result.results)}  wall={dt:.1f}s")
    for i, r in enumerate(s_result.results[:3]):
        print(f"  [{i}] {(r.title or '')[:50]:50s}  {r.url}")

    # ─── 7. wire discovery + catalog (free) ─────────────────────────────────
    banner("wire.discover('hacker news top stories') + wire.catalogs()")
    matches = client.wire.discover("hacker news top stories", limit=3)
    print(f"  matches={[m.action_id for m in matches]}")
    assert matches, "expected at least one Wire action match"
    catalogs = client.wire.catalogs()
    print(f"  catalogs={len(catalogs)}")
    assert len(catalogs) > 10, "expected a populated Wire catalog"

    # ─── 8. ai_visibility.sources / webhooks.events / monitors.list (free) ───
    banner("ai_visibility.sources() / webhooks.events() / monitors.list()")
    print(f"  ai sources={[s.slug for s in client.ai_visibility.sources()]}")
    print(f"  webhook events={client.webhooks.events()}")
    print(f"  monitors={len(client.monitors.list())}")

    # NOTE: agentic_search (~2-5 min), wire.run (credits) and monitors.create
    # (credits per check) are not exercised here. Run those manually as needed.

    banner("ALL GOOD ✓")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
