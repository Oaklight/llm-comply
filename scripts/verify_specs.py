#!/usr/bin/env python3
"""Verify bundled specs and the schema behavior CI depends on."""

from __future__ import annotations

import json
import pathlib
import sys

from llm_comply.formats import VALIDATION_SPEC_FILES
from llm_comply.schema import SpecLoader, canonical_spec

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

    openai_responses = SpecLoader(str(SPECS_DIR / "openai_responses.json"))
    assert len(openai_responses.schema_names) > 300, (
        "bundled OpenAI Responses spec is stale"
    )
    assert "Response" in openai_responses.schema_names
    assert "ResponseStreamEvent" in openai_responses.schema_names
    assert openai_responses.validate(
        {"id": "resp_1", "object": "response"}, "Response"
    ), "incomplete response should have errors"
    assert not openai_responses.validate_sse_event(
        "error",
        {
            "type": "error",
            "code": "server_error",
            "message": "boom",
            "param": None,
            "sequence_number": 1,
        },
    ), "SSE error events must validate against ResponseErrorEvent"
    subset = json.loads((SPECS_DIR / "openai_responses.json").read_text())
    schemes = set(subset.get("components", {}).get("securitySchemes", {}))
    for requirement in subset.get("security", []):
        assert set(requirement) <= schemes, (
            f"unresolved security scheme in openai_responses: {requirement}"
        )
    print(f"openai_responses: {len(openai_responses.schema_names)} schemas")

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

    assert canonical_spec({"b": 1, "a": 2}) == canonical_spec({"a": 2, "b": 1})
    assert canonical_spec({"info": {"x-google-revision": "1"}}) == canonical_spec(
        {"info": {"x-google-revision": "2"}}
    )
    print("canonical spec comparison ignores key order and volatile metadata")

    problems = SpecLoader.check_manifest()
    assert not problems, f"spec manifest drift: {problems}"
    print("spec manifest matches bundled specs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
