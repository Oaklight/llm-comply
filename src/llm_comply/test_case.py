"""Test case definition types."""

from __future__ import annotations

import dataclasses
import enum
from typing import Any
from collections.abc import Callable

from .config import ComplianceConfig


class TestCategory(enum.Enum):
    BASIC = "basic"
    STREAMING = "streaming"
    TOOLS = "tools"
    MULTIMODAL = "multimodal"
    ERROR_HANDLING = "error"


Validator = Callable[[Any, "ValidatorContext"], list[str]]


@dataclasses.dataclass
class ValidatorContext:
    """Context passed to validator functions."""

    streaming: bool = False
    sse_events: list[dict[str, Any]] | None = None


@dataclasses.dataclass
class TestCase:
    """A declarative compliance test case."""

    id: str
    name: str
    description: str
    category: TestCategory
    build_request: Callable[[ComplianceConfig], dict[str, Any]]
    validators: list[Validator] = dataclasses.field(default_factory=list)
    streaming: bool = False
    endpoint: str = "/responses"
    expected_statuses: list[int] = dataclasses.field(default_factory=lambda: [200])
    schema_name: str | None = "ResponseResource"
    validate_stream_events: bool = True
    skip_reason: Callable[[ComplianceConfig], str | None] | None = None
