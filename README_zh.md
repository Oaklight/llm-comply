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
llm-comply --format openai-chat -u https://api.openai.com/v1 -k $OPENAI_API_KEY -m gpt-4o-mini

# Anthropic Messages
llm-comply --format anthropic -u https://api.anthropic.com/v1 -k $KEY -m claude-haiku-4-5 \
  --auth-header x-api-key --no-bearer -H anthropic-version:2023-06-01

# Google GenAI — generateContent
llm-comply --format google-genai -u https://generativelanguage.googleapis.com -k $KEY \
  -m gemini-2.5-flash --auth-header x-goog-api-key --no-bearer

# Google GenAI — Interactions
llm-comply --format google-interactions -u https://generativelanguage.googleapis.com -k $KEY \
  -m gemini-2.5-flash --auth-header x-goog-api-key --no-bearer
```

## 选项

```
-u, --base-url URL     API 基础 URL（必填）
-k, --api-key KEY      API 密钥（或设置 OPENRESPONSES_API_KEY 环境变量）
-m, --model MODEL      模型名称（默认：gpt-4o-mini）
--format FORMAT        API 格式：open-responses、openai-chat、anthropic、
                       google-genai、google-interactions
-f, --filter IDS       要运行的测试 ID，逗号分隔
-i, --ignore PATTERNS  忽略匹配子串的错误（如 refusal,verbosity）
-H, --header K:V       额外请求头（如 anthropic-version:2023-06-01）
--auth-header NAME     认证请求头名称（默认：Authorization）
--no-bearer            不在 API 密钥前添加 "Bearer " 前缀
-v, --verbose          失败时显示请求/响应详情
--json                 JSON 输出（适用于 CI）
--list                 列出所有可用的测试 ID
```

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
| Open Responses | 13 | Schema + 语义（生命周期、阶段、压缩、思维链） |
| OpenAI Chat | 8 | Schema + 语义（choices、finish_reason、delta） |
| Anthropic Messages | 9 | Schema + 语义（content blocks、stop_reason、思维链） |
| Google GenAI generateContent | 9 | 仅语义（candidates、parts、finishReason、思维链） |
| Google GenAI Interactions | 9 | 仅语义（steps、model_output、思维链） |

## 许可证

MIT
