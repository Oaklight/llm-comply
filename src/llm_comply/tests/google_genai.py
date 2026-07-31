"""Google GenAI (Gemini) API compliance test definitions."""

from __future__ import annotations

from typing import Any

from ..config import ComplianceConfig
from ..test_case import TestCase, TestCategory
from ..validators import (
    google_finish_reason,
    google_has_candidates,
    google_has_content_parts,
    google_has_function_call,
    google_has_usage,
    google_streaming_has_finish,
    google_streaming_has_text,
    google_streaming_has_usage,
    streaming_has_events,
)


def _load_test_image_b64() -> str:
    import base64
    import pathlib

    path = pathlib.Path(__file__).parent.parent / "specs" / "test_image.jpg"
    return base64.b64encode(path.read_bytes()).decode()


def _ep(cfg: ComplianceConfig) -> str:
    return f"/v1beta/models/{cfg.model}:generateContent"


def _ep_stream(cfg: ComplianceConfig) -> str:
    return f"/v1beta/models/{cfg.model}:streamGenerateContent?alt=sse"


def _build_tool_request(cfg: ComplianceConfig) -> dict[str, Any]:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": "What is the weather in San Francisco?"}],
            }
        ],
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "get_weather",
                        "description": "Get current weather for a location.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "location": {
                                    "type": "STRING",
                                    "description": "City name",
                                }
                            },
                            "required": ["location"],
                        },
                    }
                ]
            }
        ],
        "tool_config": {
            "function_calling_config": {"mode": "ANY"},
        },
    }


def _build_image_request(cfg: ComplianceConfig) -> dict[str, Any]:
    b64 = _load_test_image_b64()
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "Describe this image briefly."},
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": b64,
                        }
                    },
                ],
            }
        ],
    }


# Google endpoints include the model name, so we use a dynamic endpoint
# via a wrapper that sets the endpoint at build time.
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
    if streaming:
        ep_fn = _ep_stream
    else:
        ep_fn = _ep

    original_build = build_request

    def _build_with_endpoint(cfg: ComplianceConfig) -> dict[str, Any]:
        # Stash the dynamic endpoint for the runner to use
        body = original_build(cfg)
        body["_google_endpoint"] = ep_fn(cfg)
        return body

    import dataclasses

    tc = TestCase(
        id=id,
        name=name,
        description=description,
        category=category,
        build_request=_build_with_endpoint,
        validators=validators,
        streaming=streaming,
        endpoint="/placeholder",
        schema_name=None,
        validate_stream_events=False,
    )
    if expected_statuses:
        tc = dataclasses.replace(tc, expected_statuses=expected_statuses)
    return tc


GOOGLE_GENAI_TESTS: list[TestCase] = [
    _make_test(
        id="google-basic-response",
        name="Basic Text Response",
        description="POST generateContent with a simple user message",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "contents": [
                {"role": "user", "parts": [{"text": "Say hello in exactly 3 words."}]}
            ],
        },
        validators=[
            google_has_candidates,
            google_has_content_parts,
            google_finish_reason("STOP"),
            google_has_usage,
        ],
    ),
    _make_test(
        id="google-system-prompt",
        name="System Instruction",
        description="Top-level systemInstruction field is accepted",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "systemInstruction": {
                "parts": [{"text": "Always respond in exactly one word."}]
            },
            "contents": [
                {"role": "user", "parts": [{"text": "Say hello."}]},
            ],
        },
        validators=[
            google_has_candidates,
            google_has_content_parts,
            google_finish_reason("STOP"),
        ],
    ),
    _make_test(
        id="google-multi-turn",
        name="Multi-turn Conversation",
        description="User + model messages as conversation history",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "contents": [
                {"role": "user", "parts": [{"text": "My name is Alice."}]},
                {"role": "model", "parts": [{"text": "Hello Alice!"}]},
                {
                    "role": "user",
                    "parts": [{"text": "What is my name? Reply with just the name."}],
                },
            ],
        },
        validators=[
            google_has_candidates,
            google_has_content_parts,
            google_finish_reason("STOP"),
        ],
    ),
    _make_test(
        id="google-tool-calling",
        name="Tool Calling",
        description="Function declaration triggers functionCall part in response",
        category=TestCategory.TOOLS,
        build_request=_build_tool_request,
        validators=[
            google_has_candidates,
            google_has_function_call,
            google_finish_reason("STOP"),
        ],
    ),
    _make_test(
        id="google-streaming-response",
        name="Streaming Response",
        description="SSE streaming chunks with text parts and finishReason",
        category=TestCategory.STREAMING,
        streaming=True,
        build_request=lambda cfg: {
            "contents": [
                {"role": "user", "parts": [{"text": "Count from 1 to 5."}]},
            ],
        },
        validators=[
            streaming_has_events,
            google_streaming_has_text,
            google_streaming_has_finish,
        ],
    ),
    _make_test(
        id="google-streaming-usage",
        name="Streaming Usage",
        description="usageMetadata present in streaming chunks",
        category=TestCategory.STREAMING,
        streaming=True,
        build_request=lambda cfg: {
            "contents": [
                {"role": "user", "parts": [{"text": "Say one word."}]},
            ],
        },
        validators=[
            streaming_has_events,
            google_streaming_has_usage,
        ],
    ),
    _make_test(
        id="google-image-input",
        name="Image Input",
        description="Inline base64 image via inlineData is accepted",
        category=TestCategory.MULTIMODAL,
        build_request=_build_image_request,
        validators=[
            google_has_candidates,
            google_has_content_parts,
            google_finish_reason("STOP"),
        ],
    ),
    _make_test(
        id="google-error-handling",
        name="Error Handling",
        description="Invalid request returns error response",
        category=TestCategory.ERROR_HANDLING,
        build_request=lambda cfg: {},
        expected_statuses=[400, 422],
        validators=[],
    ),
]
