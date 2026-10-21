"""OpenAPI spec loading and JSON Schema validation."""

from __future__ import annotations

import datetime
import gzip
import hashlib
import importlib.util
import json
import pathlib
import re
from typing import Any

from .formats import (
    DEFAULT_FORMAT,
    SCHEMA_VALIDATED_FORMATS,
    SPEC_FILES,
    SPEC_SOURCES,
)


def _has_jsonschema() -> bool:
    return importlib.util.find_spec("jsonschema") is not None


_SPECS_DIR = pathlib.Path(__file__).parent / "specs"

_MANIFEST_PATH = _SPECS_DIR / "manifest.json"
_MANIFEST_SCHEMA_VERSION = 1

_FORMAT_NOTES = {
    "google_generate": "Bundled from Google's OpenAPI discovery document; runtime validation is semantic",
    "google_interactions": "Bundled from Google's Interactions OpenAPI spec; runtime validation is semantic",
}

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

    @staticmethod
    def manifest_path() -> pathlib.Path:
        """Return the path of the committed spec manifest."""
        return _MANIFEST_PATH

    @classmethod
    def _entry_from_file(cls, fmt: str, path: pathlib.Path) -> dict[str, Any]:
        raw = path.read_bytes()
        spec = json.loads(raw)
        schemas = spec.get("components", {}).get("schemas", {})
        source = SPEC_SOURCES.get(fmt)
        entry: dict[str, Any] = {
            "bundled_file": path.name,
            "validation": "schema" if fmt in SCHEMA_VALIDATED_FORMATS else "semantic",
            "spec_version": spec.get("info", {}).get("version", "unknown"),
            "openapi_version": spec.get("openapi", "unknown"),
            "schema_count": len(schemas),
            "path_count": len(spec.get("paths", {})),
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "source_type": "upstream" if source else "manual",
            "source_url": source[0] if source else None,
        }
        if fmt in _FORMAT_NOTES:
            entry["note"] = _FORMAT_NOTES[fmt]
        return entry

    @classmethod
    def _semantic_entry(cls, fmt: str) -> dict[str, Any]:
        """Build the manifest entry for a format with no bundled spec."""
        entry: dict[str, Any] = {
            "bundled_file": None,
            "validation": "semantic",
            "spec_version": None,
            "openapi_version": None,
            "schema_count": 0,
            "path_count": 0,
            "size_bytes": 0,
            "sha256": None,
            "source_type": "none",
            "source_url": None,
        }
        note = _FORMAT_NOTES.get(fmt)
        if note:
            entry["note"] = note
        return entry

    @classmethod
    def load_manifest(cls) -> dict[str, Any]:
        """Load the committed spec manifest, or an empty one if absent."""
        if not _MANIFEST_PATH.exists():
            return {"schema_version": _MANIFEST_SCHEMA_VERSION, "formats": {}}
        with open(_MANIFEST_PATH) as f:
            return json.load(f)

    @classmethod
    def assemble_manifest(cls) -> dict[str, Any]:
        """Build the spec manifest from the bundled spec files.

        ``refreshed_at`` carries over from the previous manifest when a file's
        content hash is unchanged, so it records when the spec last changed.
        """
        previous = cls.load_manifest().get("formats", {})
        today = datetime.date.today().isoformat()
        formats: dict[str, Any] = {}
        for fmt, filename in SPEC_FILES.items():
            if filename is None:
                formats[fmt] = cls._semantic_entry(fmt)
                continue
            path = _SPECS_DIR / filename
            if not path.exists():
                # A newly configured format may not be bundled yet.
                continue
            entry = cls._entry_from_file(fmt, path)
            prev = previous.get(fmt)
            if prev and prev.get("sha256") == entry["sha256"]:
                entry["refreshed_at"] = prev.get("refreshed_at", today)
            else:
                entry["refreshed_at"] = today
            formats[fmt] = entry
        return {"schema_version": _MANIFEST_SCHEMA_VERSION, "formats": formats}

    @classmethod
    def write_manifest(cls) -> pathlib.Path:
        """Regenerate and write the committed spec manifest."""
        manifest = cls.assemble_manifest()
        _MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
        return _MANIFEST_PATH

    @classmethod
    def check_manifest(cls) -> list[str]:
        """Return drift between the committed manifest and bundled specs."""
        manifest = cls.load_manifest()
        if manifest.get("schema_version") != _MANIFEST_SCHEMA_VERSION:
            return [
                f"manifest schema_version is {manifest.get('schema_version')!r}, "
                f"expected {_MANIFEST_SCHEMA_VERSION}"
            ]
        recorded = manifest.get("formats", {})
        problems: list[str] = [
            f"{fmt}: not a known format" for fmt in recorded if fmt not in SPEC_FILES
        ]
        for fmt, filename in SPEC_FILES.items():
            entry = recorded.get(fmt)
            if entry is None:
                problems.append(f"{fmt}: missing from manifest")
                continue
            if filename is None:
                expected = cls._semantic_entry(fmt)
            else:
                path = _SPECS_DIR / filename
                if not path.exists():
                    problems.append(f"{fmt}: bundled file {filename} is missing")
                    continue
                expected = cls._entry_from_file(fmt, path)
            for key in sorted(expected):
                if entry.get(key) != expected[key]:
                    problems.append(
                        f"{fmt}: {key} is {entry.get(key)!r}, "
                        f"expected {expected[key]!r}"
                    )
            extra = sorted(set(entry) - set(expected) - {"refreshed_at"})
            if extra:
                problems.append(f"{fmt}: unexpected manifest fields {extra}")
            refreshed_at = entry.get("refreshed_at")
            if filename is not None and refreshed_at is None:
                problems.append(f"{fmt}: missing refreshed_at")
            elif refreshed_at is not None and not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", str(refreshed_at)
            ):
                problems.append(
                    f"{fmt}: refreshed_at is {refreshed_at!r}, expected YYYY-MM-DD"
                )
        return problems

    @classmethod
    def fetch_latest(
        cls,
        fmt: str = DEFAULT_FORMAT,
        output_path: str | None = None,
        update_manifest: bool = True,
    ) -> str:
        """Fetch the latest upstream spec for a format and save it to disk.

        Args:
            fmt: Format name; must be a key of :data:`SPEC_SOURCES`.
            output_path: Destination path. Defaults to the bundled spec file
                for *fmt*.
            update_manifest: Rewrite the manifest after saving to the bundled
                path. Set false when refreshing several formats in one run.

        Raises:
            ValueError: If *fmt* has no public upstream source, or the fetched
                document is not an OpenAPI spec with schemas.

        Returns:
            A human-readable summary of the saved spec.
        """
        from llm_comply._vendor.httpclient import Response, get

        source = SPEC_SOURCES.get(fmt)
        if source is None:
            available = ", ".join(sorted(SPEC_SOURCES))
            raise ValueError(
                f"no upstream spec source for format '{fmt}' (available: {available})"
            )
        url, filename = source

        raw = get(url, timeout=60)
        assert isinstance(raw, Response)
        raw.raise_for_status()

        # Some publishers ship the spec gzip-compressed (e.g. Anthropic SDK).
        payload = raw.content
        if payload[:2] == b"\x1f\x8b":
            payload = gzip.decompress(payload)

        # Parse before writing so a bad response never corrupts the bundled spec.
        spec = json.loads(payload)
        schemas = spec.get("components", {}).get("schemas", {})
        if not spec.get("openapi") or not schemas:
            raise ValueError(
                f"fetched document for '{fmt}' is not an OpenAPI spec with schemas"
            )

        dest = pathlib.Path(output_path) if output_path else _SPECS_DIR / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        if output_path is None and update_manifest:
            cls.write_manifest()

        version = spec.get("info", {}).get("version", "unknown")
        return (
            f"Saved {fmt} spec v{version} to {dest} "
            f"({len(schemas)} schemas, {len(payload)} bytes)"
        )
