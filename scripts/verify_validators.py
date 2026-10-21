#!/usr/bin/env python3
"""Verify Chat Completions message payload rules."""

from __future__ import annotations

import sys

from llm_comply.test_case import ValidatorContext
from llm_comply.tests import get_tests
from llm_comply.validators import (
    chat_has_message,
    chat_has_tool_calls,
    chat_message_matches_json_schema,
    compact_object,
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
        ("type", {**call_ok, "type": "custom"}),
        ("name", {**call_ok, "function": {"name": "", "arguments": "{}"}}),
        ("function", {**call_ok, "function": None}),
        ("object", "not-an-object"),
    ):
        errors = chat_has_tool_calls(
            _response({"role": "assistant", "content": None, "tool_calls": [call]}),
            ctx,
        )
        assert errors, label

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
        getattr(v, "__name__", "") for v in chat_tests["chat-tool-calling"].validators
    ]
    assert "chat_has_tool_calls" in names, "chat-tool-calling"

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
