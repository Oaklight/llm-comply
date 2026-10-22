# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.6.0] — 2026-10-21

### Added

- Checked-in schema verdict fixtures (`tests/fixtures/schema_verdicts.json`), run by `make verify`. Every bundled spec carries valid and invalid representative payloads, so a spec refresh that flips a validation verdict fails CI instead of relying on ad-hoc reviewer differentials.
- Spec-target manifest (`src/llm_comply/specs/manifest.json`) recording each bundled spec's version, schema count, SHA-256, upstream source, validation mode, and refresh date. It is committed, so every master commit and release tag records which upstream spec versions it targets.
- `llm-comply specs` command with `--json` and `--check` (CI drift detection).
- `GET /api/specs` endpoint; the web UI footer shows the active spec targets.
- `llm-comply update-spec --all` and a weekly `spec-update` workflow that refreshes every upstream-backed format and opens a PR when bundled specs change; the workflow shares CI's new `make verify` gate and proposes successful refreshes even if one upstream fails.
- **OpenAI Responses API** format (`openai_responses`, alias `openai-responses`) with 12 tests. Its bundled spec is extracted from the same upstream OpenAI OpenAPI document as `chat_completions`: the `/responses` paths plus their transitive `$ref` closure (357 schemas, 6 paths). SSE events resolve to their concrete event schema dynamically, with `ResponseStreamEvent` as the fallback.

### Changed

- Chat Completions: `chat_has_tool_calls` now validates each call against the spec's two variants — `function` (`id`, `function.name`/`arguments`) and `custom` (`id`, `custom.name`/`input`) — instead of only checking that the array is non-empty; the tool-calling test additionally requires a `function` call so a provider ignoring the offered tool type still fails. `chat_has_reasoning_summary` is renamed to `chat_has_reasoning_tokens` to match what it checks. Added developer-role, structured-output, web-search, and audio-output tests (9 to 13), with structured output validated against the requested JSON schema; the audio test skips on models without audio support.
- Open Responses: `has_usage` now checks all five required `Usage` fields and their nested details, and `compact_object` validates the full `CompactResource` shape (`object`, `id`, `output`, `created_at`, `usage`). The compact checks remain advisory, so their findings are reported as warnings. Added `multi-turn-tool-use`, `structured-output`, and `file-input` tests (13 to 16, and the shared `file-input` also raises `openai_responses` to 12); structured output is validated against the requested JSON schema, not just parseability, and file input sends inline base64 `input_file` content whose answer the output must contain.
- Web UI: `--tls-cert` / `--tls-key` serve the UI over HTTPS (TLS 1.2 minimum), keeping the API key the browser submits off the wire in clear text.
- Web UI: request logging now records time-to-first-byte and total transfer time via `on_response_started` / `on_response_completed`; SSE runs are no longer logged at ~0 ms. `GET /health` exposes cumulative counters (`runs_started`, `runs_completed`, `runs_aborted`, `runs_failed`, `requests_completed`, `client_disconnects`): `runs_started` reconciles with the terminal counters, and a stream that raises increments `runs_failed` and sends a final `event: error` frame. `streaming_disconnects` was renamed to `client_disconnects` because it counts every aborted response, not only SSE.
- Web UI: `/api/run/stream` emits `: ping` heartbeats while a test runs and stops scheduling tests when the browser disconnects.
- Vendored zerodep modules updated via PR #30: httpclient 0.5.0 → 0.5.1, httpserver 0.4.0 → 0.5.1, sse 0.3.3 → 0.3.4.
- `chat_completions` streaming tests now validate every SSE chunk against `CreateChatCompletionStreamResponse` instead of leaving stream validation disabled. A new `TestCase.stream_schema_name` field covers APIs whose events have no `type` field; chunks that do not match the spec now fail. Mid-stream `{"error": ...}` payloads are reported as `stream error: <message>` instead of a chunk-schema failure.
- Canonical `--format` names now match llm-rosetta: `open_responses` (default), `chat_completions`, `messages`, `google_generate`, `google_interactions`. All v0.5.0 names (`open-responses`, `openai-chat`, `anthropic`, `google-genai`, `google-interactions`) remain accepted as aliases.
- Refreshed the bundled OpenAI Chat Completions spec from upstream: 477 → 2094 schemas, 99 → 230 paths (OpenAPI 3.1.0). This adds `ChatCompletionModeration`, current `ReasoningEffort` values (`none`, `minimal`, `xhigh`, `max`), `Reasoning.mode`/`context`, and the streaming response schemas.
- Refreshed the bundled Open Responses spec from upstream (138,849 → 132,236 bytes). Version (`2026-04-24`), 108 schemas and 2 paths are unchanged; the delta collapses redundant `oneOf`/`allOf` wrappers around `$ref`s to direct references, with no required-field or enum changes. Validation verdicts are unchanged, but some schema-error text becomes more specific (e.g. `'type' is a required property` instead of `is not valid under any of the given schemas`), so `--ignore` patterns matching the old generic text may need updating.
- Refreshed the bundled Anthropic Messages spec from the official SDK's `scripts/mock-spec.json.gz` artifact (the Python and TypeScript copies are byte-identical): 928 → 2008 schemas, 89 → 224 paths. `Message` now requires `diagnostics` (nullable) and `Usage` requires `speed`; the spec carries no `info.version`, so the manifest records `unknown`. Added a `tool_result` round-trip test, web-search and code-execution server-tool tests, a structured-output test, `/messages/count_tokens`, `max_tokens` / `stop_sequence` stop-reason tests, a prompt-caching test, a document (PDF) input test, and a streaming tool-use test that validates `input_json_delta` per content block against the tool input schema (9 to 19); the server-tool tests are optional and skip when a provider rejects the built-in tool, and structured output is validated against the requested JSON schema.
- Added a bundled `google_generate.json` from Google's official OpenAPI discovery document: 252 schemas, 71 paths (`v1beta`). `generateContent` and `streamGenerateContent` responses now validate against `GenerateContentResponse`, covering fields the semantic validators never inspected (`safetyRatings`, `citationMetadata`, `groundingMetadata`, `promptFeedback`, and the rest of the response shape). Added a structured-output test (9 to 10) with `responseMimeType: application/json` and `responseSchema`, plus optional grounding and code-execution tests (10 to 12).
- Refreshed `google_interactions.json` from the official Interactions API document: 186 → 213 schemas, 15 → 20 paths (`v1beta`); runtime validation remains semantic. Added built-in tool tests for Google Search, code execution, Google Maps, and URL context (9 to 13); these are optional and report skipped when a provider does not support the tool.
- `llm-comply update-spec` now takes `--format` or `--all` and supports all six formats; it validates the fetched document before writing and updates the manifest automatically.
- Format definitions are centralized in `llm_comply/formats.py`, removing duplicated mappings across the CLI, web UI, test registry, and spec loader.

