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
}

# Bundled spec file per format. None means no spec is bundled.
SPEC_FILES: dict[str, str | None] = {
    "open_responses": "openresponses.json",
    "chat_completions": "openai_chat.json",
    "messages": "anthropic.json",
    "google_generate": None,
    "google_interactions": "google_interactions.json",
}

# Spec files that drive runtime schema validation. Google Interactions ships a
# reference-only snapshot, so its validation stays semantic.
VALIDATION_SPEC_FILES: dict[str, str | None] = {
    "open_responses": "openresponses.json",
    "chat_completions": "openai_chat.json",
    "messages": "anthropic.json",
    "google_generate": None,
    "google_interactions": None,
}

SCHEMA_VALIDATED_FORMATS = frozenset(
    fmt for fmt, filename in VALIDATION_SPEC_FILES.items() if filename
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
