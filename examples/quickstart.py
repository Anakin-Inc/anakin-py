"""
Anakin Python SDK — quickstart.

Five copy-paste-able recipes that show the most common workflows:
1. Scrape a single page to markdown
2. Discover all URLs on a site (map)
3. Crawl a site and turn it into a knowledge base
4. AI-powered web search
5. Run a pre-built Wire action

Run:
    pip install anakin-sdk
    ANAKIN_API_KEY=ak-... python examples/quickstart.py
"""

from __future__ import annotations

import os

from anakin import Anakin


def example_scrape(client: Anakin) -> None:
    """1. Scrape a single page to markdown."""
    doc = client.scrape("https://example.com", formats=["markdown"])
    print(f"\n--- {doc.url} ({doc.duration_ms} ms, cached={doc.cached}) ---")
    print((doc.markdown or "")[:300], "...")


def example_map(client: Anakin) -> None:
    """2. Discover all URLs on a site."""
    sitemap = client.map("https://docs.python.org/3/", limit=50, depth=2)
    print(f"\n--- {sitemap.url} ---")
    print(f"Found {sitemap.total_links} URLs. First 5:")
    for link in sitemap.links[:5]:
        print(f"  {link}")


def example_crawl(client: Anakin) -> None:
    """3. Crawl a site and gather markdown for every page."""
    result = client.crawl(
        "https://example.com",
        max_pages=5,
        depth=2,
    )
    print(f"\n--- {result.url} ({result.duration_ms} ms) ---")
    print(f"Crawled {result.completed_pages}/{result.total_pages} pages")
    for page in result.pages:
        if page.status == "completed":
            md_len = len(page.markdown or "")
            print(f"  ✓ {page.url}  ({md_len} chars markdown)")
        else:
            print(f"  ✗ {page.url}  failed: {page.error}")


def example_search(client: Anakin) -> None:
    """4. AI-powered web search (synchronous, 3 credits)."""
    result = client.search("best practices for python http clients", limit=3)
    print(f"\n--- search ({len(result.results)} results) ---")
    for r in result.results:
        print(f"  • {r.title}")
        print(f"    {r.url}")


def example_wire(client: Anakin) -> None:
    """
    5. Run a Wire action.

    Find action IDs in the Wire dashboard at https://anakin.io/holocron.
    Replace `action_id` and `params` with real values from a connected account.
    """
    # Example shape — uncomment and fill in:
    #
    # result = client.wire(
    #     action_id="li_profile_scrape",
    #     params={"profile_url": "https://www.linkedin.com/in/example"},
    # )
    # print(f"\n--- wire (status={result.status}, credits={result.credits_used}) ---")
    # print(result.data)
    print("\n--- wire ---")
    print("(skipped — uncomment in source and provide a valid action_id)")


def main() -> None:
    if not os.environ.get("ANAKIN_API_KEY"):
        raise SystemExit("Set ANAKIN_API_KEY in your environment first.")

    with Anakin() as client:
        example_scrape(client)
        example_map(client)
        example_crawl(client)
        example_search(client)
        example_wire(client)


if __name__ == "__main__":
    main()
