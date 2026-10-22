"""OpenAI Responses API compliance test definitions.

OpenAI's Responses API shares request/response shapes with the vendor-neutral
Open Responses format. Reuse the compatible cases, point them at OpenAI's
``Response`` schema, and keep the Open Responses-only phase tests out.
"""

from __future__ import annotations

import dataclasses

from ..test_case import TestCase
from .open_responses import OPEN_RESPONSES_TESTS

# Cases whose request and response shapes OpenAI's Responses API supports.
_COMPATIBLE_TEST_IDS = {
    "basic-response",
    "system-prompt",
    "multi-turn",
    "tool-calling",
    "streaming-response",
    "streaming-usage",
    "image-input",
    "file-input",
    "compact-response",
    "compact-missing-model",
    "reasoning-summary",
    "error-handling",
}


OPENAI_RESPONSES_TESTS: list[TestCase] = [
    dataclasses.replace(
        tc,
        id=f"openai-{tc.id}",
        description=tc.description.replace("Open Responses", "OpenAI Responses"),
        schema_name="Response" if tc.schema_name else None,
    )
    for tc in OPEN_RESPONSES_TESTS
    if tc.id in _COMPATIBLE_TEST_IDS
]
