# llm-comply

**[中文](README_zh.md) | English**

[![PyPI](https://img.shields.io/pypi/v/llm-comply)](https://pypi.org/project/llm-comply/)
[![CI](https://github.com/Oaklight/llm-comply/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/llm-comply/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/llm-comply)](https://pypi.org/project/llm-comply/)
[![License](https://img.shields.io/github/license/Oaklight/llm-comply)](https://github.com/Oaklight/llm-comply/blob/master/LICENSE)

Multi-format LLM API compliance testing tool — validates endpoints against official specs for **OpenAI Chat Completions**, **Open Responses**, **Anthropic Messages**, **Google GenAI generateContent**, and **Google GenAI Interactions**.

**[Try it online →](https://llm-comply.service.oaklight.top)**

## Install

```bash
pip install llm-comply
# For colored terminal output:
pip install llm-comply[rich]
```

## Quick Start

```bash
# Open Responses (default)
llm-comply -u https://api.openai.com/v1 -k $OPENAI_API_KEY -m gpt-4o-mini

# OpenAI Chat Completions
llm-comply --format chat_completions -u https://api.openai.com/v1 -k $OPENAI_API_KEY -m gpt-4o-mini

# OpenAI Responses API
llm-comply --format openai_responses -u https://api.openai.com/v1 -k $OPENAI_API_KEY -m gpt-4o-mini

# Anthropic Messages
llm-comply --format messages -u https://api.anthropic.com/v1 -k $KEY -m claude-haiku-4-5

# Google GenAI — generateContent
llm-comply --format google_generate -u https://generativelanguage.googleapis.com -k $KEY \
  -m gemini-2.5-flash

# Google GenAI — Interactions
llm-comply --format google_interactions -u https://generativelanguage.googleapis.com -k $KEY \
  -m gemini-2.5-flash
```

Auth headers and defaults are selected per format: `Authorization` + `Bearer` for the
OpenAI-facing formats, `x-api-key` for Messages (with `anthropic-version`), and
`x-goog-api-key` for Google. `--auth-header` selects the header name only; the
prefix follows `--bearer`/`--no-bearer` when given, otherwise the format default.
`-H name:value` overrides or adds headers, but cannot replace the resolved
credential header.

## Options

```
-u, --base-url URL     API base URL (required)
-k, --api-key KEY      API key (or set OPENRESPONSES_API_KEY env)
-m, --model MODEL      Model name (default: gpt-4o-mini)
--format FORMAT        API format: open_responses, openai_responses,
                       chat_completions, messages,
                       google_generate, google_interactions
                       (legacy aliases: open-responses, openai-responses,
                       openai-chat, anthropic, google-genai,
                       google-interactions)
-f, --filter IDS       Comma-separated test IDs to run
-i, --ignore PATTERNS  Ignore errors matching substrings (e.g. refusal,verbosity)
-H, --header K:V       Extra headers (e.g. anthropic-version:2023-06-01)
--auth-header NAME     Auth header name (default: per format: Authorization,
                       x-api-key, or x-goog-api-key)
--bearer               Prepend "Bearer " to the API key (overrides the format default)
--no-bearer            Don't prepend "Bearer " to API key (overrides the format default)
-v, --verbose          Show request/response on failure
--json                 JSON output for CI
--list                 List available test IDs
```

## Spec Targets

Bundled spec versions are tracked in
[`src/llm_comply/specs/manifest.json`](src/llm_comply/specs/manifest.json) and
rendered by `llm-comply specs`. The manifest is committed, so every master
commit and release tag records exactly which upstream spec version it targets.

| Format | Bundled spec | Version | Schemas | Validation | Refreshed |
|--------|--------------|---------|--------:|------------|-----------|
| `open_responses` | `openresponses.json` | 2026-04-24 | 108 | Schema | 2026-10-21 |
| `openai_responses` | `openai_responses.json` | 2.3.0 | 357 | Schema | 2026-10-21 |
| `chat_completions` | `openai_chat.json` | 2.3.0 | 2094 | Schema | 2026-10-21 |
| `messages` | `anthropic.json` | unknown (no version in spec) | 2008 | Schema | 2026-10-21 |
| `google_generate` | `google_generate.json` | v1beta | 252 | Semantic | 2026-10-21 |
| `google_interactions` | `google_interactions.json` | v1beta | 213 | Semantic | 2026-10-21 |

```bash
llm-comply specs            # human-readable table
llm-comply specs --json     # machine-readable manifest
llm-comply specs --check    # CI: fail if the manifest drifts from bundled files
```

Refresh bundled specs from their upstream sources (the manifest is updated too):

```bash
llm-comply update-spec --all                     # every upstream-backed format
llm-comply update-spec --format open_responses   # a single format
llm-comply update-spec --format messages         # Anthropic Messages
```

`messages` is pulled from the official Anthropic SDK's bundled
`scripts/mock-spec.json.gz` (the Python and TypeScript copies are byte-identical).
`chat_completions` and `openai_responses` come from the same upstream OpenAI
OpenAPI document; the Responses spec bundles only the `/responses` paths and
their transitive `$ref` closure.
Google specs come from the official OpenAPI discovery document
(`google_generate`) and the Interactions API document (`google_interactions`).
`google_generate` responses validate against `GenerateContentResponse`; the
Interactions spec is bundled for version tracking while runtime validation
stays semantic. The discovery schemas declare types and enums but no
`required` arrays, so checking that fields are present remains the semantic
validators' job.
A weekly `spec-update` workflow runs `update-spec --all` and opens a PR when any
upstream spec changes.

## Web UI

```bash
llm-comply --web                                      # http://127.0.0.1:8090
llm-comply --web --host 0.0.0.0 \
  --tls-cert /path/cert.pem --tls-key /path/key.pem   # https://0.0.0.0:8090
```

The UI accepts an API key in the browser, so serve it over TLS whenever it is
reachable beyond localhost. `--tls-cert` and `--tls-key` must be provided
together; TLS 1.2 is the minimum.

`GET /health` returns the version and cumulative counters (`runs_started`,
`runs_completed`, `runs_aborted`, `runs_failed`, `requests_completed`,
`client_disconnects`), so `runs_started` reconciles with the terminal counters.
A stream that raises sends a final `event: error` frame and increments
`runs_failed`. Closing the browser tab aborts the run before the next test
starts; the test already in flight still finishes because its API call has been
sent.

## Docker

```bash
docker run -p 8090:8090 oaklight/llm-comply:latest
```

Reference `compose.yaml` for production deployment:

```yaml
services:
  llm-comply:
    image: oaklight/llm-comply:latest
    container_name: llm-comply
    restart: unless-stopped
    ports:
      - 127.0.0.1:8090:8090
    read_only: true
    tmpfs:
      - /tmp:size=64m,exec
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    mem_limit: 256m
    cpus: 0.5
```

> **Note**: The binary image uses Nuitka onefile format, which extracts to `/tmp` at startup. The `tmpfs` mount with `exec` is required when using `read_only: true`.

## Test Coverage

| Format | Tests | What's Validated |
|--------|:-----:|-----------------|
| `open_responses` | 16 | Schema + semantic (lifecycle, phases, compaction, multi-turn tools, structured output, file input, thinking) |
| `openai_responses` | 12 | Schema + semantic (lifecycle, streaming events, tools, reasoning, file input) |
| `chat_completions` | 13 | Schema + semantic (choices, finish_reason, delta, stream chunks, developer role, structured output, web search, audio output, error envelope) |
| `messages` | 13 | Schema + semantic (content blocks, stop_reason, thinking, tool_result round-trip, web search, code execution, structured output) |
| `google_generate` | 12 | Schema + semantic (candidates, parts, finishReason, safetyRatings, thinking, structured output, grounding, code execution) |
| `google_interactions` | 13 | Semantic only (steps, model_output, thinking, google search, code execution, maps, url context) |

`chat-audio-output` treats the model name as a capability hint: it skips unless
the name contains `audio` (case-insensitive), so deployments with role-named
audio aliases should run the test with a name that includes it.

The built-in Google Interactions tool tests are optional: a provider that does
not support a tool and answers with 400, 404, 405, 422, or 501 reports the
test as skipped instead of failed. The Google GenAI grounding and
code-execution tests follow the same rule.

## License

MIT
