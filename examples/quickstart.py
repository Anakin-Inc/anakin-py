"""
Anakin Python SDK: quickstart.

Six copy-paste recipes for the most common workflows:
1. Run a pre-built Wire action (structured data from a known site)
2. Scrape a single page to markdown
3. Scrape several pages in one batch
4. Discover all URLs on a site (map)
5. Crawl a site into a knowledge base
6. AI-powered web search

Run:
    pip install anakin-sdk
    ANAKIN_API_KEY=ak-... python examples/quickstart.py

No key yet? Get one free (300 credits) at https://anakin.io/signup, or try
examples/zero_touch.py, which needs no key at all.
"""

from __future__ import annotations

import os

from anakin import Anakin


def example_wire(client: Anakin) -> None:
    """1. Find a Wire action by intent, then run it. No scraper to write."""
    matches = client.wire.discover("hacker news top stories", auth_mode="none", limit=3)
    print("\n--- wire.discover ---")
    for m in matches:
        print(f"  {m.action_id:<24} catalog={m.catalog_slug}  credits={m.credits}")
    if not matches:
        return
    result = client.wire.run(matches[0].action_id, {"limit": 3})
    print(f"--- wire.run {matches[0].action_id} (credits={result.credits_used}) ---")
    print(str(result.data)[:300], "...")


def example_scrape(client: Anakin) -> None:
    """2. Scrape a single page to markdown."""
    doc = client.scrape("https://example.com", formats=["markdown", "links"])
    print(f"\n--- {doc.url} ({doc.duration_ms} ms, cached={doc.cached}) ---")
    print((doc.markdown or "")[:300], "...")
    for link in (doc.links or [])[:3]:
        print(f"  link: {link.text!r} -> {link.href}")


def example_batch(client: Anakin) -> None:
    """3. Scrape up to 10 URLs in one parallel job."""
    batch = client.scrape_batch(["https://example.com", "https://example.org"])
    print(f"\n--- batch {batch.id} ---")
    for item in batch.results:
        print(f"  [{item.status}] {item.url}  {len(item.markdown or '')} chars")


def example_map(client: Anakin) -> None:
    """4. Discover all URLs on a site."""
    sitemap = client.map("https://docs.python.org/3/", limit=50, depth=2)
    print(f"\n--- map {sitemap.url} ---")
    print(f"Found {sitemap.total_links} URLs. First 5:")
    for link in sitemap.links[:5]:
        print(f"  {link}")


def example_crawl(client: Anakin) -> None:
    """5. Crawl a site and gather markdown for every page."""
    result = client.crawl("https://example.com", max_pages=5, depth=2)
    print(f"\n--- crawl {result.url} ({result.duration_ms} ms) ---")
    print(f"Crawled {result.completed_pages}/{result.total_pages} pages")
    for page in result.pages:
        if page.status == "completed":
            print(f"  ok   {page.url}  ({len(page.markdown or '')} chars markdown)")
        else:
            print(f"  fail {page.url}: {page.error}")


def example_search(client: Anakin) -> None:
    """6. AI-powered web search (synchronous)."""
    result = client.search("best practices for python http clients", limit=3)
    print(f"\n--- search ({len(result.results)} results) ---")
    for r in result.results:
        print(f"  - {r.title}\n    {r.url}")


def main() -> None:
    if not os.environ.get("ANAKIN_API_KEY"):
        raise SystemExit(
            "Set ANAKIN_API_KEY first (free key: https://anakin.io/signup), "
            "or run examples/zero_touch.py which needs no key."
        )

    with Anakin() as client:
        example_wire(client)
        example_scrape(client)
        example_batch(client)
        example_map(client)
        example_crawl(client)
        example_search(client)


if __name__ == "__main__":
    main()
