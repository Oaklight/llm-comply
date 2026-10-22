#!/usr/bin/env python3
"""Verify optional tests skip on unsupported capabilities."""

from __future__ import annotations

import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from llm_comply.cli import _build_parser
from llm_comply.config import ComplianceConfig
from llm_comply.result import TestStatus
from llm_comply.runner import TestRunner
from llm_comply.schema import SpecLoader
from llm_comply.test_case import TestCase, TestCategory


class _Handler(BaseHTTPRequestHandler):
    status = 200
    body: dict[str, Any] = {}

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        length = int(self.headers.get("content-length", 0))
        self.rfile.read(length)
        payload = json.dumps(self.body).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:
        pass


def _config(port: int) -> ComplianceConfig:
    args = _build_parser().parse_args(
        [
            "--format",
            "google_interactions",
            "-u",
            f"http://127.0.0.1:{port}",
            "-k",
            "test-key",
        ]
    )
    return ComplianceConfig.from_args(args)


def _case(optional: bool) -> TestCase:
    return TestCase(
        id="optional-capability",
        name="Optional Capability",
        description="",
        category=TestCategory.TOOLS,
        endpoint="/v1beta/interactions",
        schema_name=None,
        build_request=lambda cfg: {"model": cfg.model, "input": "hi"},
        validators=[],
        optional=optional,
    )


def main() -> int:
    """Assert optional tests distinguish capability gaps from protocol failures."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        runner = TestRunner(_config(port), [_case(True)], SpecLoader(None))

        _Handler.status = 200
        _Handler.body = {"id": "int_1", "object": "interaction", "status": "completed"}
        result = runner.run_one(_case(True))
        assert result.status == TestStatus.PASSED, result.errors

        _Handler.status = 400
        _Handler.body = {"error": {"message": "google_search is not supported"}}
        result = runner.run_one(_case(True))
        assert result.status == TestStatus.SKIPPED, result.errors
        assert any("google_search is not supported" in e for e in result.errors), (
            result.errors
        )

        # The same status fails a non-optional test.
        result = runner.run_one(_case(False))
        assert result.status == TestStatus.FAILED, result.errors

        # A server error is a protocol failure, not a capability gap: it still
        # fails an optional test.
        _Handler.status = 500
        _Handler.body = {"error": {"message": "boom"}}
        result = runner.run_one(_case(True))
        assert result.status == TestStatus.FAILED, result.errors

        # Semantic shortfalls (the provider answered with a well-formed JSON
        # object but not with the tool output the test asked for) are warnings.
        case = _case(True)
        case.validators = [lambda data, ctx: ["executableCode is missing"]]
        _Handler.status = 200
        _Handler.body = {"id": "int_1"}
        result = runner.run_one(case)
        assert result.status == TestStatus.PASSED, result.errors
        assert result.warnings == ["executableCode is missing"], result.warnings

        # A 200 that is not a JSON object is a protocol failure too.
        _Handler.body = "not json at all"
        result = runner.run_one(_case(True))
        assert result.status == TestStatus.FAILED, result.errors

        # So is an empty JSON object.
        _Handler.body = {}
        result = runner.run_one(_case(True))
        assert result.status == TestStatus.FAILED, result.errors

        # A JSON object that violates a real response schema fails as well.
        spec_path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "src/llm_comply/specs/anthropic.json"
        )
        schema_runner = TestRunner(
            _config(port), [_case(True)], SpecLoader(str(spec_path))
        )
        case = _case(True)
        case.schema_name = "Message"
        _Handler.body = {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": "not-a-list",
            "model": "claude",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "stop_details": None,
            "usage": {
                "input_tokens": 1,
                "output_tokens": 2,
                "cache_creation": None,
                "cache_creation_input_tokens": None,
                "cache_read_input_tokens": None,
                "inference_geo": None,
                "service_tier": None,
            },
            "container": None,
        }
        result = schema_runner.run_one(case)
        assert result.status == TestStatus.FAILED, result.errors
        assert any("content" in error for error in result.errors), result.errors

        # A transport failure is fatal for an optional test.
        with patch(
            "llm_comply.runner.make_request", side_effect=ConnectionError("reset")
        ):
            result = runner.run_one(_case(True))
        assert result.status == TestStatus.FAILED, result.errors

        # An optional streaming test that receives no events at all is a
        # protocol failure, not a capability gap.
        streaming = _case(True)
        streaming.streaming = True
        for events in ([], None):
            with patch(
                "llm_comply.runner.make_request", return_value=(200, None, events)
            ):
                result = runner.run_one(streaming)
            assert result.status == TestStatus.FAILED, (events, result.errors)

        # A malformed stream event is fatal too.
        broken_event = [{"data": "junk", "_parse_error": True}]
        with patch(
            "llm_comply.runner.make_request", return_value=(200, None, broken_event)
        ):
            result = runner.run_one(streaming)
        assert result.status == TestStatus.FAILED, result.errors

        # Authentication and throttling failures say nothing about whether the
        # capability is supported, so they fail as well.
        for auth_status in (401, 403, 429):
            _Handler.status = auth_status
            _Handler.body = {"error": {"message": "invalid key"}}
            result = runner.run_one(_case(True))
            assert result.status == TestStatus.FAILED, (auth_status, result.warnings)
            assert result.warnings == [], (auth_status, result.warnings)

        # The same semantic shortfall still fails a non-optional test.
        non_optional = _case(False)
        non_optional.validators = [lambda data, ctx: ["executableCode is missing"]]
        _Handler.status = 200
        _Handler.body = {"id": "int_1"}
        result = runner.run_one(non_optional)
        assert result.status == TestStatus.FAILED, result.errors
    finally:
        server.shutdown()
        server.server_close()

    print(
        "optional tests: unsupported statuses skip; capability shortfalls warn; "
        "protocol failures fail"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
