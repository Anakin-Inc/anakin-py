"""
Async client: scrape many pages concurrently.

Run:
    ANAKIN_API_KEY=ak-... python examples/async_crawl.py
"""

from __future__ import annotations

import asyncio

from anakin import AsyncAnakin

URLS = [
    "https://example.com",
    "https://example.org",
    "https://www.python.org",
]


async def main() -> None:
    async with AsyncAnakin() as client:
        sitemap = await client.map("https://docs.python.org/3/", limit=20)
        urls = URLS + sitemap.links[:5]
        docs = await asyncio.gather(
            *(client.scrape(u) for u in urls), return_exceptions=True
        )
        for url, doc in zip(urls, docs, strict=True):
            if isinstance(doc, BaseException):
                print(f"fail {url}: {doc}")
            else:
                print(f"ok   {url}: {len(doc.markdown or '')} chars")


if __name__ == "__main__":
    asyncio.run(main())
