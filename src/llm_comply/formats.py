"""Canonical API format names shared by the CLI, web UI, and test suites.

Names match the base format identifiers used by llm-rosetta, the in-house
downstream consumer. Legacy llm-comply spellings are accepted as aliases.
"""

from __future__ import annotations

DEFAULT_FORMAT = "open_responses"

FORMATS = (
    "open_responses",
    "openai_responses",
    "chat_completions",
    "messages",
    "google_generate",
    "google_interactions",
)

# Legacy spellings accepted from llm-comply <= 0.5.0.
FORMAT_ALIASES: dict[str, str] = {
    "open-responses": "open_responses",
    "openai-chat": "chat_completions",
    "anthropic": "messages",
    "google-genai": "google_generate",
    # v0.5.0 canonical spelling, retained for compatibility.
    "google-interactions": "google_interactions",
    "openai-responses": "openai_responses",
}

# Per-format spec metadata: bundled file (None = no spec) and validation mode.
# This is the single source of truth; derived views below must not be
# maintained by hand.
FORMAT_SPECS: dict[str, tuple[str | None, str]] = {
    "open_responses": ("openresponses.json", "schema"),
    "openai_responses": ("openai_responses.json", "schema"),
    "chat_completions": ("openai_chat.json", "schema"),
    "messages": ("anthropic.json", "schema"),
    "google_generate": ("google_generate.json", "semantic"),
    # Google specs are bundled for tracking, but runtime validation stays
    # semantic until the validators are extended.
    "google_interactions": ("google_interactions.json", "semantic"),
}

# Bundled spec file per format. None means no spec is bundled.
SPEC_FILES: dict[str, str | None] = {
    fmt: filename for fmt, (filename, _mode) in FORMAT_SPECS.items()
}

# Spec files that drive runtime schema validation.
VALIDATION_SPEC_FILES: dict[str, str | None] = {
    fmt: filename if mode == "schema" else None
    for fmt, (filename, mode) in FORMAT_SPECS.items()
}

SCHEMA_VALIDATED_FORMATS = frozenset(
    fmt for fmt, (_filename, mode) in FORMAT_SPECS.items() if mode == "schema"
)

# Public upstream sources: format -> (url, bundled filename).
SPEC_SOURCES: dict[str, tuple[str, str]] = {
    "open_responses": (
        "https://raw.githubusercontent.com/openresponses/openresponses/main/public/openapi/openapi.json",
        "openresponses.json",
    ),
    "openai_responses": (
        # Same upstream document as chat_completions; fetch_latest extracts the
        # /responses paths and their transitive schemas.
        "https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.json",
        "openai_responses.json",
    ),
    "chat_completions": (
        "https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.json",
        "openai_chat.json",
    ),
    # Anthropic publishes no stable spec permalink. The official SDKs ship the
    # generated OpenAPI document as a gzip artifact used by their mock server;
    # the Python and TypeScript copies are byte-identical. The older
    # .stats.yml `openapi_spec_url` field is no longer present.
    "messages": (
        "https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/scripts/mock-spec.json.gz",
        "anthropic.json",
    ),
    "google_generate": (
        "https://generativelanguage.googleapis.com/$discovery/OPENAPI3_0?version=v1beta",
        "google_generate.json",
    ),
    "google_interactions": (
        "https://ai.google.dev/static/api/interactions.openapi.json",
        "google_interactions.json",
    ),
}

# update-spec choices: refreshable formats plus legacy spellings mapping to them.
REFRESHABLE_FORMATS = tuple(SPEC_SOURCES)
REFRESHABLE_CHOICES = REFRESHABLE_FORMATS + tuple(
    alias for alias, canonical in FORMAT_ALIASES.items() if canonical in SPEC_SOURCES
)

# Extra headers each format needs by default.
EXTRA_HEADERS: dict[str, dict[str, str]] = {
    "messages": {"anthropic-version": "2023-06-01"},
}


def normalize_format(name: str) -> str:
    """Return the canonical format name, accepting legacy aliases.

    Args:
        name: A canonical format name or a legacy alias.

    Raises:
        ValueError: If the name is not a known format.

    Returns:
        The canonical format name.
    """
    canonical = FORMAT_ALIASES.get(name, name)
    if canonical not in FORMATS:
        choices = ", ".join(FORMATS)
        raise ValueError(f"unknown format {name!r}; choose from: {choices}")
    return canonical
