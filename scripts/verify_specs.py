#!/usr/bin/env python3
"""Verify bundled specs and the schema behavior CI depends on."""

from __future__ import annotations

import pathlib
import sys

from llm_comply.formats import VALIDATION_SPEC_FILES
from llm_comply.schema import SpecLoader

SPECS_DIR = pathlib.Path(__file__).resolve().parent.parent / "src/llm_comply/specs"

CHAT_STREAM_CHUNK = {
    "id": "chatcmpl-1",
    "object": "chat.completion.chunk",
    "created": 1,
    "model": "m",
    "choices": [
        {
            "index": 0,
            "delta": {"content": "hi"},
            "finish_reason": None,
            "logprobs": None,
        }
    ],
}


def main() -> int:
    """Run the bundled-spec assertions."""
    responses = SpecLoader(str(SPECS_DIR / "openresponses.json"))
    assert responses.spec_version == "2026-04-24"
    assert responses.validate(
        {"id": "resp_1", "object": "response"}, "ResponseResource"
    ), "incomplete response should have errors"
    print(f"open_responses: {len(responses.schema_names)} schemas")

    chat = SpecLoader(str(SPECS_DIR / "openai_chat.json"))
    assert len(chat.schema_names) > 2000, "bundled OpenAI Chat spec is stale"
    assert "CreateChatCompletionResponse" in chat.schema_names
    assert "CreateChatCompletionStreamResponse" in chat.schema_names
    assert chat.validate("none", "ReasoningEffort") == []
    assert chat.validate("xhigh", "ReasoningEffort") == []
    assert chat.validate(CHAT_STREAM_CHUNK, "CreateChatCompletionStreamResponse") == []
    print(f"chat_completions: {len(chat.schema_names)} schemas")

    messages = SpecLoader(str(SPECS_DIR / "anthropic.json"))
    assert len(messages.schema_names) > 1500, "bundled Anthropic spec is stale"
    assert "Message" in messages.schema_names
    assert "diagnostics" in messages.get_schema("Message")["required"]
    assert "speed" in messages.get_schema("Usage")["required"]
    print(f"messages: {len(messages.schema_names)} schemas")

    assert SpecLoader(None).schema_names == []

    for fmt in ("google_generate", "google_interactions"):
        google = SpecLoader(str(SPECS_DIR / f"{fmt}.json"))
        assert len(google.schema_names) > 200, f"bundled {fmt} spec is stale"
        assert VALIDATION_SPEC_FILES[fmt] is None, f"{fmt} should stay semantic"
        print(f"{fmt}: {len(google.schema_names)} schemas (semantic)")
    print("google formats: semantic validation mode")

    problems = SpecLoader.check_manifest()
    assert not problems, f"spec manifest drift: {problems}"
    print("spec manifest matches bundled specs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
