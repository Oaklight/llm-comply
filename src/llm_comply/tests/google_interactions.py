"""Google Interactions API compliance test definitions."""

from __future__ import annotations

from typing import Any

from ..config import ComplianceConfig
from ..test_case import TestCase, TestCategory
from ..validators import (
    interactions_has_id,
    interactions_has_model_output,
    interactions_has_steps,
    interactions_has_thought,
    interactions_has_usage,
    interactions_status,
    interactions_has_function_call,
    interactions_function_call_has_id,
    interactions_has_model_field,
    interactions_has_object_field,
    interactions_streaming_has_text,
    interactions_streaming_has_lifecycle,
    interactions_streaming_has_completed,
    interactions_streaming_has_usage,
    streaming_has_events,
)


def _load_test_image_b64() -> str:
    import base64
    import pathlib

    path = pathlib.Path(__file__).parent.parent / "specs" / "test_image.jpg"
    return base64.b64encode(path.read_bytes()).decode()


_ENDPOINT = "/v1beta/interactions"
_ENDPOINT_STREAM = "/v1beta/interactions?alt=sse"


def _make_test(
    *,
    id: str,
    name: str,
    description: str,
    category: TestCategory,
    build_request: Any,
    validators: list,
    streaming: bool = False,
    expected_statuses: list[int] | None = None,
) -> TestCase:
    import dataclasses

    tc = TestCase(
        id=id,
        name=name,
        description=description,
        category=category,
        build_request=build_request,
        validators=validators,
        streaming=streaming,
        endpoint=_ENDPOINT_STREAM if streaming else _ENDPOINT,
        schema_name=None,
        validate_stream_events=False,
    )
    if expected_statuses:
        tc = dataclasses.replace(tc, expected_statuses=expected_statuses)
    return tc


def _build_tool_request(cfg: ComplianceConfig) -> dict[str, Any]:
    return {
        "model": cfg.model,
        "input": "What is the weather in San Francisco?",
        "tools": [
            {
                "type": "function",
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
            }
        ],
    }


def _build_image_request(cfg: ComplianceConfig) -> dict[str, Any]:
    b64 = _load_test_image_b64()
    return {
        "model": cfg.model,
        "input": [
            {
                "type": "user_input",
                "content": [
                    {"type": "text", "text": "Describe this image briefly."},
                    {
                        "type": "image",
                        "mime_type": "image/jpeg",
                        "data": b64,
                    },
                ],
            }
        ],
    }


GOOGLE_INTERACTIONS_TESTS: list[TestCase] = [
    _make_test(
        id="interactions-basic-response",
        name="Basic Text Response",
        description="POST /v1beta/interactions with a simple string input",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": "Say hello in exactly 3 words.",
        },
        validators=[
            interactions_has_id,
            interactions_has_steps,
            interactions_has_model_output,
            interactions_status("completed"),
            interactions_has_usage,
            interactions_has_model_field,
            interactions_has_object_field,
        ],
    ),
    _make_test(
        id="interactions-system-instruction",
        name="System Instruction",
        description="system_instruction field is accepted",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "system_instruction": "Always respond in exactly one word.",
            "input": "Say hello.",
        },
        validators=[
            interactions_has_steps,
            interactions_has_model_output,
            interactions_status("completed"),
        ],
    ),
    _make_test(
        id="interactions-multi-turn",
        name="Multi-turn Conversation (Stateless)",
        description="Stateless multi-turn with user_input and model_output steps",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "store": False,
            "input": [
                {
                    "type": "user_input",
                    "content": [
                        {"type": "text", "text": "My name is Alice."},
                    ],
                },
                {
                    "type": "model_output",
                    "content": [
                        {"type": "text", "text": "Hello Alice!"},
                    ],
                },
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "text",
                            "text": "What is my name? Reply with just the name.",
                        },
                    ],
                },
            ],
        },
        validators=[
            interactions_has_steps,
            interactions_has_model_output,
            interactions_status("completed"),
        ],
    ),
    _make_test(
        id="interactions-tool-calling",
        name="Tool Calling",
        description="Function tool triggers function_call step in response",
        category=TestCategory.TOOLS,
        build_request=_build_tool_request,
        validators=[
            interactions_has_steps,
            interactions_has_function_call,
            interactions_function_call_has_id,
            interactions_status("requires_action"),
        ],
    ),
    _make_test(
        id="interactions-streaming-response",
        name="Streaming Response",
        description="SSE streaming with step.start/delta/stop and interaction lifecycle",
        category=TestCategory.STREAMING,
        streaming=True,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": "Count from 1 to 5.",
            "stream": True,
        },
        validators=[
            streaming_has_events,
            interactions_streaming_has_text,
            interactions_streaming_has_lifecycle,
            interactions_streaming_has_completed,
        ],
    ),
    _make_test(
        id="interactions-streaming-usage",
        name="Streaming Usage",
        description="Usage metadata present in interaction.completed event",
        category=TestCategory.STREAMING,
        streaming=True,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": "Say one word.",
            "stream": True,
        },
        validators=[
            streaming_has_events,
            interactions_streaming_has_usage,
        ],
    ),
    _make_test(
        id="interactions-image-input",
        name="Image Input",
        description="Inline base64 image via content type 'image' is accepted",
        category=TestCategory.MULTIMODAL,
        build_request=_build_image_request,
        validators=[
            interactions_has_steps,
            interactions_has_model_output,
            interactions_status("completed"),
        ],
    ),
    _make_test(
        id="interactions-thinking",
        name="Thinking Config",
        description="generation_config.thinking_level produces thought steps",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": "What is 15 * 37? Show your reasoning.",
            "generation_config": {
                "thinking_level": "low",
            },
        },
        validators=[
            interactions_has_steps,
            interactions_has_model_output,
            interactions_status("completed"),
            interactions_has_usage,
            interactions_has_thought,
        ],
    ),
    _make_test(
        id="interactions-error-handling",
        name="Error Handling",
        description="Invalid request returns error response",
        category=TestCategory.ERROR_HANDLING,
        build_request=lambda cfg: {},
        expected_statuses=[400, 422],
        validators=[],
    ),
]
