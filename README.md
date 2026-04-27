# anakin

[![PyPI version](https://img.shields.io/pypi/v/anakin.svg)](https://pypi.org/project/anakin/)
[![Python Version](https://img.shields.io/pypi/pyversions/anakin.svg)](https://pypi.org/project/anakin/)
[![License](https://img.shields.io/pypi/l/anakin.svg)](https://github.com/Anakin-Inc/anakin-py/blob/main/LICENSE)

Official Python SDK for [Anakin](https://anakin.io) — web scraping, crawling, search, and Wire actions.

> **Status: alpha (v0.1.x).** Public API may change between minor versions until v1.0.

## Install

```bash
pip install anakin
```

## Quickstart

```python
from anakin import Anakin

client = Anakin(api_key="ak-...")  # or set ANAKIN_API_KEY env var

# Scrape a single URL
doc = client.scrape("https://example.com", formats=["markdown"])
print(doc.markdown)

# Discover URLs on a site
sitemap = client.map("https://example.com", limit=200)
print(sitemap.links)

# Crawl pages and get content
crawl = client.crawl("https://example.com", max_pages=20)
for page in crawl.pages:
    print(page.url, len(page.markdown or ""))
```

The SDK polls long-running jobs internally — you get the final result back from a single sync method call. No job IDs to manage, no polling loops to write.

## Configuration

```python
client = Anakin(
    api_key="ak-...",          # or ANAKIN_API_KEY env var
    timeout=60.0,              # per-request HTTP timeout
    max_retries=4,             # retries on 429/5xx
    poll_interval=1.0,         # initial polling delay
    poll_max_interval=10.0,    # max polling delay
    poll_timeout=300.0,        # total wait before JobTimeoutError
)
```

## Errors

```python
from anakin import (
    AnakinError,                # base for everything below
    AuthenticationError,        # bad/missing API key
    InsufficientCreditsError,   # 402 (exposes .balance, .required)
    InvalidRequestError,        # 400
    JobFailedError,             # job came back with status="failed"
    JobTimeoutError,            # poll_timeout exceeded
    RateLimitError,             # 429 (exposes .retry_after)
    ServerError,                # 5xx after retries
    NetworkError,               # DNS/connection/timeout
)
```

## Development

```bash
pip install -e ".[dev]"
ruff check .
mypy src/
pytest
```

## License

Apache 2.0. See [LICENSE](LICENSE).
