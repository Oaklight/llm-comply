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
from llm_comply.tests import get_tests

SPECS_DIR = pathlib.Path(__file__).resolve().parent.parent / "src/llm_comply/specs"


class _SSEHandler(BaseHTTPRequestHandler):
    chunks: list[Any] = []

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        length = int(self.headers.get("content-length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for chunk in self.chunks:
            if isinstance(chunk, str):
                # Raw SSE lines (comments, heartbeats) pass through as-is.
                line = chunk if chunk.startswith((":", "data:")) else f"data: {chunk}"
                self.wfile.write(f"{line}\n\n".encode())
            else:
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


def _tool_call_chunk() -> dict[str, Any]:
    delta = {
        "tool_calls": [
            {
                "index": 0,
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city":"SF"}'},
            }
        ]
    }
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
        "choices": [
            {"index": 0, "delta": delta, "logprobs": None, "finish_reason": None}
        ],
    }


def _delta_chunk(delta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
        "choices": [
            {"index": 0, "delta": delta, "logprobs": None, "finish_reason": None}
        ],
    }


def _finish_chunk(reason: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
        "choices": [
            {"index": 0, "delta": {}, "logprobs": None, "finish_reason": reason}
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

    # The shipped streaming cases must use the mechanism the runner exercises.
    chat_streams = [tc for tc in get_tests("chat_completions") if tc.streaming]
    assert chat_streams, "no streaming chat_completions cases"
    for tc in chat_streams:
        assert tc.validate_stream_events, tc.id
        assert tc.stream_schema_name == "CreateChatCompletionStreamResponse", tc.id
        assert tc.stream_schema_name in spec.schema_names, tc.id

    server = ThreadingHTTPServer(("127.0.0.1", 0), _SSEHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        runner = TestRunner(_config(port), [_test_case()], spec)
        _SSEHandler.chunks = [_chunk(None), _chunk("hello")]
        result = runner.run_one(_test_case())
        assert result.status == TestStatus.PASSED, result.errors

        # Bare data lines and SSE comments are heartbeats, not payloads.
        _SSEHandler.chunks = [
            ": keep-alive",
            _chunk(None),
            "",
            ": ping",
            "data:",
            "   ",
            _chunk("hello"),
        ]
        result = runner.run_one(_test_case())
        assert result.status == TestStatus.PASSED, result.errors

        # Tool-call-only streams are valid: text deltas are not required.
        shipped = {tc.id: tc for tc in get_tests("chat_completions")}
        _SSEHandler.chunks = [
            _chunk(None),
            _tool_call_chunk(),
            _finish_chunk("tool_calls"),
        ]
        result = runner.run_one(shipped["chat-streaming-response"])
        assert result.status == TestStatus.PASSED, result.errors

        # Refusal-only streams are also valid progress.
        _SSEHandler.chunks = [
            _chunk(None),
            _delta_chunk({"refusal": "I cannot help with that."}),
            _finish_chunk("content_filter"),
        ]
        result = runner.run_one(shipped["chat-streaming-response"])
        assert result.status == TestStatus.PASSED, result.errors

        # Reasoning-only streams (vLLM-style) are progress too.
        for field in ("reasoning_content", "reasoning"):
            _SSEHandler.chunks = [
                _chunk(None),
                _delta_chunk({field: "thinking"}),
                _finish_chunk("stop"),
            ]
            result = runner.run_one(shipped["chat-streaming-response"])
            assert result.status == TestStatus.PASSED, (field, result.errors)

        # Empty reasoning text is not progress.
        _SSEHandler.chunks = [
            _chunk(None),
            _delta_chunk({"reasoning_content": ""}),
            _finish_chunk("stop"),
        ]
        result = runner.run_one(shipped["chat-streaming-response"])
        assert result.status == TestStatus.FAILED

        # The relaxation stays bounded: nothing, empty content, or an empty
        # tool_calls list must still fail.
        for chunks in (
            [_chunk(None), _finish_chunk("stop")],
            [_chunk(None), _chunk(""), _finish_chunk("stop")],
            [_chunk(None), _delta_chunk({"tool_calls": []}), _finish_chunk("stop")],
        ):
            _SSEHandler.chunks = chunks
            result = runner.run_one(shipped["chat-streaming-response"])
            assert result.status == TestStatus.FAILED, chunks

        _SSEHandler.chunks = [_chunk(None), {"id": "broken", "object": "chunk"}]
        result = runner.run_one(_test_case())
        assert result.status == TestStatus.FAILED, "invalid chunk was not rejected"
        assert any("choices" in error for error in result.errors), result.errors

        # A mid-stream error envelope is reported as such, not as a bad chunk.
        _SSEHandler.chunks = [
            {"error": {"message": "overloaded", "type": "server_error"}}
        ]
        result = runner.run_one(_test_case())
        assert result.status == TestStatus.FAILED
        assert any("stream error: overloaded" in e for e in result.errors), (
            result.errors
        )
        assert not any("choices" in e for e in result.errors), result.errors

        # Malformed payloads must fail with a diagnosis, not be skipped.
        _SSEHandler.chunks = ["not-json"]
        result = runner.run_one(_test_case())
        assert result.status == TestStatus.FAILED
        assert any("not valid JSON" in e for e in result.errors), result.errors

        _SSEHandler.chunks = [42]
        result = runner.run_one(_test_case())
        assert result.status == TestStatus.FAILED
        assert any("not a JSON object" in e for e in result.errors), result.errors
    finally:
        server.shutdown()
        server.server_close()

    print(
        "stream validation: valid chunks pass; invalid, error, and malformed "
        "payloads fail"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
