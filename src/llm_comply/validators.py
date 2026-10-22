"""Validator functions for compliance tests."""

from __future__ import annotations

import json
from typing import Any

import jsonschema

from .test_case import Validator, ValidatorContext


def has_output(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a non-empty output array."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    output = response.get("output")
    if not isinstance(output, list) or len(output) == 0:
        return ["response.output is missing or empty"]
    return []


def _output_text(response: Any) -> str | None:
    """Concatenate ``output_text`` content, or return None when absent."""
    if not isinstance(response, dict):
        return None
    texts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if isinstance(part, dict) and part.get("type") == "output_text":
                texts.append(str(part.get("text", "")))
    return "".join(texts) if texts else None


def responses_output_is_json(response: Any, ctx: ValidatorContext) -> list[str]:
    """Concatenated output_text content must parse as JSON."""
    text = _output_text(response)
    if text is None:
        return ["no output_text content to parse as JSON"]
    try:
        json.loads(text)
    except ValueError as exc:
        return [f"output_text is not valid JSON: {exc}"]
    return []


def responses_output_contains(expected: str) -> Validator:
    """Factory: concatenated output_text must contain *expected*."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not expected:
            return ["expected text is empty"]
        text = _output_text(response)
        if text is None:
            return ["no output_text content to inspect"]
        if expected not in text:
            return [f"output_text does not contain {expected!r}"]
        return []

    _check.__qualname__ = f"responses_output_contains({expected!r})"
    return _check


def responses_output_matches_json_schema(schema: dict[str, Any]) -> Validator:
    """Factory: parsed output_text must validate against *schema*."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        text = _output_text(response)
        if text is None:
            return ["no output_text content to parse as JSON"]
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            return [f"output_text is not valid JSON: {exc}"]
        try:
            jsonschema.validate(parsed, schema)
        except jsonschema.ValidationError as exc:
            return [f"output_text does not match the requested schema: {exc.message}"]
        return []

    _check.__qualname__ = "responses_output_matches_json_schema"
    return _check


def completed_status(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response status must be 'completed'."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    status = response.get("status")
    if status != "completed":
        return [f"expected status='completed', got '{status}'"]
    return []


def has_response_id(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a non-empty id field."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    rid = response.get("id")
    if not rid or not isinstance(rid, str):
        return ["response.id is missing or empty"]
    return []


def has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a usage object with token counts."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return ["response.usage is missing"]
    errors: list[str] = []
    for field in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "input_tokens_details",
        "output_tokens_details",
    ):
        if field not in usage:
            errors.append(f"response.usage.{field} is missing")
    if "input_tokens_details" in usage:
        details = usage["input_tokens_details"]
        if not isinstance(details, dict):
            errors.append("response.usage.input_tokens_details is not an object")
        elif "cached_tokens" not in details:
            errors.append(
                "response.usage.input_tokens_details.cached_tokens is missing"
            )
    if "output_tokens_details" in usage:
        details = usage["output_tokens_details"]
        if not isinstance(details, dict):
            errors.append("response.usage.output_tokens_details is not an object")
        elif "reasoning_tokens" not in details:
            errors.append(
                "response.usage.output_tokens_details.reasoning_tokens is missing"
            )
    return errors


def has_output_type(expected_type: str) -> Validator:
    """Factory: validate response has an output item of the given type."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        output = response.get("output", [])
        if not isinstance(output, list):
            return ["response.output is not an array"]
        types = [item.get("type") for item in output if isinstance(item, dict)]
        if expected_type not in types:
            return [f"no output item with type='{expected_type}' (found: {types})"]
        return []

    _check.__qualname__ = f"has_output_type({expected_type!r})"
    return _check


# -- Streaming validators --


def streaming_has_events(response: Any, ctx: ValidatorContext) -> list[str]:
    """SSE events must have been received."""
    if not ctx.sse_events:
        return ["no SSE events received"]
    return []


def streaming_has_terminal(response: Any, ctx: ValidatorContext) -> list[str]:
    """Stream must end with a terminal event (completed/failed/incomplete)."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    terminal = {"response.completed", "response.failed", "response.incomplete"}
    typed = [e["type"] for e in ctx.sse_events if isinstance(e.get("type"), str)]
    if not any(t in terminal for t in typed):
        return ["stream has no terminal event (completed/failed/incomplete)"]
    return []


def streaming_lifecycle_order(response: Any, ctx: ValidatorContext) -> list[str]:
    """SSE events must follow the expected lifecycle ordering."""
    if not ctx.sse_events:
        return ["no SSE events to check"]

    errors: list[str] = []
    seen_types: list[str] = [
        e["type"] for e in ctx.sse_events if e.get("type") != "[DONE]"
    ]

    if not seen_types:
        return ["no typed events found"]

    # First event should be response.created or response.queued
    expected_first = {"response.created", "response.queued"}
    if seen_types[0] not in expected_first:
        errors.append(f"first event should be {expected_first}, got '{seen_types[0]}'")

    # Check response.created comes before response.in_progress
    created_idx = _first_idx(seen_types, "response.created")
    in_progress_idx = _first_idx(seen_types, "response.in_progress")
    if created_idx is not None and in_progress_idx is not None:
        if created_idx > in_progress_idx:
            errors.append("response.created must come before response.in_progress")

    # Terminal event should be one of the terminal types
    terminal = {"response.completed", "response.failed", "response.incomplete"}
    non_done = [t for t in seen_types if t != "[DONE]"]
    if non_done and non_done[-1] not in terminal:
        errors.append(f"last typed event should be terminal, got '{non_done[-1]}'")

    return errors


def streaming_has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """Final streaming response must include usage data."""
    if not isinstance(response, dict):
        return ["no final response extracted from stream"]
    return has_usage(response, ctx)


def streaming_sequence_numbers(response: Any, ctx: ValidatorContext) -> list[str]:
    """sequence_number must be monotonically increasing across events."""
    if not ctx.sse_events:
        return ["no SSE events to check"]

    errors: list[str] = []
    prev_seq: int | None = None

    for i, event in enumerate(ctx.sse_events):
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        seq = data.get("sequence_number")
        if seq is None:
            continue
        if not isinstance(seq, int):
            errors.append(f"event {i}: sequence_number is not an integer")
            continue
        if prev_seq is not None and seq <= prev_seq:
            errors.append(f"event {i}: sequence_number {seq} <= previous {prev_seq}")
        prev_seq = seq

    return errors


def responses_streaming_output_text(response: Any, ctx: ValidatorContext) -> list[str]:
    """Stream must carry non-empty ``response.output_text.delta`` text.

    Assumes the test elicited text: a valid stream that carries only tool
    calls has no text deltas and must not use this validator.
    """
    if not ctx.sse_events:
        return ["no SSE events to check"]
    errors: list[str] = []
    parts: list[str] = []
    for position, event in enumerate(ctx.sse_events):
        if event.get("type") != "response.output_text.delta":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            errors.append(f"event {position}: output_text.delta has no data object")
            continue
        delta = data.get("delta")
        if not isinstance(delta, str):
            errors.append(f"event {position}: output_text.delta.delta is not a string")
            continue
        parts.append(delta)
    if errors:
        return errors
    if not parts:
        return ["no response.output_text.delta events found"]
    if not "".join(parts).strip():
        return ["response.output_text.delta events carried no text"]
    return []


# -- Open Responses phase / compact validators --


def has_output_phase(expected_phase: str) -> Validator:
    """Factory: validate at least one assistant output has the given phase."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        for item in response.get("output", []):
            if not isinstance(item, dict):
                continue
            if item.get("role") == "assistant" and item.get("phase") == expected_phase:
                return []
        return [f"no assistant output with phase='{expected_phase}'"]

    _check.__qualname__ = f"has_output_phase({expected_phase!r})"
    return _check


def responses_error_body(response: Any, ctx: ValidatorContext) -> list[str]:
    """A 4xx body must carry a usable error payload.

    The Open Responses spec defines ``ErrorPayload`` (flat ``type``/``code``/
    ``message``/``param``) for streaming error events but declares no
    non-streaming error response, so both that shape and the common
    ``{"error": {...}}`` envelope are accepted. The message must be a
    non-empty string in either case.
    """
    if not isinstance(response, dict):
        return ["error response is not a JSON object"]
    if "error" in response:
        error = response["error"]
        if not isinstance(error, dict):
            return ["error is not an object"]
        message = error.get("message")
        if not isinstance(message, str) or not message:
            return ["error.message is missing or empty"]
        return []
    missing = [
        field for field in ("type", "code", "message", "param") if field not in response
    ]
    if missing:
        return [f"error payload is missing fields: {', '.join(missing)}"]
    message = response.get("message")
    if not isinstance(message, str) or not message:
        return ["error payload message is missing or empty"]
    return []


def compact_object(response: Any, ctx: ValidatorContext) -> list[str]:
    """Compacted response must carry the CompactResource fields."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    errors: list[str] = []
    obj = response.get("object")
    if obj != "response.compaction":
        errors.append(f"expected object 'response.compaction', got '{obj}'")
    for field in ("id", "output", "created_at", "usage"):
        if field not in response:
            errors.append(f"response.{field} is missing")
    if "usage" in response:
        errors.extend(has_usage(response, ctx))
    return errors


# -- Chat Completions validators --


def chat_has_choices(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a non-empty choices array."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        return ["response.choices is missing or empty"]
    return []


# Non-content fields that represent a real Chat Completions payload.
_CHAT_PAYLOAD_FIELDS = (
    "tool_calls",
    "function_call",
    "refusal",
    "reasoning_content",
    "reasoning",
    "audio",
)


def chat_has_message(response: Any, ctx: ValidatorContext) -> list[str]:
    """First choice must have an assistant role and a payload field."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    choices = response.get("choices", [])
    if not choices:
        return ["response.choices is empty"]
    msg = choices[0].get("message", {})
    errors: list[str] = []
    if msg.get("role") != "assistant":
        errors.append(
            f"choices[0].message.role: expected 'assistant', got '{msg.get('role')}'"
        )
    if msg.get("content") is None and not any(
        msg.get(field) for field in _CHAT_PAYLOAD_FIELDS
    ):
        errors.append(
            "choices[0].message has none of: content, "
            + ", ".join(_CHAT_PAYLOAD_FIELDS)
        )
    return errors


def chat_finish_reason(expected: str) -> Validator:
    """Factory: validate choices[0].finish_reason matches expected value."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        choices = response.get("choices", [])
        if not choices:
            return ["response.choices is empty"]
        reason = choices[0].get("finish_reason")
        if reason != expected:
            return [f"finish_reason: expected '{expected}', got '{reason}'"]
        return []

    _check.__qualname__ = f"chat_finish_reason({expected!r})"
    return _check


def chat_has_tool_calls(response: Any, ctx: ValidatorContext) -> list[str]:
    """First choice message must have well-formed function or custom tool calls."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    choices = response.get("choices", [])
    if not choices:
        return ["response.choices is empty"]
    tc = choices[0].get("message", {}).get("tool_calls")
    if not isinstance(tc, list) or len(tc) == 0:
        return ["choices[0].message.tool_calls is missing or empty"]
    errors: list[str] = []
    for index, call in enumerate(tc):
        prefix = f"choices[0].message.tool_calls[{index}]"
        if not isinstance(call, dict):
            errors.append(f"{prefix} is not an object")
            continue
        if not isinstance(call.get("id"), str) or not call.get("id"):
            errors.append(f"{prefix}.id is missing or not a string")
        call_type = call.get("type")
        if call_type == "function":
            function = call.get("function")
            if not isinstance(function, dict):
                errors.append(f"{prefix}.function is missing or not an object")
                continue
            if not isinstance(function.get("name"), str) or not function.get("name"):
                errors.append(f"{prefix}.function.name is missing or not a string")
            if not isinstance(function.get("arguments"), str):
                errors.append(f"{prefix}.function.arguments is missing or not a string")
        elif call_type == "custom":
            custom = call.get("custom")
            if not isinstance(custom, dict):
                errors.append(f"{prefix}.custom is missing or not an object")
                continue
            if not isinstance(custom.get("name"), str) or not custom.get("name"):
                errors.append(f"{prefix}.custom.name is missing or not a string")
            if not isinstance(custom.get("input"), str):
                errors.append(f"{prefix}.custom.input is missing or not a string")
        else:
            errors.append(
                f"{prefix}.type: expected 'function' or 'custom', got '{call_type}'"
            )
    return errors


def chat_has_tool_call_of_type(expected: str) -> Validator:
    """Factory: tool calls must be well-formed and include *expected* type."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        errors = chat_has_tool_calls(response, ctx)
        calls: list[Any] = []
        if isinstance(response, dict):
            choices = response.get("choices") or []
            if choices and isinstance(choices[0], dict):
                message = choices[0].get("message") or {}
                calls = message.get("tool_calls") or []
        if not any(
            isinstance(call, dict) and call.get("type") == expected for call in calls
        ):
            errors.append(f"no tool call of type '{expected}'")
        return errors

    _check.__qualname__ = "chat_has_tool_call_of_type"
    return _check


def _chat_message_text(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    choices = response.get("choices", [])
    if not choices or not isinstance(choices[0], dict):
        return None
    content = choices[0].get("message", {}).get("content")
    return content if isinstance(content, str) else None


def chat_message_is_json(response: Any, ctx: ValidatorContext) -> list[str]:
    """First choice message content must parse as JSON."""
    text = _chat_message_text(response)
    if text is None:
        return ["choices[0].message.content is missing or not a string"]
    try:
        json.loads(text)
    except ValueError as exc:
        return [f"message content is not valid JSON: {exc}"]
    return []


def chat_message_matches_json_schema(schema: dict[str, Any]) -> Validator:
    """Factory: parsed message content must validate against *schema*."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        text = _chat_message_text(response)
        if text is None:
            return ["choices[0].message.content is missing or not a string"]
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            return [f"message content is not valid JSON: {exc}"]
        try:
            jsonschema.validate(parsed, schema)
        except jsonschema.ValidationError as exc:
            return [
                f"message content does not match the requested schema: {exc.message}"
            ]
        return []

    _check.__qualname__ = "chat_message_matches_json_schema"
    return _check


def chat_has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have usage with prompt_tokens/completion_tokens/total_tokens."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return ["response.usage is missing"]
    errors: list[str] = []
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if field not in usage:
            errors.append(f"response.usage.{field} is missing")
    return errors


def chat_has_audio(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response message must carry an audio payload when audio is requested."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    choices = response.get("choices", [])
    if not choices or not isinstance(choices[0], dict):
        return ["response.choices is empty"]
    message = choices[0].get("message", {})
    audio = message.get("audio") if isinstance(message, dict) else None
    if not isinstance(audio, dict):
        return ["choices[0].message.audio is missing or not an object"]
    errors: list[str] = []
    for field in ("id", "data", "transcript"):
        if not isinstance(audio.get(field), str) or not audio.get(field):
            errors.append(f"choices[0].message.audio.{field} is missing or empty")
    if not isinstance(audio.get("expires_at"), int):
        errors.append("choices[0].message.audio.expires_at is not an integer")
    return errors


_CHAT_TOKEN_DETAIL_FIELDS: dict[str, tuple[str, ...]] = {
    "completion_tokens_details": (
        "accepted_prediction_tokens",
        "audio_tokens",
        "reasoning_tokens",
        "rejected_prediction_tokens",
        "text_tokens",
    ),
    "prompt_tokens_details": (
        "audio_tokens",
        "cache_write_tokens",
        "cached_tokens",
        "image_tokens",
        "text_tokens",
    ),
}


def _chat_token_details(usage: dict[str, Any], key: str) -> list[str]:
    if key not in usage:
        return [f"[warning] usage.{key} is missing"]
    details = usage[key]
    if not isinstance(details, dict):
        return [f"[warning] usage.{key} is not an object"]
    return [
        f"[warning] usage.{key}.{field} is not an integer"
        for field in _CHAT_TOKEN_DETAIL_FIELDS[key]
        if field in details and not isinstance(details[field], int)
    ]


def chat_has_completion_token_details(
    response: Any, ctx: ValidatorContext
) -> list[str]:
    """Warn when usage.completion_tokens_details sub-fields are malformed."""
    if not isinstance(response, dict):
        return []
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return []
    return _chat_token_details(usage, "completion_tokens_details")


def chat_has_prompt_token_details(response: Any, ctx: ValidatorContext) -> list[str]:
    """Warn when usage.prompt_tokens_details sub-fields are malformed."""
    if not isinstance(response, dict):
        return []
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return []
    return _chat_token_details(usage, "prompt_tokens_details")


def chat_streaming_has_delta(response: Any, ctx: ValidatorContext) -> list[str]:
    """At least one streaming chunk must carry content, tools, or reasoning."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    progress_fields = ("content", *_CHAT_PAYLOAD_FIELDS)
    for event in ctx.sse_events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        choices = data.get("choices", [])
        for c in choices:
            delta = c.get("delta", {})
            if any(delta.get(field) for field in progress_fields):
                return []
    return [
        "no streaming chunk contained any of: "
        + ", ".join(f"delta.{field}" for field in progress_fields)
    ]


def chat_streaming_has_finish(response: Any, ctx: ValidatorContext) -> list[str]:
    """At least one chunk must have a non-null finish_reason."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    for event in ctx.sse_events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        for c in data.get("choices", []):
            if c.get("finish_reason") is not None:
                return []
    return ["no streaming chunk had a finish_reason"]


def chat_streaming_has_done(response: Any, ctx: ValidatorContext) -> list[str]:
    """Chat Completions stream must end with [DONE] sentinel."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    if ctx.sse_events[-1].get("type") != "[DONE]":
        return ["stream did not end with [DONE] terminator"]
    return []


def chat_streaming_has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """Streaming must include a chunk with usage data."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    for event in ctx.sse_events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        usage = data.get("usage")
        if isinstance(usage, dict) and "prompt_tokens" in usage:
            return []
    return ["no streaming chunk contained usage data"]


# -- Chat Completions advisory (warning) validators --


def chat_has_refusal_field(response: Any, ctx: ValidatorContext) -> list[str]:
    """Warn if message lacks the refusal field (OpenAI spec: required, nullable)."""
    if not isinstance(response, dict):
        return []
    choices = response.get("choices", [])
    if not choices:
        return []
    msg = choices[0].get("message", {})
    if "refusal" not in msg:
        return [
            "[warning] choices[0].message missing 'refusal' field (spec: required, nullable)"
        ]
    return []


def chat_has_annotations_field(response: Any, ctx: ValidatorContext) -> list[str]:
    """Warn if message lacks the annotations field (OpenAI always returns [])."""
    if not isinstance(response, dict):
        return []
    choices = response.get("choices", [])
    if not choices:
        return []
    msg = choices[0].get("message", {})
    if "annotations" not in msg:
        return ["[warning] choices[0].message missing 'annotations' field"]
    return []


def chat_has_logprobs_field(response: Any, ctx: ValidatorContext) -> list[str]:
    """Warn if choice lacks the logprobs field (spec: required, nullable)."""
    if not isinstance(response, dict):
        return []
    choices = response.get("choices", [])
    if not choices:
        return []
    if "logprobs" not in choices[0]:
        return [
            "[warning] choices[0] missing 'logprobs' field (spec: required, nullable)"
        ]
    return []


def chat_id_has_prefix(prefix: str) -> Validator:
    """Factory: warn if response id does not start with expected prefix."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return []
        rid = response.get("id", "")
        if rid and not rid.startswith(prefix):
            return [f"[warning] response.id '{rid[:20]}...' missing '{prefix}' prefix"]
        return []

    _check.__qualname__ = f"chat_id_has_prefix({prefix!r})"
    return _check


def chat_streaming_all_have_finish_reason(
    response: Any, ctx: ValidatorContext
) -> list[str]:
    """Warn if any streaming chunk choice lacks the finish_reason key."""
    if not ctx.sse_events:
        return []
    missing = 0
    total = 0
    for event in ctx.sse_events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        for choice in data.get("choices", []):
            total += 1
            if "finish_reason" not in choice:
                missing += 1
    if missing:
        return [
            f"[warning] {missing}/{total} streaming chunk choices missing "
            f"'finish_reason' key (spec: required, nullable)"
        ]
    return []


# -- Anthropic Messages validators --


def anth_has_content(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a non-empty content array."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    content = response.get("content")
    if not isinstance(content, list) or len(content) == 0:
        return ["response.content is missing or empty"]
    return []


def anth_role_assistant(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response role must be 'assistant'."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    if response.get("role") != "assistant":
        return [f"expected role='assistant', got '{response.get('role')}'"]
    return []


def anth_stop_reason(expected: str) -> Validator:
    """Factory: validate stop_reason matches expected value."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        reason = response.get("stop_reason")
        if reason != expected:
            return [f"stop_reason: expected '{expected}', got '{reason}'"]
        return []

    _check.__qualname__ = f"anth_stop_reason({expected!r})"
    return _check


def anth_has_tool_use(response: Any, ctx: ValidatorContext) -> list[str]:
    """Content must include a tool_use block."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    for block in response.get("content", []):
        if isinstance(block, dict) and block.get("type") == "tool_use":
            return []
    return ["no content block with type='tool_use'"]


def anth_has_content_block_of_type(*expected: str) -> Validator:
    """Factory: content must include a block of every expected type."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        content = response.get("content")
        if not isinstance(content, list):
            return ["response.content is missing or not an array"]
        types = {block.get("type") for block in content if isinstance(block, dict)}
        missing = [block_type for block_type in expected if block_type not in types]
        if missing:
            return [f"content is missing block types: {', '.join(missing)}"]
        return []

    _check.__qualname__ = f"anth_has_content_block_of_type({', '.join(expected)})"
    return _check


def _anth_output_text(response: Any) -> str | None:
    """Concatenate text blocks from the response, or None when there are none."""
    if not isinstance(response, dict):
        return None
    content = response.get("content")
    if not isinstance(content, list):
        return None
    texts = [
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    return "".join(texts) if texts else None


def anth_output_is_json(response: Any, ctx: ValidatorContext) -> list[str]:
    """Concatenated text blocks must parse as JSON."""
    text = _anth_output_text(response)
    if text is None:
        return ["no text block to parse as JSON"]
    try:
        json.loads(text)
    except ValueError as exc:
        return [f"text blocks are not valid JSON: {exc}"]
    return []


def anth_output_matches_json_schema(schema: dict[str, Any]) -> Validator:
    """Factory: parsed text blocks must validate against *schema*."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        text = _anth_output_text(response)
        if text is None:
            return ["no text block to parse as JSON"]
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            return [f"text blocks are not valid JSON: {exc}"]
        try:
            jsonschema.validate(parsed, schema)
        except jsonschema.ValidationError as exc:
            return [f"text blocks do not match the requested schema: {exc.message}"]
        return []

    _check.__qualname__ = "anth_output_matches_json_schema"
    _check.__schema__ = schema
    return _check


_CODE_EXECUTION_FAMILIES = {
    "code_execution": "code_execution_tool_result",
    "bash_code_execution": "bash_code_execution_tool_result",
    "text_editor_code_execution": "text_editor_code_execution_tool_result",
}
_CODE_EXECUTION_RESULT_BLOCKS = tuple(_CODE_EXECUTION_FAMILIES.values()) + tuple(
    block_type + "_error" for block_type in _CODE_EXECUTION_FAMILIES.values()
)


def anth_has_code_execution(response: Any, ctx: ValidatorContext) -> list[str]:
    """A server tool run must pair with a result that exited successfully.

    ``server_tool_use`` ids must match the ``tool_use_id`` they answer, and
    the sandbox run counts as proof only when ``return_code`` is 0. Multiple
    runs pass when any one succeeded, matching the Google code-execution
    validator's retry semantics.
    """
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    content = response.get("content")
    if not isinstance(content, list):
        return ["response.content is missing or not an array"]
    server_by_id: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if (
            block.get("type") == "server_tool_use"
            and block.get("name") in _CODE_EXECUTION_FAMILIES
            and isinstance(block.get("id"), str)
        ):
            server_by_id[block["id"]] = block["name"]
        elif block.get("type") in _CODE_EXECUTION_RESULT_BLOCKS:
            results.append(block)
    if not server_by_id:
        return ["no server_tool_use block for code_execution"]
    if not results:
        return ["no code_execution_tool_result block"]
    paired = [result for result in results if result.get("tool_use_id") in server_by_id]
    if not paired:
        return ["code_execution_tool_result does not match any server_tool_use id"]
    failures: list[str] = []
    for result in paired:
        tool_id = result.get("tool_use_id")
        expected = _CODE_EXECUTION_FAMILIES[server_by_id[tool_id]]
        result_type = result.get("type")
        if result_type not in (expected, expected + "_error"):
            failures.append(
                f"result type {result_type} does not match tool {server_by_id[tool_id]}"
            )
            continue
        inner = result.get("content")
        if result_type.endswith("_error"):
            code = inner.get("error_code") if isinstance(inner, dict) else None
            failures.append(f"code execution failed: {code or result_type}")
            continue
        if not isinstance(inner, dict):
            continue
        inner_type = inner.get("type")
        if (
            inner_type in ("code_execution_result", "bash_code_execution_result")
            and inner.get("return_code") == 0
        ):
            return []
        if (
            isinstance(inner_type, str)
            and inner_type.startswith("text_editor_code_execution_")
            and not inner_type.endswith("_error")
        ):
            return []
        if "error_code" in inner:
            failures.append(f"code execution failed: {inner['error_code']}")
        elif "return_code" in inner:
            failures.append(
                f"code execution did not succeed: return_code={inner['return_code']}"
            )
    return failures or ["code execution did not report a result"]


def anth_output_contains(expected: str) -> Validator:
    """Factory: concatenated text blocks must contain *expected*."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not expected:
            return ["expected text is empty"]
        text = _anth_output_text(response)
        if text is None:
            return ["no text block to inspect"]
        if expected not in text:
            return [f"text blocks do not contain {expected!r}"]
        return []

    _check.__qualname__ = f"anth_output_contains({expected!r})"
    return _check


def anth_cache_used(response: Any, ctx: ValidatorContext) -> list[str]:
    """A cached prompt must report cache creation or cache reads."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return ["response.usage is missing or not an object"]

    def _positive(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    created = usage.get("cache_creation_input_tokens")
    read = usage.get("cache_read_input_tokens")
    if _positive(created) or _positive(read):
        return []
    return [
        "cache was not used: "
        f"cache_creation_input_tokens={created}, "
        f"cache_read_input_tokens={read}"
    ]


def anth_max_tokens_honoured(limit: int) -> Validator:
    """Factory: usage.output_tokens must not exceed the requested max_tokens."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return ["response.usage is missing or not an object"]
        tokens = usage.get("output_tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool):
            return ["response.usage.output_tokens is missing or not an integer"]
        if tokens > limit:
            return [f"usage.output_tokens {tokens} exceeds max_tokens={limit}"]
        return []

    _check.__qualname__ = f"anth_max_tokens_honoured({limit})"
    return _check


def anth_stop_sequence(expected: str) -> Validator:
    """Factory: validate the response's matched stop_sequence.

    The matched sequence must also be absent from the returned text; if it
    appears, generation was not actually stopped by it.
    """

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        value = response.get("stop_sequence")
        if value != expected:
            return [f"stop_sequence: expected {expected!r}, got {value!r}"]
        text = _anth_output_text(response) or ""
        if expected in text:
            return [f"output text still contains stop sequence {expected!r}"]
        return []

    _check.__qualname__ = f"anth_stop_sequence({expected!r})"
    return _check


def anth_has_input_tokens(response: Any, ctx: ValidatorContext) -> list[str]:
    """Token-count responses must report a positive input_tokens count.

    The spec sets no minimum, so rejecting zero is deliberate: the prompt is
    non-empty, so a zero count is a provider bug worth reporting.
    """
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    tokens = response.get("input_tokens")
    if not isinstance(tokens, int) or isinstance(tokens, bool):
        return ["response.input_tokens is missing or not an integer"]
    if tokens <= 0:
        return [f"response.input_tokens is not positive: {tokens}"]
    return []


def anth_has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have usage with input_tokens/output_tokens."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return ["response.usage is missing"]
    errors: list[str] = []
    for field in ("input_tokens", "output_tokens"):
        if field not in usage:
            errors.append(f"response.usage.{field} is missing")
    return errors


def anth_type_message(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response type must be 'message'."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    if response.get("type") != "message":
        return [f"expected type='message', got '{response.get('type')}'"]
    return []


def anth_streaming_lifecycle(response: Any, ctx: ValidatorContext) -> list[str]:
    """Anthropic stream must follow message_start → content → message_delta → message_stop."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    types = [e["type"] for e in ctx.sse_events if isinstance(e.get("type"), str)]
    errors: list[str] = []
    if not types:
        return ["no typed events found"]
    if types[0] not in ("message_start", "ping"):
        errors.append(f"first event should be message_start or ping, got '{types[0]}'")
    non_ping = [t for t in types if t != "ping"]
    if non_ping and non_ping[-1] != "message_stop":
        errors.append(f"last event should be message_stop, got '{non_ping[-1]}'")
    if "message_delta" not in types:
        errors.append("missing message_delta event (carries stop_reason/usage)")
    return errors


def anth_streaming_content_block_bracketing(
    response: Any, ctx: ValidatorContext
) -> list[str]:
    """Every content_block_start must have a matching content_block_stop."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    open_blocks: dict[int, int] = {}
    errors: list[str] = []
    for position, event in enumerate(ctx.sse_events):
        event_type = event.get("type")
        if event_type not in ("content_block_start", "content_block_stop"):
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            errors.append(f"event {position}: {event_type} has no data object")
            continue
        index = data.get("index")
        if not isinstance(index, int):
            errors.append(f"event {position}: {event_type} has no integer index")
            continue
        if event_type == "content_block_start":
            if index in open_blocks:
                errors.append(
                    f"event {position}: content_block_start for index {index} "
                    "while that block is already open"
                )
            open_blocks[index] = position
        elif event_type == "content_block_stop" and index not in open_blocks:
            errors.append(
                f"event {position}: content_block_stop for index {index} "
                "without a preceding start"
            )
        elif event_type == "content_block_stop":
            open_blocks.pop(index)
    for index, position in open_blocks.items():
        errors.append(
            f"content block {index} opened at event {position} has no "
            "content_block_stop"
        )
    return errors


def anth_streaming_has_tool_input_delta(
    input_schema: dict[str, Any] | None = None,
) -> Validator:
    """Streaming tool calls must emit input_json_delta events forming valid JSON.

    When *input_schema* is given, the assembled arguments must also validate
    against the tool's declared input schema, not merely parse.
    """

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not ctx.sse_events:
            return ["no SSE events to check"]
        tool_indexes: set[int] = set()
        fragments: dict[int, list[str]] = {}
        errors: list[str] = []
        for event in ctx.sse_events:
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            index = data.get("index")
            if data.get("type") == "content_block_start":
                block = data.get("content_block")
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    if isinstance(index, int) and not isinstance(index, bool):
                        tool_indexes.add(index)
                    else:
                        errors.append(
                            "tool_use content_block_start has no integer index"
                        )
            elif data.get("type") == "content_block_delta":
                delta = data.get("delta")
                if isinstance(delta, dict) and delta.get("type") == "input_json_delta":
                    if not isinstance(index, int) or isinstance(index, bool):
                        errors.append("input_json_delta event has no integer index")
                        continue
                    fragment = delta.get("partial_json")
                    if isinstance(fragment, str):
                        fragments.setdefault(index, []).append(fragment)
        if not tool_indexes:
            return errors or ["no tool_use content_block_start event"]
        for index in sorted(tool_indexes):
            if index not in fragments:
                errors.append(
                    f"tool_use block at index {index} has no input_json_delta events"
                )
                continue
            text = "".join(fragments[index])
            if not text.strip():
                errors.append(
                    f"input_json_delta events at index {index} carried no partial JSON"
                )
                continue
            try:
                parsed = json.loads(text)
            except ValueError as exc:
                errors.append(
                    f"tool input deltas at index {index} do not form valid JSON: {exc}"
                )
                continue
            if input_schema is not None:
                try:
                    jsonschema.validate(parsed, input_schema)
                except jsonschema.ValidationError as exc:
                    errors.append(
                        f"tool input at index {index} does not match the tool "
                        f"schema: {exc.message}"
                    )
        return errors

    _check.__qualname__ = "anth_streaming_has_tool_input_delta"
    _check.__schema__ = input_schema
    return _check


def anth_streaming_has_text_delta(response: Any, ctx: ValidatorContext) -> list[str]:
    """At least one content_block_delta with text must be present."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    for event in ctx.sse_events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        delta = data.get("delta", {})
        if delta.get("type") == "text_delta" and delta.get("text"):
            return []
    return ["no content_block_delta with text_delta found"]


def anth_streaming_has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """message_delta event must carry usage data."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    for event in ctx.sse_events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if event.get("type") == "message_delta":
            usage = data.get("usage")
            if isinstance(usage, dict) and "output_tokens" in usage:
                return []
    return ["no message_delta event with usage data"]


# -- Google GenAI validators --


def _google_candidates(response: Any) -> list[dict[str, Any]]:
    """Return the candidate objects from a response, ignoring malformed entries."""
    if not isinstance(response, dict):
        return []
    cands = response.get("candidates")
    if not isinstance(cands, list):
        return []
    return [cand for cand in cands if isinstance(cand, dict)]


def google_has_candidates(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a non-empty candidates array."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    cands = response.get("candidates")
    if not isinstance(cands, list) or len(cands) == 0:
        return ["response.candidates is missing or empty"]
    if not isinstance(cands[0], dict):
        return ["response.candidates[0] is not an object"]
    return []


def google_has_content_parts(response: Any, ctx: ValidatorContext) -> list[str]:
    """First candidate must have content with non-empty parts."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    cands = _google_candidates(response)
    if not cands:
        return ["response.candidates is empty"]
    content = cands[0].get("content")
    if not isinstance(content, dict):
        return ["candidates[0].content is missing or not an object"]
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        return ["candidates[0].content.parts is missing or empty"]
    return []


def _google_output_text(response: Any) -> str | None:
    """Concatenate text parts from the first candidate that has any, or None."""
    if not isinstance(response, dict):
        return None
    texts: list[str] = []
    for cand in _google_candidates(response):
        content = cand.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if (
                isinstance(part, dict)
                and part.get("thought") is not True
                and isinstance(part.get("text"), str)
            ):
                texts.append(part["text"])
        if texts:
            return "".join(texts)
    return None


_GOOGLE_GROUNDING_FIELDS = (
    "groundingChunks",
    "grounding_chunks",
    "webSearchQueries",
    "web_search_queries",
    "groundingSupports",
    "grounding_supports",
    "searchEntryPoint",
    "search_entry_point",
    "retrievalMetadata",
    "retrieval_metadata",
    "imageSearchQueries",
    "image_search_queries",
)


def google_has_grounding_metadata(response: Any, ctx: ValidatorContext) -> list[str]:
    """A candidate must carry groundingMetadata with at least one grounding field.

    ``googleMapsWidgetContextToken`` alone is not counted: it renders a maps
    widget and is not evidence that a search returned results.
    """
    for cand in _google_candidates(response):
        grounding = cand.get("groundingMetadata") or cand.get("grounding_metadata")
        if isinstance(grounding, dict) and any(
            grounding.get(field) for field in _GOOGLE_GROUNDING_FIELDS
        ):
            return []
    return ["groundingMetadata is missing or has no grounding fields"]


def google_has_code_execution(response: Any, ctx: ValidatorContext) -> list[str]:
    """A candidate must pair executableCode with a successful codeExecutionResult."""
    saw_code = False
    outcomes: list[Any] = []
    for cand in _google_candidates(response):
        content = cand.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("executableCode") or part.get("executable_code"):
                saw_code = True
            result = part.get("codeExecutionResult") or part.get(
                "code_execution_result"
            )
            if isinstance(result, dict):
                outcomes.append(result.get("outcome"))
    if not saw_code:
        return ["no part carried executableCode"]
    if not outcomes:
        return ["executableCode carried but no codeExecutionResult"]
    # A model may retry after a failed execution; any successful run counts.
    if any(outcome in (None, "OUTCOME_OK") for outcome in outcomes):
        return []
    return [f"code execution did not succeed: {outcomes[-1]}"]


def google_output_is_json(response: Any, ctx: ValidatorContext) -> list[str]:
    """Concatenated candidate text must parse as JSON."""
    text = _google_output_text(response)
    if text is None:
        return ["no text part to parse as JSON"]
    try:
        json.loads(text)
    except ValueError as exc:
        return [f"candidate text is not valid JSON: {exc}"]
    return []


def google_output_matches_json_schema(schema: dict[str, Any]) -> Validator:
    """Factory: parsed candidate text must validate against *schema*."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        text = _google_output_text(response)
        if text is None:
            return ["no text part to parse as JSON"]
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            return [f"candidate text is not valid JSON: {exc}"]
        try:
            jsonschema.validate(parsed, schema)
        except jsonschema.ValidationError as exc:
            return [
                f"candidate text does not match the requested schema: {exc.message}"
            ]
        return []

    _check.__qualname__ = "google_output_matches_json_schema"
    _check.__schema__ = schema
    return _check


def google_finish_reason(expected: str) -> Validator:
    """Factory: validate candidates[0].finishReason matches expected."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        cands = _google_candidates(response)
        if not cands:
            return ["response.candidates is empty"]
        reason = cands[0].get("finishReason")
        if reason != expected:
            return [f"finishReason: expected '{expected}', got '{reason}'"]
        return []

    _check.__qualname__ = f"google_finish_reason({expected!r})"
    return _check


def google_has_function_call(response: Any, ctx: ValidatorContext) -> list[str]:
    """First candidate must have a functionCall part."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    cands = _google_candidates(response)
    if not cands:
        return ["response.candidates is empty"]
    content = cands[0].get("content")
    if not isinstance(content, dict):
        return ["candidates[0].content is missing or not an object"]
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ["candidates[0].content.parts is not an array"]
    for p in parts:
        if isinstance(p, dict) and ("functionCall" in p or "function_call" in p):
            return []
    return ["no part with functionCall found"]


def google_has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have usageMetadata with token counts."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    usage = response.get("usageMetadata") or response.get("usage_metadata")
    if not isinstance(usage, dict):
        return ["response.usageMetadata is missing"]
    errors: list[str] = []
    for field in ("promptTokenCount", "candidatesTokenCount", "totalTokenCount"):
        snake = _camel_to_snake(field)
        if field not in usage and snake not in usage:
            errors.append(f"usageMetadata.{field} is missing")
    return errors


def google_streaming_has_text(response: Any, ctx: ValidatorContext) -> list[str]:
    """At least one streaming chunk must have a text part."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    for event in ctx.sse_events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        for cand in data.get("candidates", []):
            if not isinstance(cand, dict):
                continue
            content = cand.get("content")
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if isinstance(part, dict) and part.get("text"):
                    return []
    return ["no streaming chunk contained a text part"]


def google_streaming_has_finish(response: Any, ctx: ValidatorContext) -> list[str]:
    """At least one chunk must have a finishReason."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    for event in ctx.sse_events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        for cand in data.get("candidates", []):
            if isinstance(cand, dict) and cand.get("finishReason"):
                return []
    return ["no streaming chunk had a finishReason"]


def google_streaming_has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """At least one chunk must have usageMetadata."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    for event in ctx.sse_events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        usage = data.get("usageMetadata") or data.get("usage_metadata")
        if isinstance(usage, dict) and (
            "totalTokenCount" in usage or "total_token_count" in usage
        ):
            return []
    return ["no streaming chunk contained usageMetadata"]


def google_has_response_id(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a responseId / response_id field."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    if not (response.get("responseId") or response.get("response_id")):
        return ["response.responseId is missing"]
    return []


def google_has_model_version(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a modelVersion / model_version field."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    if not (response.get("modelVersion") or response.get("model_version")):
        return ["response.modelVersion is missing"]
    return []


def google_streaming_has_response_id(response: Any, ctx: ValidatorContext) -> list[str]:
    """At least one streaming chunk must have responseId / response_id."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    for event in ctx.sse_events:
        data = event.get("data")
        if isinstance(data, dict) and (
            data.get("responseId") or data.get("response_id")
        ):
            return []
    return ["no streaming chunk contained responseId"]


def google_streaming_has_model_version(
    response: Any, ctx: ValidatorContext
) -> list[str]:
    """At least one streaming chunk must have modelVersion / model_version."""
    if not ctx.sse_events:
        return ["no SSE events to check"]
    for event in ctx.sse_events:
        data = event.get("data")
        if isinstance(data, dict) and (
            data.get("modelVersion") or data.get("model_version")
        ):
            return []
    return ["no streaming chunk contained modelVersion"]


def google_error_format(response: Any, ctx: ValidatorContext) -> list[str]:
    """Error response must follow Google format: {error: {code, message, status}}."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    error = response.get("error")
    if not isinstance(error, dict):
        return ["response.error is missing or not an object"]
    errors: list[str] = []
    if "code" not in error:
        errors.append("error.code is missing")
    if "message" not in error:
        errors.append("error.message is missing")
    if "status" not in error:
        errors.append("error.status is missing")
    return errors


_GOOGLE_VALID_MODALITIES = {"TEXT", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT"}


def google_usage_valid_modalities(response: Any, ctx: ValidatorContext) -> list[str]:
    """ModalityTokenCount entries must use valid Google Modality enum values."""
    if not isinstance(response, dict):
        return []
    usage = response.get("usageMetadata") or response.get("usage_metadata")
    if not isinstance(usage, dict):
        return []
    errors: list[str] = []
    _DETAIL_FIELDS = (
        ("promptTokensDetails", "prompt_tokens_details"),
        ("candidatesTokensDetails", "candidates_tokens_details"),
    )
    for camel, snake in _DETAIL_FIELDS:
        details = usage.get(camel) or usage.get(snake, [])
        if not isinstance(details, list):
            continue
        field = camel
        for entry in details:
            if not isinstance(entry, dict):
                continue
            modality = entry.get("modality", "")
            if modality and modality not in _GOOGLE_VALID_MODALITIES:
                errors.append(
                    f"{field}[].modality: '{modality}' is not a valid "
                    f"Google Modality enum value"
                )
    return errors


def google_function_call_has_id(response: Any, ctx: ValidatorContext) -> list[str]:
    """Warn if functionCall parts lack an id field (Gemini 3.x provides it)."""
    if not isinstance(response, dict):
        return []
    cands = _google_candidates(response)
    if not cands:
        return []
    content = cands[0].get("content")
    if not isinstance(content, dict) or not isinstance(content.get("parts"), list):
        return []
    for p in content["parts"]:
        if not isinstance(p, dict):
            continue
        fc = p.get("functionCall") or p.get("function_call")
        if fc and "id" not in fc:
            return ["[warning] functionCall part has no id field"]
    return []


def _camel_to_snake(name: str) -> str:
    import re

    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def _first_idx(items: list[str], value: str) -> int | None:
    try:
        return items.index(value)
    except ValueError:
        return None


def anth_error_returns_error_type(response: Any, ctx: ValidatorContext) -> list[str]:
    """Warn if an intentionally invalid request succeeds instead of returning an error."""
    if not isinstance(response, dict):
        return []
    if response.get("type") == "message":
        return [
            "[warning] invalid request returned a successful response instead of "
            "an error (server may add default max_tokens)"
        ]
    return []


# ── Reasoning / Thinking summary validators ─────────────────────────────


def responses_has_reasoning_summary(response: Any, ctx: ValidatorContext) -> list[str]:
    """Responses API: response.reasoning.summary should be present when requested."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    reasoning = response.get("reasoning")
    if not isinstance(reasoning, dict):
        return ["response.reasoning is missing or not an object"]
    summary = reasoning.get("summary")
    if summary is None:
        return ["response.reasoning.summary is null (expected a value when requested)"]
    return []


def chat_has_reasoning_tokens(response: Any, ctx: ValidatorContext) -> list[str]:
    """Chat Completions: usage should report reasoning_tokens > 0 when reasoning is enabled."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    usage = response.get("usage", {})
    details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = details.get("reasoning_tokens", 0)
    if reasoning_tokens == 0:
        return [
            "[warning] usage.completion_tokens_details.reasoning_tokens is 0 "
            "(model may not support reasoning)"
        ]
    return []


def google_has_thought_parts(response: Any, ctx: ValidatorContext) -> list[str]:
    """Google GenAI: response should contain thought parts when thinking is enabled."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    cands = _google_candidates(response)
    if not cands:
        return ["response.candidates is empty"]
    content = cands[0].get("content")
    if not isinstance(content, dict) or not isinstance(content.get("parts"), list):
        return [
            "[warning] candidates[0].content.parts is missing or not an array "
            "(model may not emit thoughts at current thinking level)"
        ]
    parts = content["parts"]
    has_thought = any(isinstance(p, dict) and p.get("thought") is True for p in parts)
    if not has_thought:
        return [
            "[warning] no thought parts found in candidates[0].content.parts "
            "(model may not emit thoughts at current thinking level)"
        ]
    return []


def google_has_thoughts_token_count(
    response: Any,
    ctx: ValidatorContext,
) -> list[str]:
    """Google GenAI: usageMetadata should include thoughtsTokenCount."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    usage = response.get("usageMetadata") or response.get("usage_metadata")
    if not isinstance(usage, dict):
        return [
            "[warning] usageMetadata is missing or not an object "
            "(cannot check thoughtsTokenCount)"
        ]
    count = usage.get("thoughtsTokenCount") or usage.get("thoughts_token_count")
    if count is None or count == 0:
        return [
            "[warning] usageMetadata.thoughtsTokenCount is missing or 0 "
            "(model may not report thinking tokens)"
        ]
    return []


def anth_has_thinking_content(response: Any, ctx: ValidatorContext) -> list[str]:
    """Anthropic: response should contain a thinking content block."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    content = response.get("content", [])
    has_thinking = any(
        isinstance(c, dict) and c.get("type") == "thinking" for c in content
    )
    if not has_thinking:
        return [
            "[warning] no thinking content block found in response.content "
            "(model may not emit thinking at current config)"
        ]
    return []


# ── Google Interactions API validators ─────────────────────────────


def interactions_has_id(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a non-empty id field."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    rid = response.get("id")
    if not rid or not isinstance(rid, str):
        return ["response.id is missing or empty"]
    return []


def interactions_has_steps(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a non-empty steps array."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    steps = response.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        return ["response.steps is missing or empty"]
    return []


def interactions_has_model_output(response: Any, ctx: ValidatorContext) -> list[str]:
    """Steps must contain at least one model_output step with text content."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    steps = response.get("steps", [])
    for step in steps:
        if step.get("type") == "model_output":
            content = step.get("content")
            if not isinstance(content, list) or len(content) == 0:
                return ["model_output step has no content"]
            has_text = any(isinstance(c, dict) and c.get("text") for c in content)
            if not has_text:
                return ["model_output step has no text content"]
            return []
    return ["no model_output step found in response.steps"]


def interactions_status(expected: str) -> Validator:
    """Factory: validate response.status matches expected value."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        status = response.get("status")
        if status != expected:
            return [f"expected status='{expected}', got '{status}'"]
        return []

    _check.__qualname__ = f"interactions_status({expected!r})"
    return _check


def interactions_has_function_call(response: Any, ctx: ValidatorContext) -> list[str]:
    """Steps must contain at least one function_call step."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    steps = response.get("steps", [])
    for step in steps:
        if step.get("type") == "function_call":
            return []
    return ["no function_call step found in response.steps"]


def interactions_has_step_of_type(*expected: str) -> Validator:
    """Factory: steps must include every given step type."""

    def _check(response: Any, ctx: ValidatorContext) -> list[str]:
        if not isinstance(response, dict):
            return ["response is not a JSON object"]
        steps = response.get("steps")
        if not isinstance(steps, list):
            return ["response.steps is missing or not an array"]
        seen = [s.get("type") for s in steps if isinstance(s, dict)]
        missing = [step_type for step_type in expected if step_type not in seen]
        if missing:
            return [f"missing step types {missing} (saw: {seen})"]
        return []

    _check.__qualname__ = f"interactions_has_step_of_type{expected!r}"
    return _check


def interactions_function_call_has_id(
    response: Any, ctx: ValidatorContext
) -> list[str]:
    """Function call steps must have a non-empty id field."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    errors: list[str] = []
    for step in response.get("steps", []):
        if step.get("type") == "function_call":
            fc_id = step.get("id")
            if not fc_id or not isinstance(fc_id, str):
                errors.append("function_call step missing id field")
    return errors


def interactions_has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a usage object with token counts."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return ["response.usage is missing"]
    errors: list[str] = []
    for field in ("total_input_tokens", "total_output_tokens", "total_tokens"):
        if field not in usage:
            errors.append(f"response.usage.{field} is missing")
    return errors


def interactions_has_thought(response: Any, ctx: ValidatorContext) -> list[str]:
    """Steps must contain at least one thought step."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    for step in response.get("steps", []):
        if step.get("type") == "thought":
            return []
    return ["no thought step found in response.steps"]


def interactions_has_model_field(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response must have a model field."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    model = response.get("model")
    if not model or not isinstance(model, str):
        return ["response.model is missing or empty"]
    return []


def interactions_has_object_field(response: Any, ctx: ValidatorContext) -> list[str]:
    """Response.object must be 'interaction'."""
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    obj = response.get("object")
    if obj != "interaction":
        return [f"[warning] expected object='interaction', got '{obj}'"]
    return []


# ── Google Interactions streaming validators ───────────────────────


def _interactions_event_type(event: dict) -> str:
    data = event.get("data")
    if not isinstance(data, dict):
        return ""
    return data.get("event_type", event.get("type", ""))


def interactions_streaming_has_text(response: Any, ctx: ValidatorContext) -> list[str]:
    """Streaming events must contain step.delta events with text content."""
    if not ctx.sse_events:
        return ["no SSE events received"]
    for event in ctx.sse_events:
        if _interactions_event_type(event) != "step.delta":
            continue
        delta = event.get("data", {}).get("delta", {})
        if delta.get("type") == "text" and delta.get("text"):
            return []
    return ["no step.delta event with text content found"]


def interactions_streaming_has_lifecycle(
    response: Any, ctx: ValidatorContext
) -> list[str]:
    """Streaming must have interaction.created, step.start, step.stop events."""
    if not ctx.sse_events:
        return ["no SSE events received"]
    seen = {_interactions_event_type(e) for e in ctx.sse_events}
    errors: list[str] = []
    for required in ("interaction.created", "step.start", "step.stop"):
        if required not in seen:
            errors.append(f"missing streaming event: {required}")
    return errors


def interactions_streaming_has_completed(
    response: Any, ctx: ValidatorContext
) -> list[str]:
    """Streaming must end with an interaction.completed event."""
    if not ctx.sse_events:
        return ["no SSE events received"]
    for event in reversed(ctx.sse_events):
        if _interactions_event_type(event) == "interaction.completed":
            return []
    return ["no interaction.completed event found"]


def interactions_streaming_has_usage(response: Any, ctx: ValidatorContext) -> list[str]:
    """interaction.completed event must contain usage data."""
    if not ctx.sse_events:
        return ["no SSE events received"]
    for event in ctx.sse_events:
        if _interactions_event_type(event) != "interaction.completed":
            continue
        interaction = event.get("data", {}).get("interaction", {})
        usage = interaction.get("usage")
        if isinstance(usage, dict):
            return []
        return ["interaction.completed event missing usage data"]
    return ["no interaction.completed event found"]
