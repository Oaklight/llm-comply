#!/usr/bin/env python3
"""Verify Chat Completions message payload rules."""

from __future__ import annotations

import sys

from llm_comply.test_case import ValidatorContext
from llm_comply.validators import chat_has_message


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

    print("chat message validators: every payload field is accepted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
