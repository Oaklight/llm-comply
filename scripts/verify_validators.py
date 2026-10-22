#!/usr/bin/env python3
"""Verify Chat Completions message payload rules."""

from __future__ import annotations

import sys
from typing import Any
import base64

from llm_comply.config import ComplianceConfig
from llm_comply.test_case import ValidatorContext
from llm_comply.tests import get_tests
from llm_comply.tests.anthropic import _WEATHER_OUTPUT_SCHEMA as _ANTH_JSON_SCHEMA
from llm_comply.tests.google_genai import (
    _WEATHER_OUTPUT_SCHEMA,
    _WEATHER_RESPONSE_SCHEMA,
)
from llm_comply.validators import (
    anth_cache_used,
    anth_has_content_block_of_type,
    anth_has_code_execution,
    anth_has_input_tokens,
    anth_max_tokens_honoured,
    anth_output_is_json,
    anth_output_matches_json_schema,
    anth_stop_sequence,
    anth_streaming_content_block_bracketing,
    chat_has_message,
    chat_has_audio,
    chat_has_completion_token_details,
    chat_has_prompt_token_details,
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
    google_has_code_execution,
    google_has_grounding_metadata,
    google_has_thought_parts,
    google_has_thoughts_token_count,
    google_output_is_json,
    google_output_matches_json_schema,
    google_streaming_has_finish,
    google_streaming_has_text,
    google_usage_valid_modalities,
    has_usage,
    interactions_has_step_of_type,
    responses_error_body,
    responses_output_contains,
    responses_output_is_json,
    responses_output_matches_json_schema,
    responses_streaming_output_text,
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

    assert (
        responses_error_body(
            {
                "type": "invalid_request_error",
                "code": "missing_model",
                "message": "model is required",
                "param": "model",
            },
            ctx,
        )
        == []
    )
    assert (
        responses_error_body(
            {"type": "error", "code": None, "message": "bad request", "param": None},
            ctx,
        )
        == []
    )
    assert responses_error_body({"error": {"message": "bad request"}}, ctx) == []
    assert responses_error_body({}, ctx) == [
        "error payload is missing fields: type, code, message, param"
    ]
    assert responses_error_body({"error": {}}, ctx) == [
        "error.message is missing or empty"
    ]
    assert responses_error_body({"error": {"message": ""}}, ctx) == [
        "error.message is missing or empty"
    ]
    assert responses_error_body(
        {"type": "error", "code": None, "message": "", "param": None}, ctx
    ) == ["error payload message is missing or empty"]
    assert responses_error_body({"error": "nope"}, ctx) == ["error is not an object"]
    assert responses_error_body("nope", ctx) == ["error response is not a JSON object"]
    responses_error = {tc.id: tc for tc in get_tests("open_responses")}[
        "error-handling"
    ]
    assert [getattr(v, "__qualname__", "") for v in responses_error.validators] == [
        "responses_error_body"
    ]
    openai_error = {tc.id: tc for tc in get_tests("openai_responses")}[
        "openai-error-handling"
    ]
    assert "responses_error_body" in [
        getattr(v, "__qualname__", "") for v in openai_error.validators
    ]

    contains = responses_output_contains("42")
    assert (
        contains(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "42"}],
                    }
                ]
            },
            ctx,
        )
        == []
    )
    assert contains(
        {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "41"}],
                }
            ]
        },
        ctx,
    ) == ["output_text does not contain '42'"]
    assert contains({"output": []}, ctx) == ["no output_text content to inspect"]
    assert responses_output_contains("")({"output": []}, ctx) == [
        "expected text is empty"
    ]
    openai_file = {tc.id: tc for tc in get_tests("openai_responses")}[
        "openai-file-input"
    ]
    assert openai_file.schema_name == "Response"
    file_test = {tc.id: tc for tc in get_tests("open_responses")}["file-input"]
    assert file_test.schema_name == "ResponseResource"
    assert "responses_output_contains('42')" in [
        getattr(v, "__qualname__", "") for v in file_test.validators
    ]
    file_request = file_test.build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    file_content = file_request["input"][0]["content"]
    assert file_content[1]["type"] == "input_file"
    assert file_content[1]["filename"] == "answer.txt"
    assert base64.b64decode(file_content[1]["file_data"]) == (
        b"The answer inside this file is 42.\n"
    )

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

    json_candidate = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": '{"city": "SF", "temperature_c": 18}'}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ]
    }
    assert google_output_is_json(json_candidate, ctx) == []
    weather = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "temperature_c": {"type": "number"},
        },
        "required": ["city", "temperature_c"],
    }
    assert google_output_matches_json_schema(weather)(json_candidate, ctx) == []
    assert any(
        "not valid JSON" in error
        for error in google_output_is_json(
            {"candidates": [{"content": {"parts": [{"text": "nope"}]}}]}, ctx
        )
    )
    assert google_output_is_json("not-an-object", ctx) == [
        "no text part to parse as JSON"
    ]
    assert google_output_is_json({"candidates": []}, ctx) == [
        "no text part to parse as JSON"
    ]
    assert any(
        "does not match" in error
        for error in google_output_matches_json_schema(weather)(
            {"candidates": [{"content": {"parts": [{"text": "[1, 2]"}]}}]}, ctx
        )
    )
    google_tests = {tc.id: tc for tc in get_tests("google_generate")}
    assert "google-structured-output" in google_tests
    names = [
        getattr(v, "__name__", "")
        for v in google_tests["google-structured-output"].validators
    ]
    qualnames = [
        getattr(v, "__qualname__", "")
        for v in google_tests["google-structured-output"].validators
    ]
    assert "google_output_is_json" in names, "google-structured-output"
    assert "google_output_matches_json_schema" in qualnames, "google-structured-output"
    request = google_tests["google-structured-output"].build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert request["generationConfig"]["responseMimeType"] == "application/json"
    assert request["generationConfig"]["responseSchema"] == _WEATHER_RESPONSE_SCHEMA
    schema_validator = next(
        v
        for v in google_tests["google-structured-output"].validators
        if getattr(v, "__qualname__", "") == "google_output_matches_json_schema"
    )
    assert schema_validator.__schema__ == _WEATHER_OUTPUT_SCHEMA
    assert _WEATHER_RESPONSE_SCHEMA["required"] == _WEATHER_OUTPUT_SCHEMA["required"]
    assert _WEATHER_RESPONSE_SCHEMA["properties"].keys() == (
        _WEATHER_OUTPUT_SCHEMA["properties"].keys()
    )
    for key, prop in _WEATHER_RESPONSE_SCHEMA["properties"].items():
        assert prop["type"].lower() == _WEATHER_OUTPUT_SCHEMA["properties"][key]["type"]

    # Thought parts are not output text; the JSON answer must still parse.
    thought_candidate = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "thinking", "thought": True},
                        {"text": '{"city": "SF", "temperature_c": 18}'},
                    ],
                    "role": "model",
                }
            }
        ]
    }
    assert google_output_is_json(thought_candidate, ctx) == []
    assert google_output_matches_json_schema(weather)(thought_candidate, ctx) == []

    grounding = {"candidates": [{"groundingMetadata": {"webSearchQueries": ["x"]}}]}
    assert google_has_grounding_metadata(grounding, ctx) == []
    assert (
        google_has_grounding_metadata(
            {
                "candidates": [
                    {
                        "groundingMetadata": {
                            "searchEntryPoint": {"renderedContent": "x"}
                        }
                    }
                ]
            },
            ctx,
        )
        == []
    )
    assert (
        google_has_grounding_metadata(
            {"candidates": [{"grounding_metadata": {"web_search_queries": ["x"]}}]}, ctx
        )
        == []
    )
    # Grounding chunks are the field real grounded responses usually carry,
    # so each spelling needs a chunk-only positive.
    for metadata in (
        {"groundingChunks": [{"web": {"uri": "https://example.com"}}]},
        {"grounding_chunks": [{"web": {"uri": "https://example.com"}}]},
        {"retrievalMetadata": {"googleSearchDynamicRetrievalScore": 0.9}},
        {"imageSearchQueries": ["cat"]},
    ):
        assert (
            google_has_grounding_metadata(
                {"candidates": [{"groundingMetadata": metadata}]}, ctx
            )
            == []
        ), metadata
    for empty in (
        {"candidates": []},
        {"candidates": [{"groundingMetadata": {}}]},
        {"candidates": [{"groundingMetadata": {"webSearchQueries": []}}]},
        {"candidates": [{"groundingMetadata": {"unrelated": 1}}]},
        {"candidates": [{"groundingMetadata": {"googleMapsWidgetContextToken": "x"}}]},
    ):
        assert google_has_grounding_metadata(empty, ctx) == [
            "groundingMetadata is missing or has no grounding fields"
        ]
    code_part = {"executableCode": {"language": "PYTHON", "code": "1"}}
    result_part = {"codeExecutionResult": {"outcome": "OUTCOME_OK", "output": "55"}}
    code_execution = {"candidates": [{"content": {"parts": [code_part, result_part]}}]}
    assert google_has_code_execution(code_execution, ctx) == []
    # A model may retry after a failed run; the successful attempt counts.
    retried = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        code_part,
                        {"codeExecutionResult": {"outcome": "OUTCOME_FAILED"}},
                        {"executableCode": {"language": "PYTHON", "code": "2"}},
                        {
                            "codeExecutionResult": {
                                "outcome": "OUTCOME_DEADLINE_EXCEEDED"
                            }
                        },
                        result_part,
                    ]
                }
            }
        ]
    }
    assert google_has_code_execution(retried, ctx) == []
    all_failed = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        code_part,
                        {"codeExecutionResult": {"outcome": "OUTCOME_FAILED"}},
                        {
                            "codeExecutionResult": {
                                "outcome": "OUTCOME_DEADLINE_EXCEEDED"
                            }
                        },
                    ]
                }
            }
        ]
    }
    assert google_has_code_execution(all_failed, ctx) == [
        "code execution did not succeed: OUTCOME_DEADLINE_EXCEEDED"
    ]
    snake_code_execution = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"executable_code": {"language": "PYTHON", "code": "1"}},
                        {
                            "code_execution_result": {
                                "outcome": "OUTCOME_OK",
                                "output": "55",
                            }
                        },
                    ]
                }
            }
        ]
    }
    assert google_has_code_execution(snake_code_execution, ctx) == []
    assert google_has_code_execution(
        {"candidates": [{"content": {"parts": [code_part]}}]}, ctx
    ) == ["executableCode carried but no codeExecutionResult"]
    assert google_has_code_execution(
        {"candidates": [{"content": {"parts": [result_part]}}]}, ctx
    ) == ["no part carried executableCode"]
    failed_part = {"codeExecutionResult": {"outcome": "OUTCOME_FAILED", "output": ""}}
    assert google_has_code_execution(
        {"candidates": [{"content": {"parts": [code_part, failed_part]}}]}, ctx
    ) == ["code execution did not succeed: OUTCOME_FAILED"]
    # success followed by a later failure: any successful run still counts,
    # so the check cannot be satisfied by looking only at the last result.
    succeeded_then_failed = {
        "candidates": [{"content": {"parts": [code_part, result_part, failed_part]}}]
    }
    assert google_has_code_execution(succeeded_then_failed, ctx) == []
    assert google_has_code_execution({"candidates": []}, ctx) == [
        "no part carried executableCode"
    ]
    assert google_tests["google-grounding"].optional
    assert google_tests["google-code-execution"].optional
    for test_id, validator_name in (
        ("google-grounding", "google_has_grounding_metadata"),
        ("google-code-execution", "google_has_code_execution"),
    ):
        qualnames = [
            getattr(v, "__qualname__", "") for v in google_tests[test_id].validators
        ]
        assert validator_name in qualnames, (test_id, qualnames)
    grounding_request = google_tests["google-grounding"].build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert grounding_request["tools"] == [{"googleSearch": {}}]
    code_request = google_tests["google-code-execution"].build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert code_request["tools"] == [{"codeExecution": {}}]

    step_check = interactions_has_step_of_type(
        "google_search_call", "google_search_result"
    )
    assert (
        step_check(
            {
                "steps": [
                    {"type": "google_search_call"},
                    {"type": "google_search_result"},
                ]
            },
            ctx,
        )
        == []
    )
    assert any(
        "missing step types" in error
        for error in step_check({"steps": [{"type": "google_search_call"}]}, ctx)
    )
    assert step_check({"steps": "nope"}, ctx) == [
        "response.steps is missing or not an array"
    ]
    interaction_tests = {tc.id: tc for tc in get_tests("google_interactions")}
    expected_steps = {
        "interactions-google-search": ("google_search_call", "google_search_result"),
        "interactions-code-execution": (
            "code_execution_call",
            "code_execution_result",
        ),
        "interactions-google-maps": ("google_maps_call", "google_maps_result"),
        "interactions-url-context": ("url_context_call", "url_context_result"),
    }
    for test_id, expected in expected_steps.items():
        assert test_id in interaction_tests, test_id
        assert interaction_tests[test_id].optional, test_id
        qualnames = [
            getattr(v, "__qualname__", "")
            for v in interaction_tests[test_id].validators
        ]
        assert any(
            all(step_type in qualname for step_type in expected)
            for qualname in qualnames
        ), test_id
        names = [
            getattr(v, "__name__", "") for v in interaction_tests[test_id].validators
        ]
        assert "interactions_has_steps" in names, test_id
        assert any("interactions_status('completed')" in q for q in qualnames), test_id
        request = interaction_tests[test_id].build_request(
            ComplianceConfig(base_url="http://x", api_key="k", model="test")
        )
        expected_tool = expected[0].removesuffix("_call")
        assert request["tools"] == [{"type": expected_tool}], test_id

    # Completion-token details are advisory: absent is a warning, present
    # values must be integers.
    details_ok = {"usage": {"completion_tokens_details": {"reasoning_tokens": 3}}}
    assert chat_has_completion_token_details(details_ok, ctx) == []
    assert chat_has_completion_token_details({"usage": {}}, ctx) == [
        "[warning] usage.completion_tokens_details is missing"
    ]
    assert chat_has_completion_token_details(
        {"usage": {"completion_tokens_details": "nope"}}, ctx
    ) == ["[warning] usage.completion_tokens_details is not an object"]
    assert chat_has_completion_token_details(
        {"usage": {"completion_tokens_details": None}}, ctx
    ) == ["[warning] usage.completion_tokens_details is not an object"]
    for field in (
        "accepted_prediction_tokens",
        "audio_tokens",
        "reasoning_tokens",
        "rejected_prediction_tokens",
        "text_tokens",
    ):
        assert any(
            f"{field} is not an integer" in error
            for error in chat_has_completion_token_details(
                {"usage": {"completion_tokens_details": {field: "3"}}},
                ctx,
            )
        ), field

    assert (
        chat_has_prompt_token_details(
            {"usage": {"prompt_tokens_details": {"cached_tokens": 2}}}, ctx
        )
        == []
    )
    assert chat_has_prompt_token_details({"usage": {}}, ctx) == [
        "[warning] usage.prompt_tokens_details is missing"
    ]
    for field in (
        "audio_tokens",
        "cache_write_tokens",
        "cached_tokens",
        "image_tokens",
        "text_tokens",
    ):
        assert any(
            f"{field} is not an integer" in error
            for error in chat_has_prompt_token_details(
                {"usage": {"prompt_tokens_details": {field: "3"}}},
                ctx,
            )
        ), field
    chat_tests = {tc.id: tc for tc in get_tests("chat_completions")}
    names = [
        getattr(v, "__name__", "") for v in chat_tests["chat-basic-response"].validators
    ]
    assert "chat_has_completion_token_details" in names, "chat-basic-response"
    assert "chat_has_prompt_token_details" in names, "chat-basic-response"
    assert "chat-audio-output" in chat_tests
    audio_message = {
        "role": "assistant",
        "content": None,
        "audio": {
            "id": "audio_1",
            "data": "AAAA",
            "transcript": "hi",
            "expires_at": 1,
        },
    }
    assert chat_has_message(_response(audio_message), ctx) == []
    assert chat_has_audio(_response(audio_message), ctx) == []
    for field in ("id", "data", "transcript"):
        missing = dict(audio_message["audio"])
        missing.pop(field)
        assert any(
            f"audio.{field} is missing or empty" in error
            for error in chat_has_audio(
                _response({**audio_message, "audio": missing}), ctx
            )
        ), field
        empty = dict(audio_message["audio"])
        empty[field] = ""
        assert any(
            f"audio.{field} is missing or empty" in error
            for error in chat_has_audio(
                _response({**audio_message, "audio": empty}), ctx
            )
        ), field
    assert any(
        "audio is missing" in error
        for error in chat_has_audio(
            _response({"role": "assistant", "content": "hi"}), ctx
        )
    )
    assert any(
        "expires_at" in error
        for error in chat_has_audio(
            _response(
                {
                    "role": "assistant",
                    "content": None,
                    "audio": audio_message["audio"] | {"expires_at": "1"},
                }
            ),
            ctx,
        )
    )
    audio_names = [
        getattr(v, "__name__", "") for v in chat_tests["chat-audio-output"].validators
    ]
    assert "chat_has_audio" in audio_names, "chat-audio-output"
    assert chat_tests["chat-audio-output"].schema_name == "CreateChatCompletionResponse"
    audio_case = chat_tests["chat-audio-output"]
    assert audio_case.skip_reason is not None
    assert (
        audio_case.skip_reason(
            ComplianceConfig(
                base_url="http://x", api_key="k", model="gpt-4o-audio-preview"
            )
        )
        is None
    )
    assert (
        audio_case.skip_reason(
            ComplianceConfig(base_url="http://x", api_key="k", model="gpt-4o-mini")
        )
        is not None
    )
    assert chat_tests["chat-error-handling"].schema_name == "ErrorResponse"
    assert "chat-web-search" in chat_tests
    assert chat_tests["chat-web-search"].schema_name == "CreateChatCompletionResponse"

    def _event(event_type: str, index: int | None = None) -> dict:
        data = {"type": event_type}
        if index is not None:
            data["index"] = index
        return {"type": event_type, "data": data}

    block_ctx = ValidatorContext(
        streaming=True,
        sse_events=[
            _event("message_start"),
            _event("content_block_start", 0),
            _event("content_block_delta", 0),
            _event("content_block_stop", 0),
            _event("content_block_start", 1),
            _event("content_block_stop", 1),
            _event("message_delta"),
            _event("message_stop"),
        ],
    )
    assert anth_streaming_content_block_bracketing(None, block_ctx) == []

    open_block = ValidatorContext(
        streaming=True,
        sse_events=[_event("content_block_start", 0)],
    )
    assert any(
        "has no content_block_stop" in error
        for error in anth_streaming_content_block_bracketing(None, open_block)
    )

    stray_stop = ValidatorContext(
        streaming=True,
        sse_events=[_event("content_block_stop", 2)],
    )
    assert any(
        "without a preceding start" in error
        for error in anth_streaming_content_block_bracketing(None, stray_stop)
    )

    double_start = ValidatorContext(
        streaming=True,
        sse_events=[
            _event("content_block_start", 0),
            _event("content_block_start", 0),
        ],
    )
    assert any(
        "already open" in error
        for error in anth_streaming_content_block_bracketing(None, double_start)
    )

    malformed = ValidatorContext(
        streaming=True,
        sse_events=[
            {"type": "content_block_start", "data": {"type": "content_block_start"}},
            {"type": "content_block_stop", "data": None},
        ],
    )
    malformed_errors = anth_streaming_content_block_bracketing(None, malformed)
    assert any("has no integer index" in error for error in malformed_errors), (
        malformed_errors
    )
    assert any("has no data object" in error for error in malformed_errors), (
        malformed_errors
    )
    anth_tests = {tc.id: tc for tc in get_tests("messages")}
    names = [
        getattr(v, "__name__", "")
        for v in anth_tests["anth-streaming-response"].validators
    ]
    assert "anth_streaming_content_block_bracketing" in names, "anth-streaming-response"

    block_check = anth_has_content_block_of_type(
        "server_tool_use", "web_search_tool_result"
    )
    assert (
        block_check(
            {
                "content": [
                    {"type": "text"},
                    {"type": "server_tool_use"},
                    {"type": "web_search_tool_result"},
                ]
            },
            ctx,
        )
        == []
    )
    assert block_check({"content": [{"type": "server_tool_use"}]}, ctx) == [
        "content is missing block types: web_search_tool_result"
    ]
    assert block_check({"content": "nope"}, ctx) == [
        "response.content is missing or not an array"
    ]
    assert block_check("nope", ctx) == ["response is not a JSON object"]
    assert anth_tests["anth-tool-result"].schema_name == "Message"
    assert not anth_tests["anth-tool-result"].optional
    count_tokens = anth_tests["anth-count-tokens"]
    assert count_tokens.endpoint == "/messages/count_tokens"
    assert count_tokens.schema_name == "CountMessageTokensResponse"
    assert [getattr(v, "__qualname__", "") for v in count_tokens.validators] == [
        "anth_has_input_tokens"
    ]
    count_request = count_tokens.build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert count_request == {
        "model": "test",
        "messages": [{"role": "user", "content": "Count the tokens in this sentence."}],
    }
    assert anth_has_input_tokens({"input_tokens": 5}, ctx) == []
    assert anth_has_input_tokens({"input_tokens": 0}, ctx) == [
        "response.input_tokens is not positive: 0"
    ]
    assert anth_has_input_tokens({"input_tokens": "5"}, ctx) == [
        "response.input_tokens is missing or not an integer"
    ]
    assert anth_has_input_tokens({"input_tokens": True}, ctx) == [
        "response.input_tokens is missing or not an integer"
    ]
    assert anth_has_input_tokens("nope", ctx) == ["response is not a JSON object"]
    stop_sequence = anth_stop_sequence("END")
    assert stop_sequence({"stop_sequence": "END"}, ctx) == []
    assert stop_sequence({"stop_sequence": None}, ctx) == [
        "stop_sequence: expected 'END', got None"
    ]
    assert stop_sequence({"stop_sequence": "STOP"}, ctx) == [
        "stop_sequence: expected 'END', got 'STOP'"
    ]
    assert stop_sequence("nope", ctx) == ["response is not a JSON object"]
    assert stop_sequence(
        {
            "stop_sequence": "END",
            "content": [{"type": "text", "text": "Sure, END"}],
        },
        ctx,
    ) == ["output text still contains stop sequence 'END'"]
    assert stop_sequence(
        {"stop_sequence": "END", "content": [{"type": "text", "text": "END END"}]},
        ctx,
    ) == ["output text still contains stop sequence 'END'"]
    assert (
        stop_sequence(
            {"stop_sequence": "END", "content": [{"type": "text", "text": "hello"}]},
            ctx,
        )
        == []
    )
    max_check = anth_max_tokens_honoured(1)
    assert max_check({"usage": {"output_tokens": 1}}, ctx) == []
    assert max_check({"usage": {"output_tokens": 2}}, ctx) == [
        "usage.output_tokens 2 exceeds max_tokens=1"
    ]
    assert max_check({"usage": {"output_tokens": "1"}}, ctx) == [
        "response.usage.output_tokens is missing or not an integer"
    ]
    assert max_check({}, ctx) == ["response.usage is missing or not an object"]
    assert max_check("nope", ctx) == ["response is not a JSON object"]
    cache_test = anth_tests["anth-prompt-cache"]
    assert cache_test.schema_name == "Message"
    assert "anth_cache_used" in [
        getattr(v, "__qualname__", "") for v in cache_test.validators
    ]
    cache_request = cache_test.build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert cache_request["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert len(cache_request["system"][0]["text"]) > 10000
    assert (
        anth_cache_used(
            {
                "usage": {
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 0,
                }
            },
            ctx,
        )
        == []
    )
    assert (
        anth_cache_used(
            {
                "usage": {
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 5,
                }
            },
            ctx,
        )
        == []
    )
    assert anth_cache_used(
        {
            "usage": {
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            }
        },
        ctx,
    ) == [
        "cache was not used: cache_creation_input_tokens=0, cache_read_input_tokens=0"
    ]
    assert anth_cache_used({"usage": {}}, ctx) == [
        "cache was not used: cache_creation_input_tokens=None, "
        "cache_read_input_tokens=None"
    ]
    assert anth_cache_used({}, ctx) == ["response.usage is missing or not an object"]
    assert anth_cache_used("nope", ctx) == ["response is not a JSON object"]
    max_tokens = anth_tests["anth-max-tokens"]
    assert max_tokens.schema_name == "Message"
    assert "anth_stop_reason('max_tokens')" in [
        getattr(v, "__qualname__", "") for v in max_tokens.validators
    ]
    assert "anth_max_tokens_honoured(1)" in [
        getattr(v, "__qualname__", "") for v in max_tokens.validators
    ]
    max_request = max_tokens.build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert max_request["max_tokens"] == 1
    stop_test = anth_tests["anth-stop-sequence"]
    assert stop_test.schema_name == "Message"
    stop_quals = [getattr(v, "__qualname__", "") for v in stop_test.validators]
    assert "anth_stop_reason('stop_sequence')" in stop_quals, stop_quals
    assert "anth_stop_sequence('END')" in stop_quals, stop_quals
    stop_request = stop_test.build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert stop_request["stop_sequences"] == ["END"]
    result_quals = [
        getattr(v, "__qualname__", "")
        for v in anth_tests["anth-tool-result"].validators
    ]
    assert "anth_has_content_block_of_type(text)" in result_quals, result_quals
    result_request = anth_tests["anth-tool-result"].build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    # CreateMessageParams requires model, messages, and max_tokens; without
    # max_tokens the API returns 400, which the optional machinery would read
    # as "capability unsupported" and skip forever.
    assert result_request["max_tokens"] == 1024
    assert result_request["tools"][0]["name"] == "get_weather"
    assert result_request["messages"][1]["content"][0]["type"] == "tool_use"
    result_block = result_request["messages"][2]["content"][0]
    assert result_block["type"] == "tool_result"
    assert result_block["tool_use_id"] == "toolu_01"
    web_search = anth_tests["anth-web-search"]
    assert web_search.optional
    assert web_search.schema_name == "Message"
    web_quals = [getattr(v, "__qualname__", "") for v in web_search.validators]
    assert any(
        "server_tool_use" in qual and "web_search_tool_result" in qual
        for qual in web_quals
    ), web_quals
    web_request = web_search.build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert web_request["max_tokens"] == 1024
    assert web_request["messages"][0]["content"]
    assert web_request["tools"] == [
        {"type": "web_search_20260318", "name": "web_search", "max_uses": 3}
    ]
    code_execution = anth_tests["anth-code-execution"]
    assert code_execution.optional
    assert code_execution.schema_name == "Message"
    ce_quals = [getattr(v, "__qualname__", "") for v in code_execution.validators]
    assert "anth_has_code_execution" in ce_quals, ce_quals
    assert "anth_stop_reason('end_turn')" in ce_quals, ce_quals
    ce_use = {
        "type": "server_tool_use",
        "name": "code_execution",
        "id": "srvtoolu_1",
        "input": {"code": "print(1)"},
    }

    def _ce_result(tool_use_id: str, **inner: Any) -> dict:
        return {
            "type": "code_execution_tool_result",
            "tool_use_id": tool_use_id,
            "content": {
                "type": "code_execution_result",
                "return_code": 0,
                "stdout": "55",
                "stderr": "",
                "content": [],
                **inner,
            },
        }

    ce_ok = {"content": [ce_use, _ce_result("srvtoolu_1")]}
    assert anth_has_code_execution(ce_ok, ctx) == []
    assert anth_has_code_execution(
        {"content": [ce_use, _ce_result("srvtoolu_1", return_code=1)]}, ctx
    ) == ["code execution did not succeed: return_code=1"]
    assert (
        anth_has_code_execution(
            {
                "content": [
                    ce_use,
                    _ce_result("srvtoolu_1", return_code=1),
                    {**ce_use, "id": "srvtoolu_2"},
                    _ce_result("srvtoolu_2"),
                ]
            },
            ctx,
        )
        == []
    )
    assert anth_has_code_execution(
        {"content": [ce_use, _ce_result("srvtoolu_other")]}, ctx
    ) == ["code_execution_tool_result does not match any server_tool_use id"]
    assert anth_has_code_execution({"content": [ce_use]}, ctx) == [
        "no code_execution_tool_result block"
    ]
    assert anth_has_code_execution({"content": [_ce_result("srvtoolu_1")]}, ctx) == [
        "no server_tool_use block for code_execution"
    ]
    assert anth_has_code_execution(
        {
            "content": [
                ce_use,
                {
                    "type": "code_execution_tool_result",
                    "tool_use_id": "srvtoolu_1",
                    "content": {
                        "type": "code_execution_tool_result_error",
                        "error_code": "unavailable",
                    },
                },
            ]
        },
        ctx,
    ) == ["code execution failed: unavailable"]
    assert anth_has_code_execution({"content": "nope"}, ctx) == [
        "response.content is missing or not an array"
    ]
    ce_request = code_execution.build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert ce_request["max_tokens"] == 1024
    assert ce_request["tools"] == [
        {"type": "code_execution_20260521", "name": "code_execution"}
    ]
    json_response = {
        "content": [
            # thinking blocks may carry a text key; it must not enter the payload
            {"type": "thinking", "thinking": "reasoning", "text": "decoy"},
            {"type": "text", "text": '{"city": "SF", "temperature_c": 18}'},
        ]
    }
    assert anth_output_is_json(json_response, ctx) == []
    assert anth_output_matches_json_schema(_ANTH_JSON_SCHEMA)(json_response, ctx) == []
    split_response = {
        "content": [
            {"type": "text", "text": '{"city": "SF", '},
            {"type": "text", "text": '"temperature_c": 18}'},
        ]
    }
    assert anth_output_is_json(split_response, ctx) == []
    assert anth_output_matches_json_schema(_ANTH_JSON_SCHEMA)(split_response, ctx) == []
    assert anth_output_matches_json_schema(_ANTH_JSON_SCHEMA)(
        {"content": [{"type": "text", "text": '{"city": "SF"}'}]}, ctx
    ) == [
        "text blocks do not match the requested schema: "
        "'temperature_c' is a required property"
    ]
    assert anth_output_is_json({"content": []}, ctx) == [
        "no text block to parse as JSON"
    ]
    assert anth_output_is_json(
        {"content": [{"type": "text", "text": "not json"}]}, ctx
    ) == ["text blocks are not valid JSON: Expecting value: line 1 column 1 (char 0)"]
    assert anth_output_matches_json_schema(_ANTH_JSON_SCHEMA)(
        {"content": [{"type": "text", "text": "[1, 2]"}]}, ctx
    ) == [
        "text blocks do not match the requested schema: [1, 2] is not of type 'object'"
    ]
    assert anth_output_is_json({"content": "nope"}, ctx) == [
        "no text block to parse as JSON"
    ]
    structured = anth_tests["anth-structured-output"]
    assert structured.schema_name == "Message"
    structured_quals = [getattr(v, "__qualname__", "") for v in structured.validators]
    assert "anth_output_is_json" in structured_quals, structured_quals
    assert "anth_output_matches_json_schema" in structured_quals, structured_quals
    schema_validator = next(
        v
        for v in structured.validators
        if getattr(v, "__qualname__", "") == "anth_output_matches_json_schema"
    )
    assert schema_validator.__schema__ == _ANTH_JSON_SCHEMA
    structured_request = structured.build_request(
        ComplianceConfig(base_url="http://x", api_key="k", model="test")
    )
    assert structured_request["output_config"]["format"] == {
        "type": "json_schema",
        "schema": _ANTH_JSON_SCHEMA,
    }
    assert structured_request["max_tokens"] == 1024
    print("anthropic streaming: content blocks are correctly bracketed")

    def _delta_event(delta: Any) -> dict:
        return {"type": "response.output_text.delta", "data": {"delta": delta}}

    text_ctx = ValidatorContext(
        streaming=True,
        sse_events=[_delta_event("Count "), _delta_event("to five")],
    )
    assert responses_streaming_output_text(None, text_ctx) == []
    # Providers often open with an empty delta; it is not a failure by itself.
    assert (
        responses_streaming_output_text(
            None,
            ValidatorContext(
                streaming=True,
                sse_events=[_delta_event(""), _delta_event("hi")],
            ),
        )
        == []
    )
    assert responses_streaming_output_text(
        None,
        ValidatorContext(
            streaming=True,
            sse_events=[_delta_event("  "), _delta_event("")],
        ),
    ) == ["response.output_text.delta events carried no text"]
    assert responses_streaming_output_text(
        None, ValidatorContext(streaming=True, sse_events=[])
    ) == ["no SSE events to check"]
    assert responses_streaming_output_text(
        None,
        ValidatorContext(streaming=True, sse_events=[{"type": "response.created"}]),
    ) == ["no response.output_text.delta events found"]
    assert any(
        "is not a string" in error
        for error in responses_streaming_output_text(
            None,
            ValidatorContext(streaming=True, sse_events=[_delta_event(5)]),
        )
    )
    open_tests = {tc.id: tc for tc in get_tests("open_responses")}
    names = [
        getattr(v, "__name__", "") for v in open_tests["streaming-response"].validators
    ]
    assert "responses_streaming_output_text" in names, "streaming-response"
    print("open responses streaming: output text deltas are non-empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
