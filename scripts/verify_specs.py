#!/usr/bin/env python3
"""Verify bundled specs and the schema behavior CI depends on."""

from __future__ import annotations

import json
import pathlib
import re
import sys

from llm_comply.formats import VALIDATION_SPEC_FILES
from llm_comply.config import ComplianceConfig
from llm_comply.schema import SpecLoader, canonical_spec
from llm_comply.spec_extract import extract_openai_responses
from llm_comply.spec_relax import _ANTHROPIC_OPTIONAL_FIELDS, _CHAT_NULLABLE_STRINGS
from llm_comply.test_case import TestCategory
from llm_comply.tests import get_tests
from llm_comply.tests.google_genai import _make_test
from llm_comply.validators import _GOOGLE_GROUNDING_FIELDS

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
    raw_responses = json.loads((SPECS_DIR / "openresponses.json").read_text())
    assert raw_responses["components"]["schemas"]["JsonSchemaResponseFormat"][
        "properties"
    ]["schema"] == {"type": "null"}

    responses = SpecLoader(str(SPECS_DIR / "openresponses.json"))
    assert responses.spec_version == "2026-04-24"
    assert responses.validate(
        {"id": "resp_1", "object": "response"}, "ResponseResource"
    ), "incomplete response should have errors"
    print(f"open_responses: {len(responses.schema_names)} schemas")

    # Every shipped success-path request must validate against the spec, so a
    # builder that drifts from CreateResponseBody fails here rather than at a
    # provider.
    responses_config = ComplianceConfig(
        base_url="http://x", api_key="k", model="test-model"
    )
    covered: list[str] = []
    for tc in get_tests("open_responses"):
        if tc.streaming or 200 not in tc.expected_statuses:
            continue
        covered.append(tc.id)
        request = tc.build_request(responses_config)
        # CreateResponseBody declares no required properties, so the schema
        # alone would accept {} or a request missing model/input.
        assert {"model", "input"} <= set(request), tc.id
        assert responses.validate(request, "CreateResponseBody") == [], tc.id
    assert len(covered) == 12, covered
    # OpenAI echoes the requested JSON schema in the response, while the
    # upstream response schema declares it null-only.
    live_format = {
        "type": "json_schema",
        "name": "weather",
        "description": None,
        "strict": True,
        "schema": {"type": "object", "additionalProperties": False},
    }
    assert responses.validate(live_format, "JsonSchemaResponseFormat") == []
    relaxed_schema_prop = responses.get_schema("JsonSchemaResponseFormat")[
        "properties"
    ]["schema"]
    assert relaxed_schema_prop.get("type") == ["object", "null"]

    raw_chat = json.loads((SPECS_DIR / "openai_chat.json").read_text())
    raw_chat_schemas = raw_chat["components"]["schemas"]
    raw_choice = raw_chat_schemas["CreateChatCompletionResponse"]["properties"][
        "choices"
    ]["items"]
    assert "logprobs" in raw_choice["required"]
    for name in ("CreateChatCompletionResponse", "CreateChatCompletionStreamResponse"):
        fp = raw_chat_schemas[name]["properties"]["system_fingerprint"]
        assert fp.get("type") == "string", name
    for field in _CHAT_NULLABLE_STRINGS:
        assert field in raw_chat_schemas["CreateChatCompletionResponse"]["properties"]

    chat = SpecLoader(str(SPECS_DIR / "openai_chat.json"))
    assert len(chat.schema_names) > 2000, "bundled OpenAI Chat spec is stale"
    assert "CreateChatCompletionResponse" in chat.schema_names
    assert "CreateChatCompletionStreamResponse" in chat.schema_names
    assert chat.validate("none", "ReasoningEffort") == []
    assert chat.validate("xhigh", "ReasoningEffort") == []
    assert chat.validate(CHAT_STREAM_CHUNK, "CreateChatCompletionStreamResponse") == []
    # Live OpenAI responses omit logprobs and return system_fingerprint: null;
    # both are relaxed at load time.
    live_chat = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }
        ],
        "system_fingerprint": None,
    }
    assert chat.validate(live_chat, "CreateChatCompletionResponse") == []
    relaxed_choice = chat.get_schema("CreateChatCompletionResponse")["properties"][
        "choices"
    ]["items"]["required"]
    assert set(raw_choice["required"]) - set(relaxed_choice) == {"logprobs"}
    relaxed_fp = chat.get_schema("CreateChatCompletionResponse")["properties"][
        "system_fingerprint"
    ]
    assert relaxed_fp.get("type") is None
    assert {"type": "string"} in relaxed_fp["anyOf"]
    assert {"type": "null"} in relaxed_fp["anyOf"]
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
    production_response = {
        "id": "resp_1",
        "object": "response",
        "created_at": 1,
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "metadata": {},
        "model": "gpt-4",
        "output": [],
        "parallel_tool_calls": True,
        "temperature": 1,
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1.0,
    }
    assert openai_responses.validate(production_response, "Response") == [], (
        "production responses omit access_programs"
    )
    synthetic = {
        "openapi": "3.1.0",
        "info": {},
        "paths": {
            "/responses": {
                "post": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Response"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Response": {"allOf": [{"required": ["access_programs", "id"]}]}
            }
        },
    }
    extracted = extract_openai_responses(synthetic)
    assert extracted["components"]["schemas"]["Response"]["allOf"][0]["required"] == [
        "id"
    ], "extraction must apply the production relaxation"
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

    raw_messages = json.loads((SPECS_DIR / "anthropic.json").read_text())
    raw_anthropic = raw_messages["components"]["schemas"]
    for schema_name, fields in _ANTHROPIC_OPTIONAL_FIELDS.items():
        for field in fields:
            assert field in raw_anthropic[schema_name]["required"], (
                schema_name,
                field,
            )

    messages = SpecLoader(str(SPECS_DIR / "anthropic.json"))
    assert len(messages.schema_names) > 1500, "bundled Anthropic spec is stale"
    assert "Message" in messages.schema_names
    assert "diagnostics" in messages.get_schema("Message")["required"]
    assert "speed" in messages.get_schema("Usage")["required"]
    # Live Messages API responses omit these fields even though the SDK spec
    # marks them required; the load-time relaxation keeps them optional.
    usage_required = messages.get_schema("Usage")["required"]
    assert "output_tokens_details" not in usage_required
    assert "server_tool_use" not in usage_required
    assert "citations" not in messages.get_schema("ResponseTextBlock")["required"]
    assert "caller" not in messages.get_schema("ResponseServerToolUseBlock")["required"]
    live_usage = {
        "cache_creation": None,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "inference_geo": None,
        "input_tokens": 10,
        "output_tokens": 3,
        "service_tier": "standard",
        "speed": "standard",
    }
    assert messages.validate(live_usage, "Usage") == []
    assert messages.validate({"type": "text", "text": "hi"}, "ResponseTextBlock") == []
    assert "skills" not in messages.get_schema("Container")["required"]
    assert (
        messages.validate(
            {"id": "container_1", "expires_at": "2026-10-22T07:10:04Z"}, "Container"
        )
        == []
    )
    for schema_name, fields in _ANTHROPIC_OPTIONAL_FIELDS.items():
        raw_required = set(raw_anthropic[schema_name]["required"])
        relaxed_required = set(messages.get_schema(schema_name)["required"])
        assert raw_required - relaxed_required == set(fields), schema_name
        assert relaxed_required <= raw_required, schema_name
    print(f"messages: {len(messages.schema_names)} schemas")

    # The tool tests must build requests the API accepts: a 400 caused by a
    # malformed request would look like "capability unsupported" and turn the
    # optional web-search test into a permanent skip.
    anth_config = ComplianceConfig(base_url="http://x", api_key="k", model="test-model")
    anth_covered: list[str] = []
    for test_case in get_tests("messages"):
        if (
            test_case.streaming
            or test_case.category == TestCategory.ERROR_HANDLING
            or test_case.endpoint != "/messages"
            or 200 not in test_case.expected_statuses
        ):
            continue
        anth_covered.append(test_case.id)
        request = test_case.build_request(anth_config)
        assert messages.validate(request, "CreateMessageParams") == [], test_case.id
    # Pin the breadth: dropping a test from this loop should not be silent.
    assert len(anth_covered) == 14, anth_covered
    count_case = next(
        tc for tc in get_tests("messages") if tc.id == "anth-count-tokens"
    )
    count_request = count_case.build_request(anth_config)
    assert messages.validate(count_request, "CountMessageTokensParams") == []
    # Pin the params schema's strictness on its own, so deleting the check
    # above cannot silently drop this property.
    assert messages.validate(
        {**count_request, "surprise": 1}, "CountMessageTokensParams"
    ), "CountMessageTokensParams should reject unknown fields"

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

    # The grounding field list is a hand-maintained copy of the spec's
    # GroundingMetadata.properties. Tie it to the bundled spec so a refresh
    # that adds a field forces a decision instead of silently narrowing the
    # validator. The maps widget token is excluded on purpose: it renders a
    # widget and is not evidence that a search returned results.
    grounding_schema = google_generate.get_schema("GroundingMetadata")
    assert grounding_schema is not None, "GroundingMetadata missing from spec"
    grounding_properties = set(grounding_schema.get("properties", {}))
    grounding_exclusions = {"googleMapsWidgetContextToken"}
    listed_camel = {f for f in _GOOGLE_GROUNDING_FIELDS if "_" not in f}
    assert listed_camel | grounding_exclusions == grounding_properties, (
        listed_camel,
        grounding_properties,
    )
    listed_snake = {f for f in _GOOGLE_GROUNDING_FIELDS if "_" in f}
    expected_snake = {
        re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower() for field in listed_camel
    }
    assert listed_snake == expected_snake, (listed_snake, expected_snake)

    # Every shipped success-path test must carry the response schema.
    for tc in get_tests("google_generate"):
        if 200 in tc.expected_statuses and not tc.streaming:
            assert tc.schema_name == "GenerateContentResponse", tc.id
        if tc.streaming:
            assert tc.stream_schema_name == "GenerateContentResponse", tc.id
            assert tc.validate_stream_events, tc.id

    # Lock the mixed-status branch in both directions: a test that can return
    # 200 must validate the success body, while an error-only test must not.
    def _status_test(statuses: list[int]):
        return _make_test(
            id="status-test",
            name="Status Test",
            description="",
            category=TestCategory.BASIC,
            build_request=lambda cfg: {},
            validators=[],
            expected_statuses=statuses,
        )

    assert _status_test([200, 500]).schema_name == "GenerateContentResponse"
    assert _status_test([429, 200, 500]).schema_name == "GenerateContentResponse"
    assert _status_test([500]).schema_name is None

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
