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
# omits them: text blocks only carry ``citations`` when citations are enabled,
# ``server_tool_use`` only carries ``caller`` in some releases, and usage omits
# the details objects when the capability was not used.
_ANTHROPIC_OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {
    "Usage": ("output_tokens_details", "server_tool_use"),
    "ResponseTextBlock": ("citations",),
    "ResponseServerToolUseBlock": ("caller",),
}

# OpenAI's chat completion responses omit ``logprobs`` entirely (the field is
# nullable in the docs) and return ``system_fingerprint: null`` for the
# deprecated fingerprint. Both are present in the OpenAI OpenAPI document as
# required/non-nullable, so relax at load time.
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


def relax_bundled_spec(spec: dict[str, Any], filename: str) -> None:
    """Apply the documented relaxations for *filename* in place."""
    schemas = spec.get("components", {}).get("schemas", {})
    if filename == "anthropic.json":
        _relax_anthropic(schemas)
    elif filename == "openai_chat.json":
        _relax_chat(schemas)
    elif filename == "openresponses.json":
        _relax_open_responses(schemas)
