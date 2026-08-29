"""Anthropic Messages API compliance test definitions."""

from __future__ import annotations

from typing import Any

from ..config import ComplianceConfig
from ..test_case import TestCase, TestCategory
from ..validators import (
    anth_error_returns_error_type,
    anth_has_content,
    anth_has_thinking_content,
    anth_has_tool_use,
    anth_has_usage,
    anth_role_assistant,
    anth_stop_reason,
    anth_streaming_has_text_delta,
    anth_streaming_has_usage,
    anth_streaming_lifecycle,
    anth_type_message,
    has_response_id,
    streaming_has_events,
)


def _load_test_image_b64() -> str:
    import base64
    import pathlib

    path = pathlib.Path(__file__).parent.parent / "specs" / "test_image.jpg"
    return base64.b64encode(path.read_bytes()).decode()


def _build_tool_calling_request(cfg: ComplianceConfig) -> dict[str, Any]:
    return {
        "model": cfg.model,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": "What is the weather in San Francisco?",
            },
        ],
        "tools": [
            {
                "name": "get_weather",
                "description": "Get current weather for a location.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name",
                        }
                    },
                    "required": ["location"],
                },
            }
        ],
        "tool_choice": {"type": "any"},
    }


def _build_image_input_request(cfg: ComplianceConfig) -> dict[str, Any]:
    b64 = _load_test_image_b64()
    return {
        "model": cfg.model,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image briefly."},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                ],
            },
        ],
    }


ANTHROPIC_TESTS: list[TestCase] = [
    TestCase(
        id="anth-basic-response",
        name="Basic Text Response",
        description="POST /v1/messages with a simple user message",
        category=TestCategory.BASIC,
        endpoint="/messages",
        schema_name="Message",
        build_request=lambda cfg: {
            "model": cfg.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Say hello in exactly 3 words."}],
        },
        validators=[
            has_response_id,
            anth_type_message,
            anth_role_assistant,
            anth_has_content,
            anth_stop_reason("end_turn"),
            anth_has_usage,
        ],
    ),
    TestCase(
        id="anth-system-prompt",
        name="System Prompt",
        description="Top-level system field is accepted and influences output",
        category=TestCategory.BASIC,
        endpoint="/messages",
        schema_name="Message",
        build_request=lambda cfg: {
            "model": cfg.model,
            "max_tokens": 1024,
            "system": "Always respond in exactly one word.",
            "messages": [{"role": "user", "content": "Say hello."}],
        },
        validators=[
            has_response_id,
            anth_type_message,
            anth_has_content,
            anth_stop_reason("end_turn"),
        ],
    ),
    TestCase(
        id="anth-multi-turn",
        name="Multi-turn Conversation",
        description="Assistant + user messages as conversation history",
        category=TestCategory.BASIC,
        endpoint="/messages",
        schema_name="Message",
        build_request=lambda cfg: {
            "model": cfg.model,
            "max_tokens": 1024,
            "messages": [
                {"role": "user", "content": "My name is Alice."},
                {"role": "assistant", "content": "Hello Alice!"},
                {
                    "role": "user",
                    "content": "What is my name? Reply with just the name.",
                },
            ],
        },
        validators=[
            has_response_id,
            anth_type_message,
            anth_has_content,
            anth_stop_reason("end_turn"),
        ],
    ),
    TestCase(
        id="anth-tool-calling",
        name="Tool Calling",
        description="Tool definition triggers tool_use content block",
        category=TestCategory.TOOLS,
        endpoint="/messages",
        schema_name="Message",
        build_request=_build_tool_calling_request,
        validators=[
            has_response_id,
            anth_type_message,
            anth_has_tool_use,
            anth_stop_reason("tool_use"),
        ],
    ),
    TestCase(
        id="anth-streaming-response",
        name="Streaming Response",
        description="SSE streaming lifecycle: message_start → deltas → message_stop",
        category=TestCategory.STREAMING,
        endpoint="/messages",
        schema_name=None,
        streaming=True,
        validate_stream_events=False,
        build_request=lambda cfg: {
            "model": cfg.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Count from 1 to 5."}],
        },
        validators=[
            streaming_has_events,
            anth_streaming_lifecycle,
            anth_streaming_has_text_delta,
        ],
    ),
    TestCase(
        id="anth-streaming-usage",
        name="Streaming Usage",
        description="Usage data present in message_delta event",
        category=TestCategory.STREAMING,
        endpoint="/messages",
        schema_name=None,
        streaming=True,
        validate_stream_events=False,
        build_request=lambda cfg: {
            "model": cfg.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Say one word."}],
        },
        validators=[
            streaming_has_events,
            anth_streaming_has_usage,
        ],
    ),
    TestCase(
        id="anth-image-input",
        name="Image Input",
        description="Base64 image in source block is accepted",
        category=TestCategory.MULTIMODAL,
        endpoint="/messages",
        schema_name="Message",
        build_request=_build_image_input_request,
        validators=[
            has_response_id,
            anth_type_message,
            anth_has_content,
            anth_stop_reason("end_turn"),
        ],
    ),
    TestCase(
        id="anth-thinking-display",
        name="Thinking Display",
        description="thinking config with display=summarized produces thinking content blocks",
        category=TestCategory.BASIC,
        endpoint="/messages",
        schema_name="Message",
        build_request=lambda cfg: {
            "model": cfg.model,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": "What is 15 * 37? Show your reasoning.",
                }
            ],
            "thinking": {
                "type": "enabled",
                "budget_tokens": 2048,
                "display": "summarized",
            },
        },
        validators=[
            has_response_id,
            anth_type_message,
            anth_role_assistant,
            anth_has_content,
            anth_stop_reason("end_turn"),
            anth_has_usage,
            anth_has_thinking_content,
        ],
        skip_reason=lambda cfg: (
            "extended thinking requires claude-3.5-sonnet or later"
            if not any(
                p in (cfg.model or "")
                for p in (
                    "claude-3-5",
                    "claude-3.5",
                    "claude-4",
                    "claude-opus",
                    "claude-sonnet-4",
                    "claude-haiku-4",
                )
            )
            else None
        ),
    ),
    TestCase(
        id="anth-error-handling",
        name="Error Handling",
        description="Invalid request (missing max_tokens) returns error or warning",
        category=TestCategory.ERROR_HANDLING,
        endpoint="/messages",
        schema_name=None,
        build_request=lambda cfg: {
            "model": cfg.model,
            "messages": [{"role": "user", "content": "test"}],
        },
        expected_statuses=[200, 400, 422],
        validators=[anth_error_returns_error_type],
    ),
]
