# Changelog

All notable changes to `anakin-sdk` are documented here. The project follows
[Semantic Versioning](https://semver.org/); while in `0.x`, minor versions may
contain breaking changes (called out below).

## [0.2.0] - 2026-10-09

Brings the SDK up to the full public API and the Anakin MCP tool surface.

### Added
- **Async client**: `AsyncAnakin`, with the same methods as `Anakin`.
- **Keyless "Zero Touch" mode**: `Anakin()` with no key works for `scrape()`, `wire.discover()`, `wire.catalogs()`, `wire.catalog()` and `wire.zero_touch()`. Other methods raise `ConfigurationError` locally, with a signup link.
- **Wire namespace** (`client.wire.*`): `discover`, `catalogs`, `catalog`, `run`, `zero_touch`, `get_job`, `download` (file results), `identities`, `identity`, `login`, `verify_credential`, `build`, `builds`, `get_build`, and `sources.*` (1Password / Azure Key Vault identity sources). `wire.run` supports `credential_id`, `identity_id`, `webhook_url` and sync-mode actions. `client.wire(action_id, params)` still works.
- **Scraping**: `scrape_batch()` (up to 10 URLs), `download_screenshot()`, and `scrape()` options `output_schema`, `actions` (browser actions), `webhook_url` and `inline`.
- **Monitoring** (`client.monitors.*`): page / site / wire monitors, controls, changes, snapshots, alerts and deliveries.
- **AI Visibility** (`client.ai_visibility.*`): `search`, `get`, `list`, `sources`, `retry`.
- **Webhooks** (`client.webhooks.*`) plus `anakin.verify_webhook_signature()`.
- **Browser API**: `client.browser.connect_url()`, `client.browser.headers()`, `client.browser.recordings`.
- `wait=False` on every job method (returns immediately, `status="pending"`), and `get_scrape`, `get_scrape_batch`, `get_map`, `get_crawl`, `get_agentic_search` to fetch jobs later.
- `webhook_url=` on scrape, scrape_batch, map, crawl, agentic_search and wire.run.
- `crawl(session_name=...)`.
- Errors: `ConflictError` (409), `UnprocessableEntityError` (422), `WireAuthExpiredError`, `WireLoginError`, and `AnakinPermissionError` (the new name for `PermissionError`). `JobFailedError` and `JobTimeoutError` now carry `.job_id`, and `InsufficientCreditsError` adds `.signup_url` / `.trial_credits_remaining`.
- `py.typed` marker, so type checkers now see the SDK's annotations.

### Changed
- Wire now calls `/v1/wire/task` and `/v1/wire/jobs/{id}` (was the legacy `/v1/holocron/*`).
- HTTP 500 is retried with backoff, as the API docs recommend. A `Retry-After` longer than 60s is raised immediately instead of slept on.
- `agentic_search()` waits at least 600s by default (it typically takes 1-5 minutes).
- `WireAuthRequiredError.connect_url` is now an absolute URL.
- Models keep unknown API fields (`model.model_extra`), and `status` fields are plain strings, so new API fields or statuses no longer raise validation errors.
- A missing job ID raises `AnakinError` instead of `RuntimeError`.

### Fixed
- `Document.links` / `Document.images` are now `list[Link]` / `list[Image]` (`{href, text}` / `{src, alt}`), matching the API. Requesting `formats=["links"]` or `["images"]` previously failed validation.
- PyPI trusted-publishing config and docs referenced the old `anakin` project name.

### Breaking
- `Document.links` / `.images` element type (see Fixed).
- `WireResult.data` is typed `Any` (actions can return lists), and `WireResult.job_id` is optional.
- `Anakin()` with no key no longer raises at construction (keyless mode); keyed calls raise `ConfigurationError` instead.
- `anakin.PermissionError` is still importable but is no longer in `__all__`.

## [0.1.0]

Initial release: `scrape`, `map`, `crawl`, `search`, `agentic_search`, `wire`, `sessions`, `countries`.
