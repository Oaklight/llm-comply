# llm-comply

[![PyPI](https://img.shields.io/pypi/v/llm-comply)](https://pypi.org/project/llm-comply/)
[![CI](https://github.com/Oaklight/llm-comply/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/llm-comply/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/llm-comply)](https://pypi.org/project/llm-comply/)
[![License](https://img.shields.io/github/license/Oaklight/llm-comply)](https://github.com/Oaklight/llm-comply/blob/master/LICENSE)

Multi-format LLM API compliance testing tool — validates endpoints against official specs for **OpenAI Chat Completions**, **Open Responses**, **Anthropic Messages**, and **Google GenAI**.

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
llm-comply --format openai-chat -u https://api.openai.com/v1 -k $OPENAI_API_KEY -m gpt-4o-mini

# Anthropic Messages
llm-comply --format anthropic -u https://api.anthropic.com/v1 -k $KEY -m claude-haiku-4-5 \
  --auth-header x-api-key --no-bearer -H anthropic-version:2023-06-01

# Google GenAI
llm-comply --format google-genai -u https://generativelanguage.googleapis.com -k $KEY \
  -m gemini-2.5-flash --auth-header x-goog-api-key --no-bearer
```

## Options

```
-u, --base-url URL     API base URL (required)
-k, --api-key KEY      API key (or set OPENRESPONSES_API_KEY env)
-m, --model MODEL      Model name (default: gpt-4o-mini)
--format FORMAT        API format: open-responses, openai-chat, anthropic, google-genai
-f, --filter IDS       Comma-separated test IDs to run
-i, --ignore PATTERNS  Ignore errors matching substrings (e.g. refusal,verbosity)
-H, --header K:V       Extra headers (e.g. anthropic-version:2023-06-01)
--auth-header NAME     Auth header name (default: Authorization)
--no-bearer            Don't prepend "Bearer " to API key
-v, --verbose          Show request/response on failure
--json                 JSON output for CI
--list                 List available test IDs
```

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
| Open Responses | 12 | Schema + semantic (lifecycle, phases, compaction) |
| OpenAI Chat | 8 | Schema + semantic (choices, finish_reason, delta) |
| Anthropic Messages | 8 | Schema + semantic (content blocks, stop_reason) |
| Google GenAI | 8 | Semantic only (candidates, parts, finishReason) |

## License

MIT
