#!/usr/bin/env python3
"""Verify optional tests skip on unsupported capabilities."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

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
    """Assert optional tests skip only for unsupported statuses."""
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

        # Server errors are never treated as "unsupported".
        _Handler.status = 500
        _Handler.body = {"error": {"message": "boom"}}
        result = runner.run_one(_case(True))
        assert result.status == TestStatus.FAILED, result.errors
    finally:
        server.shutdown()
        server.server_close()

    print("optional tests: unsupported statuses skip; other failures do not")
    return 0


if __name__ == "__main__":
    sys.exit(main())
