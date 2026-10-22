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

_UNSUPPORTED_STATUSES = {400, 404, 405, 422, 501}


def _error_detail(data: Any) -> str | None:
    """Extract a human-readable message from an error response body."""
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("status")
        if message:
            return str(message)
    elif isinstance(error, str):
        return error
    detail = data.get("detail")
    if isinstance(detail, str):
        return detail
    return None


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
        delay = self._config.delay

        for i, tc in enumerate(tests):
            if delay > 0 and i > 0:
                time.sleep(delay)
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
        status_code: int | None = None
        # A transport, status, parse, or schema failure is fatal for every
        # test, including optional ones. Only semantic findings from the
        # validators may be demoted to warnings.
        fatal = False
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

            # Optional capabilities may be unsupported by the provider.
            if (
                tc.optional
                and status_code not in tc.expected_statuses
                and status_code in _UNSUPPORTED_STATUSES
            ):
                reason = f"optional capability unsupported: HTTP {status_code}"
                detail = _error_detail(response_data)
                if detail:
                    reason += f" ({detail})"
                return TestResult(
                    id=tc.id,
                    name=tc.name,
                    status=TestStatus.SKIPPED,
                    duration_ms=(time.monotonic() - start) * 1000.0,
                    errors=[reason],
                    request=request_body,
                    response=response_data,
                )

            # Check HTTP status
            if status_code not in tc.expected_statuses:
                errors.append(f"HTTP {status_code} (expected {tc.expected_statuses})")
                fatal = True
            elif (
                tc.optional
                and not tc.streaming
                and (not isinstance(response_data, dict) or not response_data)
            ):
                # An optional capability must still answer with a non-empty
                # JSON object; an empty or text body says the endpoint itself
                # is broken, not that the tool is unsupported.
                errors.append("response is empty or not a JSON object")
                fatal = True

            # Schema validation (non-streaming response or final streaming response)
            if tc.schema_name and isinstance(response_data, dict) and not errors:
                schema_errors = self._spec.validate(response_data, tc.schema_name)
                if schema_errors:
                    fatal = True
                errors.extend(schema_errors)

            # Per-event schema validation for streaming
            stream_errors_start = len(errors)
            if tc.streaming and tc.validate_stream_events and sse_events:
                for event in sse_events:
                    edata = event.get("data")
                    if event.get("_parse_error"):
                        errors.append(
                            f"stream event is not valid JSON: {str(edata)[:200]}"
                        )
                        continue
                    if event.get("_invalid_payload"):
                        errors.append(f"stream event is not a JSON object: {edata!r}")
                        continue
                    if not isinstance(edata, dict):
                        continue
                    # Untyped providers send {"error": {...}} when the stream
                    # dies after headers; report the server's message rather
                    # than blaming the chunk schema.
                    if "error" in edata and len(edata) == 1:
                        err = edata["error"]
                        message = (
                            err.get("message", err) if isinstance(err, dict) else err
                        )
                        errors.append(f"stream error: {message}")
                        continue
                    if tc.stream_schema_name:
                        event_errors = self._spec.validate(edata, tc.stream_schema_name)
                    else:
                        etype = event.get("type", "")
                        if etype == "[DONE]":
                            continue
                        event_errors = self._spec.validate_sse_event(etype, edata)
                    errors.extend(event_errors)
            if len(errors) > stream_errors_start:
                fatal = True

            # Semantic validators
            ctx = ValidatorContext(streaming=tc.streaming, sse_events=sse_events)
            for validator in tc.validators:
                errors.extend(validator(response_data, ctx))

        except Exception as exc:
            errors.append(f"exception: {exc}")
            fatal = True
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

        # Optional capabilities are advisory only when the provider answered a
        # well-formed response at an expected status: a missing built-in-tool
        # artifact is then a warning. Status, transport, parse, and schema
        # failures remain fatal (they are protocol failures, not capability
        # gaps), as do authentication and throttling errors.
        if tc.optional and errors and not fatal:
            warnings.extend(errors)
            errors = []

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
