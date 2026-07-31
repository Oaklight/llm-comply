# llm-comply

Multi-format LLM API compliance testing tool — validates endpoints against official specs for **OpenAI Chat Completions**, **Open Responses**, **Anthropic Messages**, and **Google GenAI**.

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

## Test Coverage

| Format | Tests | What's Validated |
|--------|:-----:|-----------------|
| Open Responses | 12 | Schema + semantic (lifecycle, phases, compaction) |
| OpenAI Chat | 8 | Schema + semantic (choices, finish_reason, delta) |
| Anthropic Messages | 8 | Schema + semantic (content blocks, stop_reason) |
| Google GenAI | 8 | Semantic only (candidates, parts, finishReason) |

## License

MIT
