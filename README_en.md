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

# Anthropic Messages
llm-comply --format messages -u https://api.anthropic.com/v1 -k $KEY -m claude-haiku-4-5 \
  --auth-header x-api-key --no-bearer -H anthropic-version:2023-06-01

# Google GenAI — generateContent
llm-comply --format google_generate -u https://generativelanguage.googleapis.com -k $KEY \
  -m gemini-2.5-flash --auth-header x-goog-api-key --no-bearer

# Google GenAI — Interactions
llm-comply --format google_interactions -u https://generativelanguage.googleapis.com -k $KEY \
  -m gemini-2.5-flash --auth-header x-goog-api-key --no-bearer
```

## Options

```
-u, --base-url URL     API base URL (required)
-k, --api-key KEY      API key (or set OPENRESPONSES_API_KEY env)
-m, --model MODEL      Model name (default: gpt-4o-mini)
--format FORMAT        API format: open_responses, chat_completions, messages,
                       google_generate, google_interactions
                       (legacy aliases: open-responses, openai-chat, anthropic,
                       google-genai, google-interactions)
-f, --filter IDS       Comma-separated test IDs to run
-i, --ignore PATTERNS  Ignore errors matching substrings (e.g. refusal,verbosity)
-H, --header K:V       Extra headers (e.g. anthropic-version:2023-06-01)
--auth-header NAME     Auth header name (default: Authorization)
--no-bearer            Don't prepend "Bearer " to API key
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
| `open_responses` | `openresponses.json` | 2026-04-24 | 108 | Schema | 2026-08-01 |
| `chat_completions` | `openai_chat.json` | 2.3.0 | 2094 | Schema | 2026-10-21 |
| `messages` | `anthropic.json` | unknown (no public spec) | 928 | Schema | 2026-08-01 |
| `google_generate` | — | — | 0 | Semantic | — |
| `google_interactions` | `google_interactions.json` | v1beta | 186 | Semantic | 2026-08-29 |

```bash
llm-comply specs            # human-readable table
llm-comply specs --json     # machine-readable manifest
llm-comply specs --check    # CI: fail if the manifest drifts from bundled files
```

Refresh a bundled spec from its upstream source (the manifest is updated too):

```bash
llm-comply update-spec --format open_responses
llm-comply update-spec --format chat_completions
```

Formats without a verified public upstream (`messages`, `google_generate`,
`google_interactions`) are updated manually.

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
| `open_responses` | 13 | Schema + semantic (lifecycle, phases, compaction, thinking) |
| `chat_completions` | 9 | Schema + semantic (choices, finish_reason, delta) |
| `messages` | 9 | Schema + semantic (content blocks, stop_reason, thinking) |
| `google_generate` | 9 | Semantic only (candidates, parts, finishReason, thinking) |
| `google_interactions` | 9 | Semantic only (steps, model_output, thinking) |

## License

MIT
