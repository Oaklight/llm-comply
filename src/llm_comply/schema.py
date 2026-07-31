"""OpenAPI spec loading and JSON Schema validation."""

from __future__ import annotations

import importlib.util
import json
import pathlib
from typing import Any


def _has_jsonschema() -> bool:
    return importlib.util.find_spec("jsonschema") is not None


_SPECS_DIR = pathlib.Path(__file__).parent / "specs"
_BUNDLED_SPEC = _SPECS_DIR / "openresponses.json"
_REMOTE_URL = "https://raw.githubusercontent.com/openresponses/openresponses/main/public/openapi/openapi.json"

SSE_EVENT_TO_SCHEMA: dict[str, str] = {
    "response.created": "ResponseCreatedStreamingEvent",
    "response.queued": "ResponseQueuedStreamingEvent",
    "response.in_progress": "ResponseInProgressStreamingEvent",
    "response.completed": "ResponseCompletedStreamingEvent",
    "response.failed": "ResponseFailedStreamingEvent",
    "response.incomplete": "ResponseIncompleteStreamingEvent",
    "response.output_item.added": "ResponseOutputItemAddedStreamingEvent",
    "response.output_item.done": "ResponseOutputItemDoneStreamingEvent",
    "response.content_part.added": "ResponseContentPartAddedStreamingEvent",
    "response.content_part.done": "ResponseContentPartDoneStreamingEvent",
    "response.output_text.delta": "ResponseOutputTextDeltaStreamingEvent",
    "response.output_text.done": "ResponseOutputTextDoneStreamingEvent",
    "response.output_text.annotation.added": "ResponseOutputTextAnnotationAddedStreamingEvent",
    "response.function_call_arguments.delta": "ResponseFunctionCallArgumentsDeltaStreamingEvent",
    "response.function_call_arguments.done": "ResponseFunctionCallArgumentsDoneStreamingEvent",
    "response.reasoning.delta": "ResponseReasoningDeltaStreamingEvent",
    "response.reasoning.done": "ResponseReasoningDoneStreamingEvent",
    "response.reasoning_summary.delta": "ResponseReasoningSummaryDeltaStreamingEvent",
    "response.reasoning_summary.done": "ResponseReasoningSummaryDoneStreamingEvent",
    "response.reasoning_summary_part.added": "ResponseReasoningSummaryPartAddedStreamingEvent",
    "response.reasoning_summary_part.done": "ResponseReasoningSummaryPartDoneStreamingEvent",
    "response.refusal.delta": "ResponseRefusalDeltaStreamingEvent",
    "response.refusal.done": "ResponseRefusalDoneStreamingEvent",
    "error": "ErrorStreamingEvent",
}

TERMINAL_EVENTS = {
    "response.completed",
    "response.failed",
    "response.incomplete",
}


def _patch_nullable(obj: Any) -> Any:
    """Convert OpenAPI 3.0 ``nullable: true`` to JSON Schema ``type: [..., "null"]``."""
    if not isinstance(obj, dict):
        return obj
    for key, val in list(obj.items()):
        if isinstance(val, dict):
            _patch_nullable(val)
        elif isinstance(val, list):
            for item in val:
                _patch_nullable(item)
    if obj.pop("nullable", None):
        t = obj.get("type")
        if isinstance(t, str):
            obj["type"] = [t, "null"]
        elif isinstance(t, list) and "null" not in t:
            t.append("null")
    return obj


class SpecLoader:
    """Loads an OpenAPI spec and validates data against extracted schemas."""

    def __init__(self, spec_path: str | None = None) -> None:
        if spec_path:
            path = pathlib.Path(spec_path)
            with open(path) as f:
                self._spec: dict[str, Any] = json.load(f)
            _patch_nullable(self._spec.get("components", {}))
        else:
            self._spec = {}
        self._schemas: dict[str, Any] = self._spec.get("components", {}).get(
            "schemas", {}
        )
        self._validator_cache: dict[str, Any] = {}

    @property
    def spec_version(self) -> str:
        return self._spec.get("info", {}).get("version", "unknown")

    @property
    def schema_names(self) -> list[str]:
        return list(self._schemas.keys())

    def get_schema(self, name: str) -> dict[str, Any] | None:
        return self._schemas.get(name)

    def validate(self, data: Any, schema_name: str) -> list[str]:
        """Validate data against a named schema. Returns error messages."""
        if not _has_jsonschema():
            return ["jsonschema not installed — schema validation skipped"]

        schema = self._schemas.get(schema_name)
        if schema is None:
            return [f"schema '{schema_name}' not found in spec"]

        try:
            validator = self._get_validator(schema_name, schema)
            errors: list[str] = []
            for error in validator.iter_errors(data):
                path = ".".join(str(p) for p in error.absolute_path)
                msg = error.message
                if path:
                    msg = f"{path}: {msg}"
                errors.append(msg)
            return errors
        except Exception as exc:
            return [f"validation error: {exc}"]

    def validate_sse_event(
        self, event_type: str, event_data: dict[str, Any]
    ) -> list[str]:
        """Validate a single SSE event against its schema."""
        schema_name = SSE_EVENT_TO_SCHEMA.get(event_type)
        if schema_name is None:
            return [f"unknown SSE event type: {event_type}"]
        return self.validate(event_data, schema_name)

    def _get_validator(self, name: str, schema: dict[str, Any]) -> Any:
        if name in self._validator_cache:
            return self._validator_cache[name]

        import jsonschema
        import jsonschema.validators

        # Use the full OpenAPI spec as the base document so that
        # $ref: "#/components/schemas/X" resolves via JSON pointer.
        resolver = jsonschema.RefResolver("", self._spec)
        validator_cls = jsonschema.validators.validator_for(
            {"$schema": "https://json-schema.org/draft/2020-12/schema"}
        )
        validator = validator_cls(schema, resolver=resolver)
        self._validator_cache[name] = validator
        return validator

    @classmethod
    def fetch_latest(cls, output_path: str | None = None) -> str:
        """Fetch latest spec from GitHub and save to disk."""
        from llm_comply._vendor.httpclient import Response, get

        raw = get(_REMOTE_URL, timeout=30)
        assert isinstance(raw, Response)
        raw.raise_for_status()
        dest = pathlib.Path(output_path) if output_path else _BUNDLED_SPEC
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw.content)
        spec = json.loads(raw.content)
        version = spec.get("info", {}).get("version", "unknown")
        return f"Saved spec v{version} to {dest} ({len(raw.content)} bytes)"
