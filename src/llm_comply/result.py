"""Test result types."""

from __future__ import annotations

import dataclasses
import enum
from typing import Any


class TestStatus(enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclasses.dataclass
class TestResult:
    """Result of a single compliance test."""

    id: str
    name: str
    status: TestStatus
    duration_ms: float = 0.0
    errors: list[str] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)
    request: dict[str, Any] | None = None
    response: Any = None
    stream_events: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "duration_ms": round(self.duration_ms, 1),
        }
        if self.errors:
            d["errors"] = self.errors
        if self.warnings:
            d["warnings"] = self.warnings
        return d


@dataclasses.dataclass
class SuiteResult:
    """Aggregate results for a compliance run."""

    results: list[TestResult] = dataclasses.field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.PASSED)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.FAILED)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.SKIPPED)

    @property
    def warned(self) -> int:
        return sum(
            1 for r in self.results if r.warnings and r.status == TestStatus.PASSED
        )

    @property
    def total(self) -> int:
        return len(self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "results": [r.to_dict() for r in self.results],
        }
