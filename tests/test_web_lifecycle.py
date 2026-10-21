"""Tests for web UI TLS, lifecycle metrics, and stream cancellation."""

from __future__ import annotations

import asyncio
import json
import shutil
import ssl
import subprocess
import time

import pytest

from llm_comply import cli, web
from llm_comply.result import TestResult as _TestResult
from llm_comply.result import TestStatus as _TestStatus


# ── Fixtures and helpers ─────────────────────────────────────────────────────


def _make_self_signed_cert(tmp_path):
    """Generate a throwaway certificate with the openssl CLI."""
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl is required to generate a test certificate")
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


class _Server:
    """Handle for a test server started with ``App._serve``."""

    def __init__(self, task: asyncio.Task) -> None:
        self.task = task
        self.port = web.app.port

    async def close(self) -> None:
        web.app.shutdown()
        await self.task


async def _start_server(*, ssl_context=None) -> _Server:
    web.app.port = None
    task = asyncio.create_task(web.app._serve("127.0.0.1", 0, ssl_context=ssl_context))
    for _ in range(500):
        if web.app.port:
            return _Server(task)
        if task.done():
            task.result()  # surface startup errors
        await asyncio.sleep(0.01)
    task.cancel()
    raise RuntimeError("server did not start")


async def _request(
    port: int,
    method: str,
    path: str,
    body: str | None = None,
    *,
    client_ssl=None,
):
    """Send one request and read the response until EOF."""
    payload = b"" if body is None else body.encode("utf-8")
    head = (
        f"{method} {path} HTTP/1.1\r\n"
        "Host: localhost\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("latin-1")
    reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=client_ssl)
    try:
        writer.write(head + payload)
        await writer.drain()
        data = await asyncio.wait_for(reader.read(), timeout=10)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            pass
    header_blob, _, body_blob = data.partition(b"\r\n\r\n")
    return header_blob.decode("latin-1"), body_blob


async def _read_until(reader, marker: bytes, timeout: float = 5.0) -> bytes:
    """Read until *marker* appears in the byte stream."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    buffer = b""
    while marker not in buffer:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"did not see {marker!r}")
        chunk = await asyncio.wait_for(reader.read(4096), remaining)
        if not chunk:
            break
        buffer += chunk
    if marker not in buffer:
        raise AssertionError(f"did not see {marker!r}; got {buffer[:500]!r}")
    return buffer


class _FakeRunner:
    """Stand-in for ``TestRunner`` so the SSE tests never hit the network."""

    delay = 0.001
    last: _FakeRunner | None = None

    def __init__(self, config, test_cases, spec_loader, **kwargs) -> None:
        self.calls = 0
        _FakeRunner.last = self

    def run_one(self, tc) -> _TestResult:
        self.calls += 1
        time.sleep(_FakeRunner.delay)
        return _TestResult(
            id=tc.id,
            name=tc.name,
            status=_TestStatus.PASSED,
            duration_ms=_FakeRunner.delay * 1000,
        )


class _FailingRunner:
    """Stand-in that raises, exercising the stream's failure terminal state."""

    last: _FailingRunner | None = None

    def __init__(self, config, test_cases, spec_loader, **kwargs) -> None:
        self.calls = 0
        _FailingRunner.last = self

    def run_one(self, tc) -> _TestResult:
        self.calls += 1
        raise RuntimeError("upstream exploded")


_RUN_BODY = json.dumps(
    {
        "format": "open_responses",
        "base_url": "http://example.invalid",
        "api_key": "test-key",
    }
)


# ── TLS ──────────────────────────────────────────────────────────────────────


def test_build_ssl_context_loads_certificate(tmp_path):
    cert, key = _make_self_signed_cert(tmp_path)
    context = web._build_ssl_context(str(cert), str(key))
    assert isinstance(context, ssl.SSLContext)
    assert context.protocol == ssl.PROTOCOL_TLS_SERVER


def test_https_server_serves_health(tmp_path):
    cert, key = _make_self_signed_cert(tmp_path)
    server_context = web._build_ssl_context(str(cert), str(key))
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.check_hostname = False
    client_context.verify_mode = ssl.CERT_NONE

    async def run():
        server = await _start_server(ssl_context=server_context)
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.port, ssl=client_context
            )
            try:
                version = writer.get_extra_info("ssl_object").version()
                writer.write(
                    b"GET /health HTTP/1.1\r\n"
                    b"Host: localhost\r\n"
                    b"Connection: close\r\n\r\n"
                )
                await writer.drain()
                data = await asyncio.wait_for(reader.read(), timeout=10)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (BrokenPipeError, ConnectionResetError):
                    pass
        finally:
            await server.close()
        return version, data

    version, data = asyncio.run(run())
    assert version in {"TLSv1.2", "TLSv1.3"}
    assert data.startswith(b"HTTP/1.1 200")
    assert b'"status": "ok"' in data


def test_serve_forwards_ssl_context(tmp_path, monkeypatch):
    cert, key = _make_self_signed_cert(tmp_path)
    captured = {}

    def fake_run(host, port, *, ssl_context=None):
        captured.update(host=host, port=port, ssl_context=ssl_context)

    monkeypatch.setattr(web.app, "run", fake_run)
    web.serve(host="127.0.0.1", port=1234, tls_cert=str(cert), tls_key=str(key))
    assert isinstance(captured["ssl_context"], ssl.SSLContext)


