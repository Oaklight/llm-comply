"""Open Responses API compliance test definitions."""

from __future__ import annotations

from typing import Any

from ..config import ComplianceConfig
from ..test_case import TestCase, TestCategory
from ..test_case import ValidatorContext
from ..validators import (
    compact_object,
    completed_status,
    has_output,
    has_output_type,
    has_response_id,
    has_usage,
    responses_has_reasoning_summary,
    streaming_has_events,
    streaming_has_terminal,
    streaming_has_usage,
    streaming_lifecycle_order,
    streaming_sequence_numbers,
)

_PHASE_FIXTURE: dict[str, Any] = {
    "id": "resp_phase_schema",
    "object": "response",
    "created_at": 1764967971,
    "completed_at": 1764967972,
    "status": "completed",
    "incomplete_details": None,
    "model": "test",
    "previous_response_id": None,
    "instructions": None,
    "output": [
        {
            "id": "msg_commentary",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "phase": "commentary",
            "content": [
                {"type": "output_text", "text": "Checking.", "annotations": []}
            ],
        },
        {
            "id": "msg_final",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "phase": "final_answer",
            "content": [{"type": "output_text", "text": "Four.", "annotations": []}],
        },
    ],
    "error": None,
    "tools": [],
    "tool_choice": "auto",
    "truncation": "disabled",
    "parallel_tool_calls": True,
    "text": {"format": {"type": "text"}},
    "top_p": 1,
    "presence_penalty": 0,
    "frequency_penalty": 0,
    "top_logprobs": 0,
    "temperature": 1,
    "reasoning": {"effort": None, "summary": None},
    "usage": {
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    },
    "max_output_tokens": None,
    "max_tool_calls": None,
    "store": True,
    "background": False,
    "service_tier": "default",
    "metadata": {},
    "safety_identifier": None,
    "prompt_cache_key": None,
}


def _validate_phase_fixture(response: Any, ctx: ValidatorContext) -> list[str]:
    """Validate the local phase fixture against the spec schema."""
    import pathlib

    from ..schema import SpecLoader

    spec_path = pathlib.Path(__file__).parent.parent / "specs" / "openresponses.json"
    spec = SpecLoader(str(spec_path))
    return spec.validate(_PHASE_FIXTURE, "ResponseResource")


def _load_test_image_b64() -> str:
    import base64
    import pathlib

    path = pathlib.Path(__file__).parent.parent / "specs" / "test_image.jpg"
    return base64.b64encode(path.read_bytes()).decode()


def _build_tool_calling_request(cfg: ComplianceConfig) -> dict[str, Any]:
    return {
        "model": cfg.model,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": "What is the weather in San Francisco?",
            },
        ],
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
        "tool_choice": "required",
    }


def _build_image_input_request(cfg: ComplianceConfig) -> dict[str, Any]:
    b64 = _load_test_image_b64()
    return {
        "model": cfg.model,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Describe this image briefly."},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{b64}",
                    },
                ],
            },
        ],
    }


def _compact_warn_has_output(response: Any, ctx: ValidatorContext) -> list[str]:
    errs = has_output(response, ctx)
    return [f"[warning] {e}" for e in errs]


def _compact_warn_object(response: Any, ctx: ValidatorContext) -> list[str]:
    errs = compact_object(response, ctx)
    return [f"[warning] {e}" for e in errs]


def _compact_warn_has_compaction(response: Any, ctx: ValidatorContext) -> list[str]:
    checker = has_output_type("compaction")
    errs = checker(response, ctx)
    return [f"[warning] {e}" for e in errs]


