# llm-comply

**中文 | [English](README_en.md)**

[![PyPI](https://img.shields.io/pypi/v/llm-comply)](https://pypi.org/project/llm-comply/)
[![CI](https://github.com/Oaklight/llm-comply/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/llm-comply/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/llm-comply)](https://pypi.org/project/llm-comply/)
[![License](https://img.shields.io/github/license/Oaklight/llm-comply)](https://github.com/Oaklight/llm-comply/blob/master/LICENSE)

多格式 LLM API 合规性测试工具 — 根据官方规范验证 **OpenAI Chat Completions**、**Open Responses**、**Anthropic Messages**、**Google GenAI generateContent** 和 **Google GenAI Interactions** 端点的合规性。

**[在线体验 →](https://llm-comply.service.oaklight.top)**

## 安装

```bash
pip install llm-comply
# 启用彩色终端输出：
pip install llm-comply[rich]
```

## 快速开始

```bash
# Open Responses（默认）
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

认证请求头与默认值会按格式自动选择：OpenAI 系格式使用 `Authorization` + `Bearer`，
Messages 使用 `x-api-key`（并自动带 `anthropic-version`），Google 使用
`x-goog-api-key`。`--auth-header` 只选择请求头名称；是否加 `Bearer ` 前缀由
`--bearer`/`--no-bearer` 决定，未指定时采用格式默认值。`-H name:value` 可覆盖或
追加请求头，但不能替换已解析的认证头。

## 选项

```
-u, --base-url URL     API 基础 URL（必填）
-k, --api-key KEY      API 密钥（或设置 OPENRESPONSES_API_KEY 环境变量）
-m, --model MODEL      模型名称（默认：gpt-4o-mini）
--format FORMAT        API 格式：open_responses、openai_responses、
                       chat_completions、messages、
                       google_generate、google_interactions
                       （兼容旧名称：open-responses、openai-responses、
                       openai-chat、anthropic、google-genai、
                       google-interactions）
-f, --filter IDS       要运行的测试 ID，逗号分隔
-i, --ignore PATTERNS  忽略匹配子串的错误（如 refusal,verbosity）
-H, --header K:V       额外请求头（如 anthropic-version:2023-06-01）
--auth-header NAME     认证请求头名称（默认：按格式选择 Authorization、x-api-key
                       或 x-goog-api-key）
--bearer               在 API 密钥前添加 "Bearer " 前缀（覆盖格式默认值）
--no-bearer            不在 API 密钥前添加 "Bearer " 前缀（覆盖格式默认值）
-v, --verbose          失败时显示请求/响应详情
--json                 JSON 输出（适用于 CI）
--list                 列出所有可用的测试 ID
```

## 规范版本

内置规范的版本记录在
[`src/llm_comply/specs/manifest.json`](src/llm_comply/specs/manifest.json)，
可通过 `llm-comply specs` 查看。该 manifest 随代码提交，因此每个 master
提交和 release tag 都能明确对应到其所针对的上游规范版本。

| 格式 | 内置规范 | 版本 | Schema 数 | 验证方式 | 刷新日期 |
|------|----------|------|----------:|----------|----------|
| `open_responses` | `openresponses.json` | 2026-04-24 | 108 | Schema | 2026-10-21 |
| `openai_responses` | `openai_responses.json` | 2.3.0 | 357 | Schema | 2026-10-21 |
| `chat_completions` | `openai_chat.json` | 2.3.0 | 2094 | Schema | 2026-10-21 |
| `messages` | `anthropic.json` | unknown（规范无版本号） | 2008 | Schema | 2026-10-21 |
| `google_generate` | `google_generate.json` | v1beta | 252 | Schema | 2026-10-21 |
| `google_interactions` | `google_interactions.json` | v1beta | 213 | 语义 | 2026-10-21 |

```bash
llm-comply specs            # 人类可读表格
llm-comply specs --json     # 机器可读 manifest
llm-comply specs --check    # CI：manifest 与内置规范不一致时失败
```

从上游刷新内置规范（同时更新 manifest）：

```bash
llm-comply update-spec --all                     # 所有有上游来源的格式
llm-comply update-spec --format open_responses   # 单一格式
llm-comply update-spec --format messages         # Anthropic Messages
```

`messages` 来自 Anthropic 官方 SDK 内置的 `scripts/mock-spec.json.gz`
（Python 与 TypeScript SDK 中的副本字节完全一致）。`chat_completions` 与
`openai_responses` 来自同一份 OpenAI OpenAPI 文档；Responses 规范只内置
`/responses` 路径及其传递依赖的 `$ref` 闭包。
Google 规范来自官方
OpenAPI discovery 文档（`google_generate`）和 Interactions API 文档
（`google_interactions`）。`google_generate` 的响应会按
`GenerateContentResponse` 做 Schema 校验；Interactions 规范仅用于版本跟踪，
运行时验证仍为语义验证。discovery Schema 只声明类型与枚举，没有 `required`
数组，因此字段是否缺失仍由语义验证器负责。
每周一次的 `spec-update` workflow 会运行 `update-spec --all`，有变化时自动创建 PR。

当真实提供方的响应与内置规范不一致时，会应用有文档记录的加载期放宽
（见 `src/llm_comply/spec_relax.py`），而不是因提供方省略某个字段而失败；
每条放宽都由 `make verify` 固定。

## Web UI

```bash
llm-comply --web                                      # http://127.0.0.1:8090
llm-comply --web --host 0.0.0.0 \
  --tls-cert /path/cert.pem --tls-key /path/key.pem   # https://0.0.0.0:8090
```

Web UI 会在浏览器中接收 API key；只要服务不止本机可访问，就应通过 TLS 提供。
`--tls-cert` 与 `--tls-key` 必须同时提供，最低 TLS 版本为 1.2。

`GET /health` 返回版本号与累计计数（`runs_started`、`runs_completed`、
`runs_aborted`、`runs_failed`、`requests_completed`、`client_disconnects`），
使 `runs_started` 与各终态计数保持一致。流中抛错时会发送最后一帧
`event: error` 并递增 `runs_failed`。关闭浏览器标签页后，当前测试结束后不会
再启动下一项；已在途的请求仍会完成，因为它已经发出。

## Docker

```bash
docker run -p 8090:8090 oaklight/llm-comply:latest
```

生产部署参考 `compose.yaml`：

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

> **注意**：二进制镜像使用 Nuitka onefile 格式，启动时解压到 `/tmp`。使用 `read_only: true` 时需要带 `exec` 权限的 `tmpfs` 挂载。

## 测试覆盖

| 格式 | 测试数 | 验证内容 |
|------|:------:|----------|
| `open_responses` | 16 | Schema + 语义（生命周期、阶段、压缩、多轮工具、结构化输出、文件输入、思维链） |
| `openai_responses` | 12 | Schema + 语义（生命周期、流式事件、工具、推理、文件输入） |
| `chat_completions` | 13 | Schema + 语义（choices、finish_reason、delta、流式 chunk、developer 角色、结构化输出、Web 搜索、音频输出、错误响应） |
| `messages` | 19 | Schema + 语义（content blocks、stop_reason、max_tokens/stop_sequence、流式工具增量、思维链、提示缓存、文档输入、tool_result 往返、Web 搜索、代码执行、结构化输出、token 计数） |
| `google_generate` | 12 | Schema + 语义（candidates、parts、finishReason、safetyRatings、思维链、结构化输出、搜索接地、代码执行） |
| `google_interactions` | 13 | 仅语义（steps、model_output、思维链、Google 搜索、代码执行、地图、URL 上下文） |

`chat-audio-output` 以模型名作为能力提示：仅当名称包含 `audio`（不区分大小写）
时才运行；若部署使用自定义别名，请用包含 `audio` 的名称运行该测试。

内置 Google Interactions 工具测试是可选的：如果提供方不支持某个工具并返回
400、404、405、422 或 501，该测试会标记为跳过。其他不足——5xx，或返回成功
但没有工具输出——会标记为警告，因此内置工具不会让本来合规的 API 失败。
Google GenAI 的搜索接地与代码执行、Anthropic 的网页搜索与代码执行、以及
chat 的网页搜索测试同样遵循此规则。

## 许可证

MIT
