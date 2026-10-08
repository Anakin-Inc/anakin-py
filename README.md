# anakin-sdk

[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-blue.svg)](https://www.python.org/downloads/)
[![Type checked](https://img.shields.io/badge/type%20checked-mypy%20strict-1f5082.svg)](http://mypy-lang.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)

Official Python SDK for [Anakin](https://anakin.io), the API layer for the web. Turn any website into JSON or Markdown: scrape, crawl, search, run pre-built **Wire** actions on hundreds of sites, monitor pages for changes, and see what AI engines say about you.

> **Status: alpha (v0.x).** The public API may change between minor versions until v1.0. See [CHANGELOG.md](CHANGELOG.md).

## Install

```bash
pip install anakin-sdk
```

The PyPI name is `anakin-sdk`; the import name is `anakin`.

## Try it with no API key

```python
from anakin import Anakin

client = Anakin()  # no key: keyless "Zero Touch" mode
print(client.scrape("https://example.com").markdown)
```

Scraping and read-only Wire actions work without an account on a free per-IP allowance. For crawl, search, monitors and everything else, [get a free key (300 credits, no card)](https://anakin.io/signup) and set `ANAKIN_API_KEY`. The same code keeps working.

## Quickstart

```python
from anakin import Anakin

client = Anakin(api_key="ak-...")  # or set ANAKIN_API_KEY

# Wire: structured data from a known site, no scraper to maintain
actions = client.wire.discover("top phones on walmart")
result = client.wire.run(actions[0].action_id, {"query": "phones"})
print(result.data)

# Scrape a page (or up to 10 at once with scrape_batch)
doc = client.scrape("https://example.com", formats=["markdown", "links"])
print(doc.markdown)

# Crawl a site into a knowledge base
crawl = client.crawl("https://docs.example.com", max_pages=50)
for page in crawl.pages:
    print(page.url, len(page.markdown or ""))

# Deep research with structured output (1-5 min)
report = client.agentic_search("Compare the top 5 vector databases", schema={...})
print(report.generated_json.summary)
```

Long-running jobs are polled for you: one call returns the final result. Pass `wait=False` (optionally with `webhook_url=`) to get the job back immediately, then fetch it with `get_scrape()`, `get_crawl()` and so on.

## What's in the box

| Product | Methods |
|---|---|
| **Wire** (pre-built site actions) | `wire.discover`, `wire.catalogs`, `wire.catalog`, `wire.run` / `wire(...)`, `wire.zero_touch`, `wire.get_job`, `wire.download`, `wire.identities`, `wire.login`, `wire.verify_credential`, `wire.build`, `wire.get_build`, `wire.sources.*` |
| **URL Scraper** | `scrape` (formats, AI JSON extraction, `output_schema`, browser `actions`), `scrape_batch`, `get_scrape`, `download_screenshot` |
| **Map / Crawl** | `map`, `crawl`, `get_map`, `get_crawl` |
| **Search** | `search` (sync), `agentic_search` (deep research), `get_agentic_search` |
| **Website Monitoring** | `monitors.create` (page / site / wire scope), `list`, `get`, `update`, `pause`, `resume`, `run_now`, `changes`, `snapshots`, `test_alert`, `deliveries`, ... |
| **AI Visibility** | `ai_visibility.search` (ChatGPT, Gemini, Google AI Overview side by side), `sources`, `list`, `retry` |
| **Webhooks** | `webhooks.create`, `list`, `update`, `delete`, `test`, `deliveries`, `resend`, `signing_secret`, plus `verify_webhook_signature()` |
| **Browser** | `sessions.*` (saved logins), `browser.connect_url()` for Playwright/Puppeteer, `browser.recordings` |

Runnable recipes are in [`examples/`](examples): [quickstart](examples/quickstart.py), [zero_touch](examples/zero_touch.py), [wire_actions](examples/wire_actions.py), [price_monitor](examples/price_monitor.py), [webhook_receiver](examples/webhook_receiver.py), [async_crawl](examples/async_crawl.py), [agentic_extraction](examples/agentic_extraction.py).

## Wire in 30 seconds

```python
matches = client.wire.discover("linkedin profile work history")
detail = client.wire.catalog(matches[0].catalog_slug)       # params, auth, credit cost

# Actions with auth_mode="required" need a credential_id:
login = client.wire.login(detail.catalog.slug, {"email": "...", "password": "..."})  # never stored
result = client.wire.run(matches[0].action_id, {...}, credential_id=login.credential_id)
```

No action for your site? `client.wire.build("https://site.com", "extract product name and price")` asks Wire to generate one.

## Monitoring

```python
monitor = client.monitors.create(
    "https://example.com/product/123",
    interval_minutes=60,
    watch_mode="specific_data",
    output_schema={"type": "object", "properties": {"price": {"type": "number"}}},
    ai_mode=True,
    alert_webhook_url="https://your-app.com/hooks/anakin",
)
print(monitor.alert_webhook_secret)  # store it now; it's only returned on create
```

## Webhooks

```python
from anakin import verify_webhook_signature

ok = verify_webhook_signature(
    raw_body,                                   # exact bytes, not re-serialised JSON
    headers["X-Anakin-Signature"],
    secret,
    timestamp=headers["X-Anakin-Timestamp"],
    tolerance=300,
)
```

## Browser API (Playwright)

```python
browser = await playwright.chromium.connect_over_cdp(
    client.browser.connect_url(country="gb", session_name="my-login", record=True),
    headers=client.browser.headers(),
)
```

## Async

```python
from anakin import AsyncAnakin

async with AsyncAnakin() as client:
    docs = await asyncio.gather(*(client.scrape(u) for u in urls))
```

`AsyncAnakin` has exactly the same methods as `Anakin`, awaited.

## Configuration

```python
client = Anakin(
    api_key="ak-...",          # or ANAKIN_API_KEY env var; omit for keyless mode
    timeout=60.0,              # per-request HTTP timeout
    max_retries=4,             # retries on 429 / 5xx / network errors
    poll_interval=1.0,         # initial polling delay
    poll_max_interval=10.0,    # max polling delay
    poll_timeout=300.0,        # total wait before JobTimeoutError (agentic search: min 600s)
)
```

## Errors

```python
from anakin import (
    AnakinError,                # base for everything below
    ConfigurationError,         # e.g. method needs an API key and none is set
    AuthenticationError,        # 401: bad/missing API key
    WireAuthRequiredError,      #   connect the site account at .connect_url
    WireAuthExpiredError,       #   saved site login expired; wire.login() again
    WireLoginError,             # wire.login ran but sign-in failed (.code: BAD_PASSWORD, ...)
    InsufficientCreditsError,   # 402 (.balance, .required, .signup_url in keyless mode)
    AnakinPermissionError,      # 403
    NotFoundError,              # 404
    ConflictError,              # 409 (session in use, ACTION_EXISTS, ...)
    UnprocessableEntityError,   # 422 (e.g. session not saved yet)
    InvalidRequestError,        # 400
    RateLimitError,             # 429 after retries (.retry_after)
    ServerError,                # 5xx after retries
    NetworkError,               # DNS / connection / timeout
    JobFailedError,             # job finished with status="failed" (.job_id)
    JobTimeoutError,            # poll_timeout exceeded (.job_id: fetch it later)
)
```

Every error carries `.status_code`, `.code`, `.request_id` (include it when contacting support) and the raw `.body`.

## Pricing and limits

Credit costs per product are on the [pricing page](https://anakin.io/docs/documentation/pricing); rate limits are in the [docs](https://anakin.io/docs/documentation/rate-limits). Full API reference: [anakin.io/docs](https://anakin.io/docs/api-reference).

## Development

```bash
pip install -e ".[dev]"
ruff check .
mypy src/
pytest
```

`src/anakin/async_client.py` is generated from `src/anakin/client.py`. After editing the sync client, run `python scripts/generate_async.py` (a test fails if you forget).

## License

Apache 2.0. See [LICENSE](LICENSE).
