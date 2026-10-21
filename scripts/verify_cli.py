#!/usr/bin/env python3
"""Verify per-format CLI transport defaults on the wire.

Runs the real request builder against a local capture server, so the asserted
values are the headers a target actually receives.
"""

from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from llm_comply.cli import _build_parser
from llm_comply.config import ComplianceConfig
from llm_comply.http import make_request


class _CaptureHandler(BaseHTTPRequestHandler):
    captured: list[dict[str, str]] = []

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        length = int(self.headers.get("content-length", 0))
        self.rfile.read(length)
        _CaptureHandler.captured.append(dict(self.headers))
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


def _config(port: int, *argv: str) -> ComplianceConfig:
    args = _build_parser().parse_args(
        [*argv, "-u", f"http://127.0.0.1:{port}", "-k", "test-key"]
    )
    return ComplianceConfig.from_args(args)


def _sent_headers(config: ComplianceConfig) -> dict[str, str]:
    _CaptureHandler.captured.clear()
    status, _body, _events = make_request(config, "/messages", {"model": "m"})
    assert status == 200, status
    assert _CaptureHandler.captured, "no request reached the capture server"
    return _CaptureHandler.captured[-1]


def _header(headers: dict[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def main() -> int:
    """Check the headers sent for every format and override path."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        headers = _sent_headers(_config(port, "--format", "messages"))
        assert _header(headers, "x-api-key") == "test-key"
        assert _header(headers, "anthropic-version") == "2023-06-01"
        assert _header(headers, "Authorization") is None

        for fmt in ("google_generate", "google_interactions"):
            headers = _sent_headers(_config(port, "--format", fmt))
            assert _header(headers, "x-goog-api-key") == "test-key", fmt
            assert _header(headers, "Authorization") is None, fmt

        for fmt in ("open_responses", "openai_responses", "chat_completions"):
            headers = _sent_headers(_config(port, "--format", fmt))
            assert _header(headers, "Authorization") == "Bearer test-key", fmt
            assert _header(headers, "x-api-key") is None, fmt

        # Explicit bearer flags beat the format default in both directions.
        headers = _sent_headers(
            _config(
                port,
                "--format",
                "messages",
                "--auth-header",
                "Authorization",
                "--bearer",
            )
        )
        assert _header(headers, "Authorization") == "Bearer test-key"
        assert _header(headers, "x-api-key") is None

        headers = _sent_headers(
            _config(port, "--format", "open_responses", "--no-bearer")
        )
        assert _header(headers, "Authorization") == "test-key"

        # User headers override defaults, but cannot replace the credential.
        headers = _sent_headers(
            _config(port, "--format", "messages", "-H", "anthropic-version:2024-01-01")
        )
        assert _header(headers, "anthropic-version") == "2024-01-01"

        headers = _sent_headers(
            _config(port, "--format", "messages", "-H", "x-api-key:injected")
        )
        assert _header(headers, "x-api-key") == "test-key"

        # Legacy aliases resolve to the canonical format defaults.
        headers = _sent_headers(_config(port, "--format", "anthropic"))
        assert _header(headers, "x-api-key") == "test-key"
        assert _header(headers, "Authorization") is None
    finally:
        server.shutdown()
        server.server_close()

    print("CLI format defaults: wire-level auth headers, bearer, and headers OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
