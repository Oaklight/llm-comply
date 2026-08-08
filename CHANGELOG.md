# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] — 2026-08-09

### Added

- Warning-level validator support for non-fatal compliance issues
- Google GenAI spec compliance validators
- OpenAI Chat Completions advisory warning validators
- Web UI displays warnings alongside pass/fail results
- `deploy-dev` and Docker targets in Makefile

### Changed

- Auth header now follows format switch unless user has customized it
  (same preserve-on-custom logic as URL and model)
- Anthropic error handling test demoted from failure to warning
- Removed unused `LOCAL_WHEEL` Docker build arg

### Fixed

- Strip `/v1` suffix from base URL for Google GenAI `/v1beta` endpoints
- Google GenAI validators accept both camelCase and snake_case field names
- Web UI auth settings preserved when base URL is custom
- Replaced GoatCounter with hits.sh badge only (GoatCounter was blocked by adblockers)
- Improved hits.sh badge visibility with explicit height and margin

## [0.2.0] — 2026-08-01

### Added

- **Web UI** — `llm-comply --web` starts a browser-based compliance tester
  with format selector, live progress, expandable test details, and Stop button
- `/health` endpoint for service monitoring
- `--ignore` flag to filter known schema errors (e.g. `--ignore refusal,verbosity`)
- `--header` / `-H` flag for extra HTTP headers (e.g. `anthropic-version:2023-06-01`)
- `--web`, `--host`, `--port` flags for web UI mode
- Clear button in web UI to wipe credentials
- GoatCounter analytics and hits.sh visit badge
- Dockerfile with multi-stage build, non-root user, read-only fs, all caps dropped
- Render deployment config (`render.yaml`)

### Changed

- Web UI preserves API key, base URL, and model across format switches
  (only auth header and bearer toggle follow the format)
- Failed tests auto-expand in web UI; passed tests show detail on click
- Run Tests button becomes red Stop button during execution with AbortController

### Fixed

- Streaming tests no longer inject `stream: true` in body for Google GenAI
  (uses URL-based streaming via `?alt=sse`)
- SpecLoader handles `None` path gracefully (no spec = no schema validation)

## [0.1.0] — 2026-08-01

### Added

- Initial release — CLI compliance tester for 4 LLM API standards
- **Open Responses** — 12 tests (schema + semantic validation)
- **OpenAI Chat Completions** — 8 tests (schema + semantic validation)
- **Anthropic Messages** — 8 tests (schema + semantic validation)
- **Google GenAI** — 8 tests (semantic validation only)
- Schema validation against pinned OpenAPI specs via jsonschema
- Semantic validators: lifecycle ordering, field presence, streaming events
- `--format` flag to select API standard
- `--filter` to run specific tests by ID
- `--json` output for CI integration
- Rich colored terminal output (optional `[rich]` extra)
- Bundled test image (dice) for vision/multimodal testing
- OpenAPI 3.0 `nullable` → JSON Schema type conversion
- CI workflow (lint + smoke tests across Python 3.10–3.13)
- Release workflow with Trusted Publisher (PyPI)
- Pre-commit hooks (ruff check + ruff format)

[0.3.0]: https://github.com/Oaklight/llm-comply/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Oaklight/llm-comply/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Oaklight/llm-comply/releases/tag/v0.1.0
