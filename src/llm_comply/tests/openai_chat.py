"""OpenAI Chat Completions API compliance test definitions."""

from __future__ import annotations

from typing import Any

from ..config import ComplianceConfig
from ..test_case import TestCase, TestCategory
from ..validators import (
    chat_finish_reason,
    chat_has_annotations_field,
    chat_has_audio,
    chat_has_choices,
    chat_has_completion_token_details,
    chat_has_logprobs_field,
    chat_has_message,
    chat_has_prompt_token_details,
    chat_has_reasoning_tokens,
    chat_has_refusal_field,
    chat_has_tool_call_of_type,
    chat_has_usage,
    chat_id_has_prefix,
    chat_message_is_json,
    chat_message_matches_json_schema,
    chat_streaming_all_have_finish_reason,
    chat_streaming_has_delta,
    chat_streaming_has_done,
    chat_streaming_has_finish,
    chat_streaming_has_usage,
    has_response_id,
    streaming_has_events,
)

_CHAT_RESPONSE_WARNINGS = [
    chat_has_refusal_field,
    chat_has_annotations_field,
    chat_has_logprobs_field,
    chat_has_completion_token_details,
    chat_has_prompt_token_details,
    chat_id_has_prefix("chatcmpl-"),
]

_CHAT_STREAMING_WARNINGS = [
    chat_streaming_all_have_finish_reason,
    chat_id_has_prefix("chatcmpl-"),
]


_WEATHER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "city": {"type": "string"},
        "temperature_c": {"type": "number"},
    },
    "required": ["city", "temperature_c"],
    "additionalProperties": False,
}


def _build_developer_role_request(cfg: ComplianceConfig) -> dict[str, Any]:
    return {
        "model": cfg.model,
        "messages": [
            {
                "role": "developer",
                "content": "You always answer with exactly one word.",
            },
            {"role": "user", "content": "Say hello."},
        ],
    }


def _build_structured_output_request(cfg: ComplianceConfig) -> dict[str, Any]:
    return {
        "model": cfg.model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Return the current weather in San Francisco as JSON with "
                    "keys city and temperature_c."
                ),
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "weather",
                "strict": True,
                "schema": _WEATHER_SCHEMA,
            },
        },
    }


def _load_test_image_b64() -> str:
    import base64
    import pathlib

    path = pathlib.Path(__file__).parent.parent / "specs" / "test_image.jpg"
    return base64.b64encode(path.read_bytes()).decode()


def _build_tool_calling_request(cfg: ComplianceConfig) -> dict[str, Any]:
    return {
        "model": cfg.model,
        "messages": [
            {
                "role": "user",
                "content": "What is the weather in San Francisco?",
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name",
                            }
                        },
                        "required": ["location"],
                    },
                },
            }
        ],
        "tool_choice": "required",
    }


def _build_image_input_request(cfg: ComplianceConfig) -> dict[str, Any]:
    b64 = _load_test_image_b64()
    return {
        "model": cfg.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image briefly."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                        },
                    },
                ],
            },
        ],
    }


