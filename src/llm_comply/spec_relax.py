"""Production relaxations for bundled specs.

Upstream specs sometimes mark fields required that live providers legitimately
omit, or declare a response field narrower than what the provider echoes back.
Applying a relaxation at load time keeps the bundled document byte-faithful to
upstream while validation follows observed provider behaviour. Each entry below
is justified by a live response from the provider's own API.
"""

from __future__ import annotations

from typing import Any

# Anthropic's SDK-generated spec marks these required, but the live Messages API
# and compatible gateways omit them: text blocks only carry ``citations`` when
# citations are enabled, tool-use blocks only carry ``caller`` in some releases,
# usage omits the details objects when the capability was not used, and
# ``speed`` / ``diagnostics`` are deployment-specific.
_ANTHROPIC_OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {
    "Usage": ("output_tokens_details", "server_tool_use", "speed"),
    "Message": ("diagnostics",),
    "ResponseTextBlock": ("citations",),
    "ResponseServerToolUseBlock": ("caller",),
    "ResponseToolUseBlock": ("caller",),
    "Container": ("skills",),
}

# OpenAI's Responses usage schema requires the cache-write breakdown, but
# compatible gateways report it only when prompt caching is in play; the
# cached-token count alone is the stable part.
_OPENAI_RESPONSES_OPTIONAL_FIELDS = ("cache_write_tokens",)

# OpenAI's chat response schema requires ``logprobs`` on each choice (the live
# API omits it) and declares the deprecated ``system_fingerprint`` as a
# non-nullable string (the live API returns null). Both are relaxed at load.
_CHAT_NULLABLE_STRINGS = ("system_fingerprint",)


def _drop_required(schema: Any, fields: tuple[str, ...]) -> None:
    if not isinstance(schema, dict):
        return
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [field for field in required if field not in fields]


def _nullable(schema: Any) -> None:
    if isinstance(schema, dict) and schema.get("type") == "string":
        schema.pop("type", None)
        schema["anyOf"] = [{"type": "string"}, {"type": "null"}]


def _relax_anthropic(schemas: dict[str, Any]) -> None:
    for name, fields in _ANTHROPIC_OPTIONAL_FIELDS.items():
        _drop_required(schemas.get(name), fields)


def _relax_chat(schemas: dict[str, Any]) -> None:
    response = schemas.get("CreateChatCompletionResponse")
    if isinstance(response, dict):
        choice = response.get("properties", {}).get("choices", {}).get("items")
        _drop_required(choice, ("logprobs",))
    for name in ("CreateChatCompletionResponse", "CreateChatCompletionStreamResponse"):
        schema = schemas.get(name)
        if isinstance(schema, dict):
            for field in _CHAT_NULLABLE_STRINGS:
                _nullable(schema.get("properties", {}).get(field))


def _relax_open_responses(schemas: dict[str, Any]) -> None:
    # The response-side schema declares ``schema`` as null-only, but OpenAI
    # echoes the JSON Schema object it accepted in the request.
    fmt = schemas.get("JsonSchemaResponseFormat")
    if isinstance(fmt, dict):
        fmt.get("properties", {})["schema"] = {
            "type": ["object", "null"],
            "description": "The JSON schema echoed back for the format.",
        }


def _relax_openai_responses(schemas: dict[str, Any]) -> None:
    usage = schemas.get("ResponseUsage")
    if isinstance(usage, dict):
        details = usage.get("properties", {}).get("input_tokens_details")
        _drop_required(details, _OPENAI_RESPONSES_OPTIONAL_FIELDS)


def relax_bundled_spec(spec: dict[str, Any], filename: str) -> None:
    """Apply the documented relaxations for *filename* in place."""
    schemas = spec.get("components", {}).get("schemas", {})
    if filename == "anthropic.json":
        _relax_anthropic(schemas)
    elif filename == "openai_chat.json":
        _relax_chat(schemas)
    elif filename == "openai_responses.json":
        _relax_openai_responses(schemas)
    elif filename == "openresponses.json":
        _relax_open_responses(schemas)