OPEN_RESPONSES_TESTS: list[TestCase] = [
    TestCase(
        id="basic-response",
        name="Basic Text Response",
        description="POST /v1/responses with a simple user message",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "Say hello in exactly 3 words.",
                }
            ],
        },
        validators=[has_response_id, has_output, completed_status, has_usage],
    ),
    TestCase(
        id="system-prompt",
        name="System Prompt",
        description="System role message is accepted and influences output",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": "Always respond in exactly one word.",
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": "Say hello.",
                },
            ],
        },
        validators=[has_response_id, has_output, completed_status],
    ),
    TestCase(
        id="multi-turn",
        name="Multi-turn Conversation",
        description="Assistant + user messages as conversation history",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "My name is Alice.",
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": "Hello Alice!",
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": "What is my name? Reply with just the name.",
                },
            ],
        },
        validators=[has_response_id, has_output, completed_status],
    ),
    TestCase(
        id="tool-calling",
        name="Tool Calling",
        description="Function tool definition triggers function_call output",
        category=TestCategory.TOOLS,
        build_request=_build_tool_calling_request,
        validators=[
            has_response_id,
            has_output,
            has_output_type("function_call"),
        ],
    ),
    TestCase(
        id="streaming-response",
        name="Streaming Response",
        description="SSE streaming events, lifecycle ordering, and terminal event",
        category=TestCategory.STREAMING,
        streaming=True,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "Count from 1 to 5.",
                }
            ],
        },
        validators=[
            streaming_has_events,
            streaming_lifecycle_order,
            streaming_has_terminal,
            streaming_sequence_numbers,
            completed_status,
        ],
    ),
    TestCase(
        id="streaming-usage",
        name="Streaming Usage",
        description="Usage metadata present in final streaming event",
        category=TestCategory.STREAMING,
        streaming=True,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "Say one word.",
                }
            ],
        },
        validators=[
            streaming_has_events,
            streaming_has_usage,
        ],
    ),
    TestCase(
        id="image-input",
        name="Image Input",
        description="Content with inline base64 image is accepted",
        category=TestCategory.MULTIMODAL,
        build_request=_build_image_input_request,
        validators=[has_response_id, has_output, completed_status],
        skip_reason=lambda cfg: None,  # could check for vision-capable models
    ),
    TestCase(
        id="assistant-phase",
        name="Assistant Message Phase",
        description="Assistant history with phase labels is accepted",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": [
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": "I should answer with the saved number.",
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": "The number is four.",
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": "Repeat only the number.",
                },
            ],
        },
        validators=[has_output, completed_status],
    ),
    TestCase(
        id="response-output-phase-schema",
        name="Response Output Phase Schema",
        description="Schema accepts assistant output with phase labels (local fixture)",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "Say one word.",
                }
            ],
        },
        validators=[
            has_output,
            completed_status,
            _validate_phase_fixture,
        ],
    ),
    TestCase(
        id="compact-response",
        name="Compaction Endpoint",
        description="POST /v1/responses/compact validates compacted response (advisory — many providers lack this endpoint)",
        category=TestCategory.BASIC,
        endpoint="/responses/compact",
        schema_name=None,
        expected_statuses=[200, 404],
        build_request=lambda cfg: {
            "model": cfg.model,
            "prompt_cache_key": "openresponses-compact-test",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "We agreed to launch on Tuesday and notify support first.",
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": "Understood. The launch is Tuesday, with support notified beforehand.",
                },
            ],
        },
        validators=[
            _compact_warn_has_output,
            _compact_warn_object,
            _compact_warn_has_compaction,
        ],
    ),
    TestCase(
        id="compact-missing-model",
        name="Compaction Missing Required Model",
        description="Compact request without model field is rejected (advisory — many providers lack this endpoint)",
        category=TestCategory.ERROR_HANDLING,
        endpoint="/responses/compact",
        schema_name=None,
        build_request=lambda cfg: {
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "Compact this conversation.",
                }
            ],
        },
        expected_statuses=[400, 404, 422],
        validators=[],
    ),
    TestCase(
        id="reasoning-summary",
        name="Reasoning Summary",
        description="reasoning.effort + reasoning.summary produces reasoning output with summary content",
        category=TestCategory.BASIC,
        build_request=lambda cfg: {
            "model": cfg.model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "What is 15 * 37? Show your reasoning.",
                }
            ],
            "reasoning": {
                "effort": "low",
                "summary": "auto",
            },
        },
        validators=[
            has_response_id,
            has_output,
            completed_status,
            has_usage,
            responses_has_reasoning_summary,
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
        id="error-handling",
        name="Error Handling",
        description="Invalid request returns correct error format",
        category=TestCategory.ERROR_HANDLING,
        build_request=lambda cfg: {
            # missing model field
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "test",
                }
            ],
        },
        expected_statuses=[400, 422],
        schema_name=None,
        validators=[],
    ),
]