OPENAI_CHAT_TESTS: list[TestCase] = [
    TestCase(
        id="chat-basic-response",
        name="Basic Text Response",
        description="POST /v1/chat/completions with a simple user message",
        category=TestCategory.BASIC,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        build_request=lambda cfg: {
            "model": cfg.model,
            "messages": [{"role": "user", "content": "Say hello in exactly 3 words."}],
        },
        validators=[
            has_response_id,
            chat_has_choices,
            chat_has_message,
            chat_finish_reason("stop"),
            chat_has_usage,
            *_CHAT_RESPONSE_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-system-prompt",
        name="System Prompt",
        description="System role message is accepted and influences output",
        category=TestCategory.BASIC,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        build_request=lambda cfg: {
            "model": cfg.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Always respond in exactly one word.",
                },
                {"role": "user", "content": "Say hello."},
            ],
        },
        validators=[
            has_response_id,
            chat_has_choices,
            chat_has_message,
            chat_finish_reason("stop"),
            *_CHAT_RESPONSE_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-multi-turn",
        name="Multi-turn Conversation",
        description="Assistant + user messages as conversation history",
        category=TestCategory.BASIC,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        build_request=lambda cfg: {
            "model": cfg.model,
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
            chat_has_choices,
            chat_has_message,
            chat_finish_reason("stop"),
            *_CHAT_RESPONSE_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-tool-calling",
        name="Tool Calling",
        description="Function tool definition triggers tool_calls in response",
        category=TestCategory.TOOLS,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        build_request=_build_tool_calling_request,
        validators=[
            has_response_id,
            chat_has_choices,
            chat_has_tool_call_of_type("function"),
            chat_finish_reason("tool_calls"),
            *_CHAT_RESPONSE_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-developer-role",
        name="Developer Role",
        description="developer role message is accepted",
        category=TestCategory.BASIC,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        build_request=_build_developer_role_request,
        validators=[
            has_response_id,
            chat_has_choices,
            chat_has_message,
            chat_finish_reason("stop"),
            *_CHAT_RESPONSE_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-structured-output",
        name="Structured Output",
        description="response_format json_schema is accepted and content matches it",
        category=TestCategory.BASIC,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        build_request=_build_structured_output_request,
        validators=[
            has_response_id,
            chat_has_choices,
            chat_has_message,
            chat_message_is_json,
            chat_message_matches_json_schema(_WEATHER_SCHEMA),
            *_CHAT_RESPONSE_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-streaming-response",
        name="Streaming Response",
        description="SSE streaming chunks with delta content and [DONE] terminator",
        category=TestCategory.STREAMING,
        endpoint="/chat/completions",
        schema_name=None,
        streaming=True,
        validate_stream_events=True,
        stream_schema_name="CreateChatCompletionStreamResponse",
        build_request=lambda cfg: {
            "model": cfg.model,
            "messages": [{"role": "user", "content": "Count from 1 to 5."}],
        },
        validators=[
            streaming_has_events,
            chat_streaming_has_delta,
            chat_streaming_has_finish,
            chat_streaming_has_done,
            *_CHAT_STREAMING_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-streaming-usage",
        name="Streaming Usage",
        description="Usage metadata present in streaming with stream_options",
        category=TestCategory.STREAMING,
        endpoint="/chat/completions",
        schema_name=None,
        streaming=True,
        validate_stream_events=True,
        stream_schema_name="CreateChatCompletionStreamResponse",
        build_request=lambda cfg: {
            "model": cfg.model,
            "messages": [{"role": "user", "content": "Say one word."}],
            "stream_options": {"include_usage": True},
        },
        validators=[
            streaming_has_events,
            chat_streaming_has_usage,
            chat_streaming_has_done,
            *_CHAT_STREAMING_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-image-input",
        name="Image Input",
        description="Content with inline base64 image is accepted",
        category=TestCategory.MULTIMODAL,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        build_request=_build_image_input_request,
        validators=[
            has_response_id,
            chat_has_choices,
            chat_has_message,
            chat_finish_reason("stop"),
            *_CHAT_RESPONSE_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-reasoning-summary",
        name="Reasoning Summary",
        description="reasoning.summary parameter is accepted and produces reasoning tokens",
        category=TestCategory.BASIC,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        build_request=lambda cfg: {
            "model": cfg.model,
            "messages": [
                {
                    "role": "user",
                    "content": "What is 15 * 37? Show your reasoning.",
                }
            ],
            "reasoning_effort": "low",
        },
        validators=[
            has_response_id,
            chat_has_choices,
            chat_has_message,
            chat_finish_reason("stop"),
            chat_has_usage,
            chat_has_reasoning_tokens,
        ],
        skip_reason=lambda cfg: (
            "reasoning requires o-series or gpt-5 models"
            if not any(
                p in (cfg.model or "")
                for p in ("o1", "o3", "o4", "gpt-5", "deepseek-r")
            )
            else None
        ),
    ),
    TestCase(
        id="chat-audio-output",
        name="Audio Output",
        description="modalities audio produces a message audio payload",
        category=TestCategory.MULTIMODAL,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        build_request=lambda cfg: {
            "model": cfg.model,
            "messages": [{"role": "user", "content": "Say hello."}],
            "modalities": ["text", "audio"],
            "audio": {"voice": "alloy", "format": "wav"},
        },
        validators=[
            has_response_id,
            chat_has_choices,
            chat_has_message,
            chat_has_audio,
            *_CHAT_RESPONSE_WARNINGS,
        ],
        skip_reason=lambda cfg: (
            None
            if "audio" in (cfg.model or "").lower()
            else "audio output requires an audio-capable model"
        ),
    ),
    TestCase(
        id="chat-web-search",
        name="Web Search Options",
        description="web_search_options is accepted by the endpoint",
        category=TestCategory.BASIC,
        endpoint="/chat/completions",
        schema_name="CreateChatCompletionResponse",
        optional=True,
        build_request=lambda cfg: {
            "model": cfg.model,
            "messages": [
                {
                    "role": "user",
                    "content": "What happened in the news today? Answer in one sentence.",
                }
            ],
            "web_search_options": {},
        },
        validators=[
            has_response_id,
            chat_has_choices,
            chat_has_message,
            chat_finish_reason("stop"),
            *_CHAT_RESPONSE_WARNINGS,
        ],
    ),
    TestCase(
        id="chat-error-handling",
        name="Error Handling",
        description="Invalid request returns correct error format",
        category=TestCategory.ERROR_HANDLING,
        endpoint="/chat/completions",
        schema_name="ErrorResponse",
        build_request=lambda cfg: {
            "messages": [{"role": "user", "content": "test"}],
        },
        expected_statuses=[400, 422],
        validators=[],
    ),
]
