"""Test suite registry."""

from __future__ import annotations

from llm_comply.test_case import TestCase


def get_tests(fmt: str) -> list[TestCase]:
    """Load test cases for the given API format."""
    if fmt == "openai-chat":
        from .openai_chat import OPENAI_CHAT_TESTS

        return OPENAI_CHAT_TESTS
    if fmt == "anthropic":
        from .anthropic import ANTHROPIC_TESTS

        return ANTHROPIC_TESTS
    if fmt == "google-genai":
        from .google_genai import GOOGLE_GENAI_TESTS

        return GOOGLE_GENAI_TESTS
    if fmt == "google-interactions":
        from .google_interactions import GOOGLE_INTERACTIONS_TESTS

        return GOOGLE_INTERACTIONS_TESTS
    from .open_responses import OPEN_RESPONSES_TESTS

    return OPEN_RESPONSES_TESTS
