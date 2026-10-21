"""Canonical API format names shared by the CLI, web UI, and test suites.

Names match the base format identifiers used by llm-rosetta, the in-house
downstream consumer. Legacy llm-comply spellings are accepted as aliases.
"""

from __future__ import annotations

DEFAULT_FORMAT = "open_responses"

FORMATS = (
    "open_responses",
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
}

# Per-format spec metadata: bundled file (None = no spec) and validation mode.
# This is the single source of truth; derived views below must not be
# maintained by hand.
FORMAT_SPECS: dict[str, tuple[str | None, str]] = {
    "open_responses": ("openresponses.json", "schema"),
    "chat_completions": ("openai_chat.json", "schema"),
    "messages": ("anthropic.json", "schema"),
    "google_generate": (None, "semantic"),
    # The bundled Interactions spec has no verified upstream and is
    # reference-only, so runtime validation stays semantic.
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
    "chat_completions": (
        "https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.json",
        "openai_chat.json",
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
