"""Test runner: orchestrates compliance test execution."""

from __future__ import annotations

import time
import traceback
from typing import Any
from collections.abc import Callable

from .config import ComplianceConfig
from .http import make_request
from .result import SuiteResult, TestResult, TestStatus
from .schema import SpecLoader
from .test_case import TestCase, ValidatorContext


class TestRunner:
    """Runs compliance tests sequentially."""

    def __init__(
        self,
        config: ComplianceConfig,
        test_cases: list[TestCase],
        spec_loader: SpecLoader,
        on_result: Callable[[TestResult], None] | None = None,
    ) -> None:
        self._config = config
        self._tests = test_cases
        self._spec = spec_loader
        self._on_result = on_result

    def run_all(self) -> SuiteResult:
        suite = SuiteResult()
        tests = self._filtered_tests()

        for tc in tests:
            result = self.run_one(tc)
            suite.results.append(result)
            if self._on_result:
                self._on_result(result)

        return suite

    def run_one(self, tc: TestCase) -> TestResult:
        # Check skip
        if tc.skip_reason:
            reason = tc.skip_reason(self._config)
            if reason:
                return TestResult(
                    id=tc.id,
                    name=tc.name,
                    status=TestStatus.SKIPPED,
                    errors=[reason],
                )

        errors: list[str] = []
        request_body: dict[str, Any] = {}
        response_data: Any = None
        sse_events: list[dict[str, Any]] | None = None
        start = time.monotonic()

        try:
            request_body = tc.build_request(self._config)
            endpoint = request_body.pop("_google_endpoint", None) or tc.endpoint
            status_code, response_data, sse_events = make_request(
                self._config,
                endpoint,
                request_body,
                streaming=tc.streaming,
            )

            # Check HTTP status
            if status_code not in tc.expected_statuses:
                errors.append(f"HTTP {status_code} (expected {tc.expected_statuses})")

            # Schema validation (non-streaming response or final streaming response)
            if tc.schema_name and isinstance(response_data, dict) and not errors:
                schema_errors = self._spec.validate(response_data, tc.schema_name)
                errors.extend(schema_errors)

            # Per-event schema validation for streaming
            if tc.streaming and tc.validate_stream_events and sse_events:
                for event in sse_events:
                    etype = event.get("type", "")
                    edata = event.get("data")
                    if etype == "[DONE]" or not isinstance(edata, dict):
                        continue
                    event_errors = self._spec.validate_sse_event(etype, edata)
                    errors.extend(event_errors)

            # Semantic validators
            ctx = ValidatorContext(streaming=tc.streaming, sse_events=sse_events)
            for validator in tc.validators:
                errors.extend(validator(response_data, ctx))

        except Exception as exc:
            errors.append(f"exception: {exc}")
            if self._config.verbose:
                errors.append(traceback.format_exc())

        # Filter ignored errors
        if errors and self._config.ignore_errors:
            errors = [
                e
                for e in errors
                if not any(pat in e for pat in self._config.ignore_errors)
            ]

        elapsed = (time.monotonic() - start) * 1000.0

        _WARNING_PREFIX = "[warning] "
        warnings = [
            e[len(_WARNING_PREFIX) :] for e in errors if e.startswith(_WARNING_PREFIX)
        ]
        errors = [e for e in errors if not e.startswith(_WARNING_PREFIX)]

        status = TestStatus.PASSED if not errors else TestStatus.FAILED

        return TestResult(
            id=tc.id,
            name=tc.name,
            status=status,
            duration_ms=elapsed,
            errors=errors,
            warnings=warnings,
            request=request_body if self._config.verbose else None,
            response=response_data if self._config.verbose else None,
            stream_events=sse_events if self._config.verbose else None,
        )

    def _filtered_tests(self) -> list[TestCase]:
        if not self._config.filter_ids:
            return self._tests
        ids = set(self._config.filter_ids)
        return [tc for tc in self._tests if tc.id in ids]
