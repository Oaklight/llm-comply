"""Anthropic Messages API compliance test definitions."""

from __future__ import annotations

from typing import Any

from ..config import ComplianceConfig
from ..test_case import TestCase, TestCategory
from ..validators import (
    anth_error_returns_error_type,
    anth_has_content,
    anth_has_content_block_of_type,
    anth_has_thinking_content,
    anth_has_tool_use,
    anth_has_usage,
    anth_output_is_json,
    anth_output_matches_json_schema,
    anth_role_assistant,
    anth_stop_reason,
    anth_streaming_content_block_bracketing,
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


def _build_tool_result_request(cfg: ComplianceConfig) -> dict[str, Any]:
    """Continue a tool-use conversation by returning a tool_result block."""
    return {
        "model": cfg.model,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": "What is the weather in San Francisco?",
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "get_weather",
                        "input": {"location": "San Francisco"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01",
                        "content": "18 degrees Celsius and sunny",
                    }
                ],
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
    }


_WEATHER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "city": {"type": "string"},
        "temperature_c": {"type": "number"},
    },
    "required": ["city", "temperature_c"],
}


def _build_structured_output_request(cfg: ComplianceConfig) -> dict[str, Any]:
    return {
        "model": cfg.model,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Return the current weather in San Francisco as JSON "
                    "with keys city and temperature_c."
                ),
            }
        ],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": _WEATHER_OUTPUT_SCHEMA,
            }
        },
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
        id="anth-tool-result",
        name="Tool Result Round-trip",
        description="tool_use history plus a tool_result block yields a final text answer",
        category=TestCategory.TOOLS,
        endpoint="/messages",
        schema_name="Message",
        build_request=_build_tool_result_request,
        validators=[
            has_response_id,
            anth_type_message,
            anth_role_assistant,
            anth_has_content,
            anth_has_content_block_of_type("text"),
            anth_stop_reason("end_turn"),
        ],
    ),
    TestCase(
        id="anth-web-search",
        name="Web Search Tool",
        description="web_search server tool produces server_tool_use and web_search_tool_result blocks",
        category=TestCategory.TOOLS,
        endpoint="/messages",
        schema_name="Message",
        optional=True,
        build_request=lambda cfg: {
            "model": cfg.model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": "What is the weather in San Francisco today? Search the web.",
                }
            ],
            "tools": [
                {
                    "type": "web_search_20260318",
                    "name": "web_search",
                    "max_uses": 3,
                }
            ],
        },
        validators=[
            has_response_id,
            anth_type_message,
            anth_role_assistant,
            anth_has_content,
            anth_has_content_block_of_type("server_tool_use", "web_search_tool_result"),
            anth_stop_reason("end_turn"),
        ],
    ),
    TestCase(
        id="anth-structured-output",
        name="Structured Output",
        description="output_config JSON schema yields matching JSON text",
        category=TestCategory.BASIC,
        endpoint="/messages",
        schema_name="Message",
        build_request=_build_structured_output_request,
        validators=[
            has_response_id,
            anth_type_message,
            anth_role_assistant,
            anth_has_content,
            anth_stop_reason("end_turn"),
            anth_output_is_json,
            anth_output_matches_json_schema(_WEATHER_OUTPUT_SCHEMA),
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
            anth_streaming_content_block_bracketing,
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