### Fixed

- Chat Completions: `usage.completion_tokens_details` and `usage.prompt_tokens_details` sub-fields are now inspected (advisory; present values must be integers), and the error-handling test validates the error body against the spec's `ErrorResponse` instead of only checking the HTTP status.
- Open Responses streaming now requires at least one `response.output_text.delta` event carrying non-empty text. Missing, non-string, or whitespace-only deltas fail with an explicit error instead of passing on lifecycle alone.
- `openai_responses` no longer rejects production payloads for omitting `access_programs`. The field stays in the spec but is dropped from `Response.required` during extraction, so a refresh cannot reintroduce the false positive (#36).
- Anthropic streaming now checks that every `content_block_start` has a matching `content_block_stop` with the same index, so truncated or mis-bracketed streams fail instead of passing the lifecycle check.
- Open Responses and OpenAI Responses error-handling tests now validate the 4xx body (`responses_error_body`) instead of only the HTTP status: the spec's flat `ErrorPayload` or the common `{"error": {...}}` envelope must carry a non-empty message.
- Google validators now report malformed `candidates` / `content.parts` containers and non-object `usageMetadata` instead of raising `AttributeError`. Because the runner shares one `try` across validators, the crash previously masked every later finding for the same response.
- Non-streaming Chat Completions tests now accept a message with `tool_calls`, `function_call`, `refusal`, `reasoning_content`, or `reasoning` instead of requiring `content` or `tool_calls`. The message-payload rules are shared with the streaming delta validator, though the emptiness rule differs deliberately: a non-streaming message with `content: ""` is accepted (present but empty), while a stream needs at least one truthy delta.
- `chat-streaming-response` no longer rejects correct streams that carry only tool calls, legacy function calls, refusals, or reasoning: the delta validator accepts `delta.content`, `delta.tool_calls`, `delta.function_call`, `delta.refusal`, `delta.reasoning_content`, and `delta.reasoning`. Empty or absent deltas still fail, and the error message names every accepted field.
- Streaming payloads that are not valid JSON, or parse to something other than an object, now fail with a clear diagnosis instead of being silently skipped or raising an attribute error. Bare and whitespace-only `data:` lines are treated as heartbeats and ignored. Clarifies the "every chunk is validated" guarantee.
- Per-format transport defaults: `--format messages` now uses the `x-api-key` header and sends `anthropic-version: 2023-06-01` automatically, and the Google formats use `x-goog-api-key`, instead of requiring `--auth-header`, `--no-bearer`, and `-H` on every run. A new `--bearer` counteracts `--no-bearer`, so the pre-0.6 `Authorization: Bearer` arrangement for a Messages gateway is still expressible, and the web UI omits fields left at their format default so the server-side resolution applies. Explicit flags and `-H` values still override the defaults; `-H` can no longer replace the resolved credential header.
- Schema validation no longer rejects valid `ReasoningEffort` values (`none`, `minimal`, `xhigh`, `max`) that the stale bundled spec omitted.
- Manifest regeneration tolerates configured specs that are not bundled yet, and `update-spec --all` writes the manifest once after all fetches instead of after each one.
- `update-spec` compares specs canonically (sorted keys, volatile metadata such as `info.x-google-revision` dropped) before writing. Google's discovery endpoint re-serializes every response with a different key order and revision marker, which previously produced a spurious diff on every refresh.
- Web UI: `--tls-cert` / `--tls-key` with an empty value are treated as paths rather than as "TLS disabled", TLS flags are rejected without `--web`, and the success banner is no longer printed before the certificate is loaded.
- Web UI: a failed stream ends normally after its terminal `event: error` frame, so a reverse proxy sees a complete response. Tests cover the HTTPS handshake, `serve()` forwarding the TLS context, the failure/abort terminal counters, and the counter placement before the first chunk.

## [0.5.0] — 2026-09-12

### Added

- Nuitka binary build CI — multi-platform compilation (linux x86_64/arm64 native + musl, macOS arm64, Windows x86_64)
- Minimal Docker images from Nuitka binaries (Alpine ~21 MB, busybox:glibc ~25 MB)
- `docker.yml` workflow for multi-arch binary Docker image builds
- Makefile targets: `build-binary`, `build-binary-musl`, `build-docker-alpine`, `build-docker-glibc`
- SSE streaming endpoint (`POST /api/run/stream`) for real-time test progress in web UI
- CORS headers and request logging middleware (`before_request`/`after_request`)
- Structured JSON error handlers for 400, 404, 405, 500, and unhandled exceptions
- Startup/shutdown lifecycle hooks — preload specs on startup, clean up connection pool on shutdown
- HTTP connection pooling via `httpclient.Client` for TCP reuse across test runs

### Changed

- Release workflow now chains: PyPI publish → Nuitka binaries → Docker images → GitHub Release with binaries attached
- Vendored zerodep modules updated: httpclient 0.4.5 → 0.5.0, httpserver 0.2.1 → 0.4.0, sse 0.3.2 → 0.3.3
- Bilingual README (English + 中文) with language switcher; `README.md` is now a symlink to `README_en.md`
- Web UI footer now shows "by Oaklight" attribution
- Web UI frontend rewritten to use SSE streaming (single request) instead of per-test POST loop
- Deduplicated `_get_tests()` into shared `tests/__init__.py`; removed 72-line `_run_single_test()` from web.py
- Documentation: clarify distinction between Google GenAI generateContent and Interactions APIs

### Fixed

- Address review feedback from PRs #14, #16, #18
- Replace unicode theme icons with inline SVG sun/moon for cross-platform consistency

## [0.4.1] — 2026-09-03

### Fixed

- Fix JSONResponse error-path crash in web UI (`status` → `status_code` keyword argument)

## [0.4.0] — 2026-08-29

### Added

- **Google Interactions API** compliance test suite
- Reasoning/thinking compliance tests for all four API formats
- `--delay` option for rate-limited APIs
- Web UI redesign with Google Interactions format support

### Fixed

- Tighten `interactions_has_model_output` to verify text in content blocks
- Web UI UX polish — expand only after test run, privacy hint, theme icon

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

[0.6.0]: https://github.com/Oaklight/llm-comply/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Oaklight/llm-comply/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/Oaklight/llm-comply/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Oaklight/llm-comply/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Oaklight/llm-comply/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Oaklight/llm-comply/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Oaklight/llm-comply/releases/tag/v0.1.0