def test_build_ssl_context_rejects_missing_files(tmp_path):
    with pytest.raises(OSError):
        web._build_ssl_context(str(tmp_path / "cert.pem"), str(tmp_path / "key.pem"))


def test_serve_rejects_incomplete_tls_pair():
    with pytest.raises(ValueError, match="together"):
        web.serve(tls_cert="cert.pem")


def test_serve_rejects_empty_tls_paths():
    with pytest.raises(OSError):
        web.serve(tls_cert="", tls_key="")


def test_cli_rejects_incomplete_tls_pair(capsys):
    assert cli.main(["--web", "--tls-cert", "cert.pem"]) == 2
    assert "together" in capsys.readouterr().err


def test_cli_rejects_tls_without_web(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--tls-cert", "cert.pem", "--tls-key", "key.pem"])
    assert excinfo.value.code == 2
    assert "--web" in capsys.readouterr().err


def test_cli_accepts_tls_pair():
    args = cli._build_parser().parse_args(
        ["--web", "--tls-cert", "cert.pem", "--tls-key", "key.pem"]
    )
    assert args.tls_cert == "cert.pem"
    assert args.tls_key == "key.pem"


# ── Metrics ──────────────────────────────────────────────────────────────────


def test_health_reports_metrics():
    async def run():
        server = await _start_server()
        try:
            before = web._metrics.to_dict()
            _, body = await _request(server.port, "GET", "/health")
            payload = json.loads(body)
            assert payload["status"] == "ok"
            assert set(payload["metrics"]) == {
                "runs_started",
                "runs_completed",
                "runs_aborted",
                "runs_failed",
                "requests_completed",
                "client_disconnects",
            }
            # A health poll is a request, not a run.
            for key in (
                "runs_started",
                "runs_completed",
                "runs_aborted",
                "runs_failed",
            ):
                assert payload["metrics"][key] == before[key]
        finally:
            await server.close()

    asyncio.run(run())


def test_stream_run_reports_completion(monkeypatch):
    monkeypatch.setattr(web, "TestRunner", _FakeRunner)
    _FakeRunner.delay = 0.001

    async def run():
        server = await _start_server()
        try:
            before_started = web._metrics.runs_started
            before_completed = web._metrics.runs_completed
            before_failed = web._metrics.runs_failed
            _, body = await _request(server.port, "POST", "/api/run/stream", _RUN_BODY)
            assert b"event: suite_complete" in body
            assert web._metrics.runs_started == before_started + 1
            assert web._metrics.runs_completed == before_completed + 1
            assert web._metrics.runs_failed == before_failed
        finally:
            await server.close()

    asyncio.run(run())


def test_stream_run_reports_failure(monkeypatch):
    monkeypatch.setattr(web, "TestRunner", _FailingRunner)

    async def run():
        server = await _start_server()
        try:
            before_started = web._metrics.runs_started
            before_completed = web._metrics.runs_completed
            before_aborted = web._metrics.runs_aborted
            before_failed = web._metrics.runs_failed
            _, body = await _request(server.port, "POST", "/api/run/stream", _RUN_BODY)
            assert b"event: error" in body
            assert b"upstream exploded" in body
            assert web._metrics.runs_started == before_started + 1
            assert web._metrics.runs_failed == before_failed + 1
            assert web._metrics.runs_completed == before_completed
            assert web._metrics.runs_aborted == before_aborted
            assert _FailingRunner.last.calls == 1
        finally:
            await server.close()

    asyncio.run(run())


# ── Streaming cancellation ───────────────────────────────────────────────────


def test_heartbeat_emits_until_task_done():
    async def run():
        async def work():
            await asyncio.sleep(0.35)
            return 42

        task = asyncio.create_task(work())
        pings = []
        async for ping in web._heartbeat_until_done(task, 0.1):
            pings.append(ping)
        return task.result(), pings

    result, pings = asyncio.run(run())
    assert result == 42
    assert len(pings) >= 2
    assert set(pings) == {": ping\n\n"}


def test_stream_run_aborts_on_disconnect(monkeypatch):
    monkeypatch.setattr(web, "TestRunner", _FakeRunner)
    _FakeRunner.delay = 0.05

    async def run():
        server = await _start_server()
        try:
            before_started = web._metrics.runs_started
            before_completed = web._metrics.runs_completed
            before_aborted = web._metrics.runs_aborted
            before_failed = web._metrics.runs_failed
            before_disconnects = web._metrics.client_disconnects
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            payload = _RUN_BODY.encode("utf-8")
            head = (
                "POST /api/run/stream HTTP/1.1\r\n"
                "Host: localhost\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "\r\n"
            ).encode("latin-1")
            writer.write(head + payload)
            await writer.drain()
            await _read_until(reader, b"event: test_start")

            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass

            for _ in range(200):
                if web._metrics.runs_aborted == before_aborted + 1:
                    break
                await asyncio.sleep(0.01)
            assert web._metrics.runs_aborted == before_aborted + 1
            assert web._metrics.runs_started == before_started + 1
            assert web._metrics.runs_completed == before_completed
            assert web._metrics.runs_failed == before_failed
            assert web._metrics.client_disconnects == before_disconnects + 1

            calls = _FakeRunner.last.calls
            await asyncio.sleep(0.3)
            assert _FakeRunner.last.calls == calls
        finally:
            await server.close()

    asyncio.run(run())
