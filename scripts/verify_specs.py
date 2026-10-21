#!/usr/bin/env python3
"""Verify bundled specs and the schema behavior CI depends on."""

from __future__ import annotations

import json
import pathlib
import sys

from llm_comply.formats import VALIDATION_SPEC_FILES
from llm_comply.schema import SpecLoader, canonical_spec
from llm_comply.tests import get_tests

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

    google_generate = SpecLoader(str(SPECS_DIR / "google_generate.json"))
    assert len(google_generate.schema_names) > 200, (
        "bundled google_generate spec is stale"
    )
    assert VALIDATION_SPEC_FILES["google_generate"] == "google_generate.json"
    google_response = {
        "candidates": [
            {
                "content": {"parts": [{"text": "Hello"}], "role": "model"},
                "finishReason": "STOP",
                "index": 0,
                "safetyRatings": [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "probability": "NEGLIGIBLE",
                    }
                ],
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 2,
            "totalTokenCount": 7,
        },
        "modelVersion": "gemini-2.5-flash",
        "responseId": "resp_1",
    }
    assert google_generate.validate(google_response, "GenerateContentResponse") == []
    assert google_generate.validate(
        {"candidates": [{"finishReason": "NOT_A_REASON"}]}, "GenerateContentResponse"
    ), "invalid finishReason should have errors"
    print(f"google_generate: {len(google_generate.schema_names)} schemas (schema)")

    # Every shipped success-path test must carry the response schema.
    for tc in get_tests("google_generate"):
        if 200 in tc.expected_statuses and not tc.streaming:
            assert tc.schema_name == "GenerateContentResponse", tc.id
        if tc.streaming:
            assert tc.stream_schema_name == "GenerateContentResponse", tc.id
            assert tc.validate_stream_events, tc.id

    google_interactions = SpecLoader(str(SPECS_DIR / "google_interactions.json"))
    assert len(google_interactions.schema_names) > 200, (
        "bundled google_interactions spec is stale"
    )
    assert VALIDATION_SPEC_FILES["google_interactions"] is None, (
        "google_interactions should stay semantic"
    )
    print(
        f"google_interactions: {len(google_interactions.schema_names)} schemas (semantic)"
    )

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
