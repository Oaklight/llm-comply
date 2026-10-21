#!/usr/bin/env python3
"""Verify Chat Completions message payload rules."""

from __future__ import annotations

import sys

from llm_comply.test_case import ValidatorContext
from llm_comply.tests import get_tests
from llm_comply.validators import (
    chat_has_message,
    chat_has_tool_call_of_type,
    chat_has_tool_calls,
    chat_message_is_json,
    chat_message_matches_json_schema,
    compact_object,
    google_finish_reason,
    google_function_call_has_id,
    google_has_candidates,
    google_has_content_parts,
    google_has_function_call,
    google_has_thought_parts,
    google_has_thoughts_token_count,
    google_streaming_has_finish,
    google_streaming_has_text,
    google_usage_valid_modalities,
    has_usage,
    responses_output_is_json,
    responses_output_matches_json_schema,
)


def _response(message: dict) -> dict:
    return {"choices": [{"message": message, "finish_reason": "stop"}]}


def main() -> int:
    """Check every payload shape accepted for a non-streaming message."""
    ctx = ValidatorContext()

    # Empty content is valid (a present but empty answer); the other fields
    # count only when they carry something.
    for field, value in (
        ("content", ""),
        ("tool_calls", [{"id": "call_1"}]),
        ("function_call", {"name": "get_weather", "arguments": "{}"}),
        ("refusal", "I cannot help with that."),
        ("reasoning_content", "thinking"),
        ("reasoning", "thinking"),
    ):
        errors = chat_has_message(
            _response({"role": "assistant", "content": None, field: value}), ctx
        )
        assert not errors, (field, errors)

    errors = chat_has_message(_response({"role": "assistant", "content": None}), ctx)
    assert any("has none of" in error for error in errors), errors

    for message in (
        {"role": "assistant", "content": None, "refusal": ""},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "assistant", "content": None, "reasoning_content": ""},
    ):
        errors = chat_has_message(_response(message), ctx)
        assert any("has none of" in error for error in errors), (message, errors)

    errors = chat_has_message(_response({"role": "user", "content": "hi"}), ctx)
    assert any("expected 'assistant'" in error for error in errors), errors

    # The shipped non-streaming cases must keep calling the validator.
    # chat-tool-calling intentionally uses chat_has_tool_calls instead.
    shipped = {tc.id: tc for tc in get_tests("chat_completions")}
    for test_id in (
        "chat-basic-response",
        "chat-system-prompt",
        "chat-multi-turn",
        "chat-image-input",
        "chat-reasoning-summary",
        "chat-developer-role",
        "chat-structured-output",
    ):
        names = [getattr(v, "__name__", "") for v in shipped[test_id].validators]
        assert "chat_has_message" in names, test_id

    # structured-output must keep using the schema-matching validator.
    open_responses = {tc.id: tc for tc in get_tests("open_responses")}
    names = [
        getattr(v, "__qualname__", "")
        for v in open_responses["structured-output"].validators
    ]
    assert "responses_output_matches_json_schema" in names, "structured-output"

    tool_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "f", "arguments": "{}"},
            }
        ],
    }
    assert chat_has_tool_calls(_response(tool_message), ctx) == []
    call_ok = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "f", "arguments": "{}"},
    }
    for label, call in (
        ("id", {**call_ok, "id": ""}),
        ("type", {**call_ok, "type": "function_call"}),
        ("type-absent", {k: v for k, v in call_ok.items() if k != "type"}),
        ("name", {**call_ok, "function": {"name": "", "arguments": "{}"}}),
        ("arguments", {**call_ok, "function": {"name": "f", "arguments": 5}}),
        ("function", {**call_ok, "function": None}),
    ):
        errors = chat_has_tool_calls(
            _response({"role": "assistant", "content": None, "tool_calls": [call]}),
            ctx,
        )
        assert errors, label

    object_errors = chat_has_tool_calls(
        _response(
            {"role": "assistant", "content": None, "tool_calls": ["not-an-object"]}
        ),
        ctx,
    )
    assert any("is not an object" in error for error in object_errors), object_errors

    custom_ok = {
        "id": "call_2",
        "type": "custom",
        "custom": {"name": "f", "input": "{}"},
    }
    assert (
        chat_has_tool_calls(
            _response(
                {"role": "assistant", "content": None, "tool_calls": [custom_ok]}
            ),
            ctx,
        )
        == []
    )
    for label, call in (
        ("custom-name", {**custom_ok, "custom": {"name": "", "input": "{}"}}),
        ("custom-input", {**custom_ok, "custom": {"name": "f", "input": 5}}),
        ("custom", {**custom_ok, "custom": None}),
    ):
        errors = chat_has_tool_calls(
            _response({"role": "assistant", "content": None, "tool_calls": [call]}),
            ctx,
        )
        assert errors, label
    null_custom = chat_has_tool_calls(
        _response(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{**custom_ok, "custom": None}],
            }
        ),
        ctx,
    )
    assert any("custom is missing or not an object" in e for e in null_custom), (
        null_custom
    )

    type_check = chat_has_tool_call_of_type("function")
    assert (
        type_check(
            _response({"role": "assistant", "content": None, "tool_calls": [call_ok]}),
            ctx,
        )
        == []
    )
    custom_type_errors = type_check(
        _response({"role": "assistant", "content": None, "tool_calls": [custom_ok]}),
        ctx,
    )
    assert any("no tool call of type 'function'" in e for e in custom_type_errors), (
        custom_type_errors
    )

    chat_schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "temperature_c": {"type": "number"},
        },
        "required": ["city", "temperature_c"],
    }
    chat_schema_check = chat_message_matches_json_schema(chat_schema)
    assert (
        chat_schema_check(
            _response(
                {"role": "assistant", "content": '{"city": "SF", "temperature_c": 18}'}
            ),
            ctx,
        )
        == []
    )
    assert any(
        "does not match the requested schema" in error
        for error in chat_schema_check(
            _response({"role": "assistant", "content": "[1, 2]"}), ctx
        )
    )
    assert any(
        "not valid JSON" in error
        for error in chat_schema_check(
            _response({"role": "assistant", "content": "nope"}), ctx
        )
    )
    chat_tests = {tc.id: tc for tc in get_tests("chat_completions")}
    names = [
        getattr(v, "__qualname__", "")
        for v in chat_tests["chat-structured-output"].validators
    ]
    assert "chat_message_matches_json_schema" in names, "chat-structured-output"
    names = [
        getattr(v, "__name__", "")
        for v in chat_tests["chat-structured-output"].validators
    ]
    assert "chat_message_is_json" in names, "chat-structured-output"
    assert (
        chat_message_is_json(
            _response({"role": "assistant", "content": '{"a": 1}'}), ctx
        )
        == []
    )
    assert any(
        "not valid JSON" in error
        for error in chat_message_is_json(
            _response({"role": "assistant", "content": "nope"}), ctx
        )
    )
    names = [
        getattr(v, "__qualname__", "")
        for v in chat_tests["chat-tool-calling"].validators
    ]
    assert "chat_has_tool_call_of_type" in names, "chat-tool-calling"

    # Open Responses usage, compaction, and structured output checks.
    usage = {
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    }
    assert has_usage({"usage": usage}, ctx) == []
    assert any(
        "input_tokens_details" in error
        for error in has_usage(
            {"usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}},
            ctx,
        )
    )
    assert any(
        "not an object" in error
        for error in has_usage({"usage": {**usage, "input_tokens_details": None}}, ctx)
    )
    assert any(
        "cached_tokens" in error
        for error in has_usage({"usage": {**usage, "input_tokens_details": {}}}, ctx)
    )

    compact = {
        "object": "response.compaction",
        "id": "cmp_1",
        "output": [],
        "created_at": 1,
        "usage": usage,
    }
    assert compact_object(compact, ctx) == []
    assert any(
        "response.compaction" in error
        for error in compact_object({"object": "compact"}, ctx)
    )
    assert any(
        "response.output is missing" in error
        for error in compact_object(
            {
                "object": "response.compaction",
                "id": "cmp_1",
                "created_at": 1,
                "usage": usage,
            },
            ctx,
        )
    )
    assert any(
        "total_tokens" in error
        for error in compact_object({**compact, "usage": {"input_tokens": 1}}, ctx)
    )

    json_response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"city": "SF", "temperature_c": 18}',
                    }
                ],
            }
        ]
    }
    assert responses_output_is_json(json_response, ctx) == []
    weather_schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "temperature_c": {"type": "number"},
        },
        "required": ["city", "temperature_c"],
    }
    schema_check = responses_output_matches_json_schema(weather_schema)
    assert schema_check(json_response, ctx) == []
    assert any(
        "not valid JSON" in error
        for error in schema_check(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "not json"}],
                    }
                ]
            },
            ctx,
        )
    )
    assert any(
        "does not match the requested schema" in error
        for error in schema_check(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "[1, 2]"}],
                    }
                ]
            },
            ctx,
        )
    )
    assert any(
        "not valid JSON" in error
        for error in responses_output_is_json(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "nope"}],
                    }
                ]
            },
            ctx,
        )
    )

    print("chat message validators: every payload field is accepted")
    print("open responses validators: usage, compaction, and JSON output OK")

    # A malformed candidate container must produce findings, not an exception:
    # the runner shares one try block across validators, so a raise would hide
    # every later check.
    bad = {"responseId": "r1", "candidates": "nope", "usageMetadata": {}}
    google_validators = (
        ("has_candidates", google_has_candidates),
        ("content_parts", google_has_content_parts),
        ("finish_reason", google_finish_reason("STOP")),
        ("function_call", google_has_function_call),
        ("thought_parts", google_has_thought_parts),
        ("function_call_id", google_function_call_has_id),
    )
    for label, validator in google_validators:
        errors = validator(bad, ctx)
        assert isinstance(errors, list), label
    assert google_has_candidates(bad, ctx) == [
        "response.candidates is missing or empty"
    ]
    bad_candidate = {"candidates": [42]}
    assert google_has_candidates(bad_candidate, ctx) == [
        "response.candidates[0] is not an object"
    ]
    for label, validator in google_validators[1:]:
        assert isinstance(validator(bad_candidate, ctx), list), label

    # Reach the content and parts guards that the empty-list helper hides.
    bad_content = {"candidates": [{"content": "nope"}]}
    assert google_has_function_call(bad_content, ctx) == [
        "candidates[0].content is missing or not an object"
    ]
    bad_parts = {"candidates": [{"content": {"parts": "nope"}}]}
    assert google_has_function_call(bad_parts, ctx) == [
        "candidates[0].content.parts is not an array"
    ]

    # Malformed detail entries must be skipped, not crash the modality check.
    bad_details = {
        "usageMetadata": {
            "promptTokensDetails": ["bad", 42, {"modality": "NOT_A_MODALITY"}]
        }
    }
    assert google_usage_valid_modalities(bad_details, ctx) == [
        "promptTokensDetails[].modality: 'NOT_A_MODALITY' is not a valid "
        "Google Modality enum value"
    ]

    # The thought-parts guard needs the same content-level exercise.
    assert google_has_thought_parts({"candidates": [{"content": "nope"}]}, ctx) == [
        "[warning] candidates[0].content.parts is missing or not an array "
        "(model may not emit thoughts at current thinking level)"
    ]

    # The remaining usage-based warning must also tolerate a non-object.
    assert google_has_thoughts_token_count({"usageMetadata": "nope"}, ctx) == [
        "[warning] usageMetadata is missing or not an object "
        "(cannot check thoughtsTokenCount)"
    ]

    stream_ctx = ValidatorContext(
        streaming=True, sse_events=[{"data": {"candidates": "nope"}}]
    )
    assert google_streaming_has_text(None, stream_ctx) == [
        "no streaming chunk contained a text part"
    ]
    assert google_streaming_has_finish(None, stream_ctx) == [
        "no streaming chunk had a finishReason"
    ]

    good = {
        "candidates": [
            {
                "content": {"parts": [{"text": "hi"}], "role": "model"},
                "finishReason": "STOP",
            }
        ]
    }
    assert google_has_candidates(good, ctx) == []
    assert google_has_content_parts(good, ctx) == []
    assert google_finish_reason("STOP")(good, ctx) == []
    print("google validators: malformed candidates fail without raising")
    return 0


if __name__ == "__main__":
    sys.exit(main())
