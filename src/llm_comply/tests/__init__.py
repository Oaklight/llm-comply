"""Test suite registry."""

from __future__ import annotations

from llm_comply.formats import normalize_format
from llm_comply.test_case import TestCase


def get_tests(fmt: str) -> list[TestCase]:
    """Load test cases for the given API format.

    Args:
        fmt: Canonical format name or a legacy alias.

    Returns:
        The test cases for *fmt*.
    """
    fmt = normalize_format(fmt)
    if fmt == "chat_completions":
        from .openai_chat import OPENAI_CHAT_TESTS

        return OPENAI_CHAT_TESTS
    if fmt == "messages":
        from .anthropic import ANTHROPIC_TESTS

        return ANTHROPIC_TESTS
    if fmt == "google_generate":
        from .google_genai import GOOGLE_GENAI_TESTS

        return GOOGLE_GENAI_TESTS
    if fmt == "google_interactions":
        from .google_interactions import GOOGLE_INTERACTIONS_TESTS

        return GOOGLE_INTERACTIONS_TESTS
    if fmt == "openai_responses":
        from .openai_responses import OPENAI_RESPONSES_TESTS

        return OPENAI_RESPONSES_TESTS
    from .open_responses import OPEN_RESPONSES_TESTS

    return OPEN_RESPONSES_TESTS
