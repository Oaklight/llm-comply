#!/usr/bin/env python3
"""Verify Chat Completions message payload rules."""

from __future__ import annotations

import sys

from llm_comply.test_case import ValidatorContext
from llm_comply.tests import get_tests
from llm_comply.validators import (
    chat_has_message,
    compact_object,
    has_usage,
    responses_output_is_json,
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
    ):
        names = [getattr(v, "__name__", "") for v in shipped[test_id].validators]
        assert "chat_has_message" in names, test_id

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

    json_response = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": '{"city": "SF"}'}],
            }
        ]
    }
    assert responses_output_is_json(json_response, ctx) == []
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
