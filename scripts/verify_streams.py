#!/usr/bin/env python3
"""Verify streaming schema validation against a local SSE server."""

from __future__ import annotations

import json
import pathlib
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

SPECS_DIR = pathlib.Path(__file__).resolve().parent.parent / "src/llm_comply/specs"


class _SSEHandler(BaseHTTPRequestHandler):
    chunks: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        length = int(self.headers.get("content-length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for chunk in self.chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *args: Any) -> None:
        pass


def _chunk(content: str | None) -> dict[str, Any]:
    delta = {"role": "assistant"} if content is None else {"content": content}
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
        "choices": [
            {"index": 0, "delta": delta, "logprobs": None, "finish_reason": None}
        ],
    }


def _config(port: int) -> ComplianceConfig:
    args = _build_parser().parse_args(
        [
            "--format",
            "chat_completions",
            "-u",
            f"http://127.0.0.1:{port}",
            "-k",
            "test-key",
        ]
    )
    return ComplianceConfig.from_args(args)


def _test_case() -> TestCase:
    return TestCase(
        id="stream-schema",
        name="Stream Schema",
        description="Each chunk validates against the streaming schema",
        category=TestCategory.STREAMING,
        endpoint="/chat/completions",
        schema_name=None,
        streaming=True,
        stream_schema_name="CreateChatCompletionStreamResponse",
        build_request=lambda cfg: {
            "model": cfg.model,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )


def main() -> int:
    """Run the valid and invalid stream cases against captured SSE."""
    spec = SpecLoader(str(SPECS_DIR / "openai_chat.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SSEHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        runner = TestRunner(_config(port), [_test_case()], spec)
        _SSEHandler.chunks = [_chunk(None), _chunk("hello")]
        result = runner.run_one(_test_case())
        assert result.status == TestStatus.PASSED, result.errors

        _SSEHandler.chunks = [_chunk(None), {"id": "broken", "object": "chunk"}]
        result = runner.run_one(_test_case())
        assert result.status == TestStatus.FAILED, "invalid chunk was not rejected"
        assert any("choices" in error for error in result.errors), result.errors
    finally:
        server.shutdown()
        server.server_close()

    print("stream schema validation: valid chunks pass, invalid chunks fail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
