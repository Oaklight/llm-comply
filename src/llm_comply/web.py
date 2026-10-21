"""llm-comply web UI server — single HTML file, vendored httpserver."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import pathlib
import ssl
import time
from collections.abc import AsyncIterator
from typing import Any

from llm_comply._vendor.httpserver import (
    App,
    JSONResponse,
    Response,
    StreamingResponse,
    abort,
)
from llm_comply.config import ComplianceConfig
from llm_comply.formats import (
    DEFAULT_AUTH,
    DEFAULT_FORMAT,
    EXTRA_HEADERS,
    FORMAT_AUTH_DEFAULTS,
    FORMATS,
    VALIDATION_SPEC_FILES,
    normalize_format,
)
from llm_comply.result import TestStatus
from llm_comply.runner import TestRunner
from llm_comply.schema import SpecLoader
from llm_comply.tests import get_tests

logger = logging.getLogger(__name__)

_HTML_PATH = pathlib.Path(__file__).parent / "web.html"

_spec_cache: dict[str, SpecLoader] = {}

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}

# Emit an SSE comment while a test runs.  Besides keeping proxies from idling
# out, the periodic write gives the server a chance to notice that the browser
# went away so the remaining tests can be cancelled.
_STREAM_HEARTBEAT_SECONDS = 2.0


@dataclasses.dataclass
class _RunMetrics:
    """Cumulative counters exposed by ``GET /health``."""

    runs_started: int = 0
    runs_completed: int = 0
    runs_aborted: int = 0
    requests_completed: int = 0
    streaming_disconnects: int = 0

    def to_dict(self) -> dict[str, int]:
        return dataclasses.asdict(self)


_metrics = _RunMetrics()


def _add_cors(response: Response | JSONResponse) -> None:
    """Add CORS headers to a response."""
    for k, v in _CORS_HEADERS.items():
        response.headers[k] = v


def _get_spec(fmt: str) -> SpecLoader:
    spec_file = VALIDATION_SPEC_FILES.get(fmt)
    if spec_file:
        specs_dir = pathlib.Path(__file__).parent / "specs"
        return SpecLoader(str(specs_dir / spec_file))
    return SpecLoader(None)


def _result_to_dict(result, tc) -> dict[str, Any]:
    """Convert a TestResult to the dict format expected by the web UI."""
    d: dict[str, Any] = {
        "id": result.id,
        "name": result.name,
        "status": result.status.value,
        "duration_ms": round(result.duration_ms, 1),
        "errors": result.errors or [],
        "streaming": tc.streaming,
    }
    if result.warnings:
        d["warnings"] = result.warnings
    if result.status == TestStatus.FAILED:
        if result.request:
            req_str = json.dumps(result.request, ensure_ascii=False)
            d["request"] = req_str[:800] if len(req_str) > 800 else req_str
        if result.response and isinstance(result.response, dict):
            resp_str = json.dumps(result.response, ensure_ascii=False)
            d["response"] = resp_str[:800] if len(resp_str) > 800 else resp_str
    return d


def _parse_run_body(request):
    """Parse and validate the /api/run request body."""
    body = request.json()
    try:
        fmt = normalize_format(body.get("format", DEFAULT_FORMAT))
    except ValueError as exc:
        abort(400, str(exc))
    base_url = body.get("base_url", "").rstrip("/")
    api_key = body.get("api_key", "")
    model = body.get("model", "gpt-4o-mini")
    default_auth_header, default_bearer = FORMAT_AUTH_DEFAULTS.get(fmt, DEFAULT_AUTH)
    auth_header = body.get("auth_header") or default_auth_header
    use_bearer = body.get("use_bearer")
    if use_bearer is None:
        use_bearer = default_bearer
    ignore_str = body.get("ignore", "")

    if not base_url or not api_key:
        abort(400, "base_url and api_key are required")

    extra = EXTRA_HEADERS.get(fmt)
    ignore_list = (
        [s.strip() for s in ignore_str.split(",") if s.strip()] if ignore_str else None
    )

    config = ComplianceConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        auth_header=auth_header,
        use_bearer_prefix=use_bearer,
        extra_headers=extra,
        verbose=True,
        ignore_errors=ignore_list,
    )

    tests = get_tests(fmt)
    spec = _spec_cache.get(fmt) or _get_spec(fmt)
    runner = TestRunner(config=config, test_cases=tests, spec_loader=spec)

    return body, fmt, tests, runner


app = App()


# ── Error handlers ───────────────────────────────────────────────────────────


@app.errorhandler(400)
async def handle_bad_request(request, exc):
    resp = JSONResponse({"error": exc.message, "status": 400}, status_code=400)
    _add_cors(resp)
    return resp


@app.errorhandler(404)
async def handle_not_found(request, exc):
    resp = JSONResponse({"error": exc.message, "status": 404}, status_code=404)
    _add_cors(resp)
    return resp


@app.errorhandler(405)
async def handle_method_not_allowed(request, exc):
    resp = JSONResponse({"error": exc.message, "status": 405}, status_code=405)
    _add_cors(resp)
    return resp


@app.errorhandler(500)
async def handle_internal_error(request, exc):
    # Handles explicit abort(500) calls
    resp = JSONResponse(
        {"error": "Internal server error", "status": 500}, status_code=500
    )
    _add_cors(resp)
    return resp


@app.errorhandler(Exception)
async def handle_exception(request, exc):
    logger.exception("Unhandled exception in %s %s", request.method, request.path)
    resp = JSONResponse(
        {"error": "Internal server error", "status": 500}, status_code=500
    )
    _add_cors(resp)
    return resp


# ── Middleware ────────────────────────────────────────────────────────────────


@app.before_request
async def handle_cors_and_timing(request):
    request.state.start_time = time.monotonic()
    if request.method == "OPTIONS":
        logger.info("OPTIONS %s -> 204", request.path)
        return Response(
            status_code=204,
            headers={**_CORS_HEADERS, "Access-Control-Max-Age": "86400"},
        )


@app.after_request
async def add_cors(request, response):
    _add_cors(response)
    return response


# ── Response lifecycle signals ───────────────────────────────────────────────


@app.on_response_started
async def record_response_start(request, response):
    request.state.response_start = time.monotonic()


@app.on_response_completed
async def record_response_completed(request, response):
    _metrics.requests_completed += 1
    if getattr(request.state, "stream_run", False):
        _metrics.runs_completed += 1

    start = getattr(request.state, "start_time", None)
    if start is None:
        return
    now = time.monotonic()
    started = getattr(request.state, "response_start", now)
    logger.info(
        "%s %s -> %d (ttfb %.1fms, total %.1fms)",
        request.method,
        request.path,
        response.status_code,
        (started - start) * 1000,
        (now - start) * 1000,
    )


@app.on_client_disconnect
async def record_client_disconnect(request):
    _metrics.streaming_disconnects += 1
    if getattr(request.state, "stream_run", False):
        _metrics.runs_aborted += 1

    start = getattr(request.state, "start_time", None)
    elapsed_ms = (time.monotonic() - start) * 1000 if start is not None else 0.0
    logger.info(
        "%s %s client disconnected after %.1fms",
        request.method,
        request.path,
        elapsed_ms,
    )


# ── Lifecycle hooks ───────────────────────────────────────────────────────────


@app.on_startup
async def preload_specs():
    for fmt in FORMATS:
        _spec_cache[fmt] = _get_spec(fmt)
    logger.info("Preloaded specs for %d formats", len(_spec_cache))


@app.on_startup
async def log_startup():
    from llm_comply import __version__

    logger.info("llm-comply web UI v%s ready", __version__)


@app.on_shutdown
async def cleanup_resources():
    from llm_comply.http import close_client

    close_client()
    logger.info("Closed HTTP client connection pool")


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get("/")
async def index(request):
    html = _HTML_PATH.read_text(encoding="utf-8")
    return Response(body=html, content_type="text/html")


@app.get("/health")
async def health(request):
    from llm_comply import __version__

    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "metrics": _metrics.to_dict(),
        }
    )


@app.get("/api/tests")
async def list_tests(request):
    raw_fmt = (
        request.query_params.get("format", [DEFAULT_FORMAT]) or [DEFAULT_FORMAT]
    )[0]
    try:
        fmt = normalize_format(raw_fmt)
    except ValueError as exc:
        abort(400, str(exc))
    tests = get_tests(fmt)
    return JSONResponse(
        [
            {
                "id": tc.id,
                "name": tc.name,
                "description": tc.description,
                "streaming": tc.streaming,
            }
            for tc in tests
        ]
    )


@app.get("/api/specs")
async def list_specs(request):
    """Return the committed spec-target manifest."""
    manifest = SpecLoader.load_manifest()
    if not manifest.get("formats"):
        manifest = SpecLoader.assemble_manifest()
    return JSONResponse(manifest)


@app.post("/api/run")
async def run_tests(request):
    body, fmt, tests, runner = _parse_run_body(request)
    test_id = body.get("test_id")

    if test_id:
        tc = next((t for t in tests if t.id == test_id), None)
        if not tc:
            abort(404, f"test {test_id} not found")
        result = runner.run_one(tc)
        return JSONResponse(_result_to_dict(result, tc))

    results = []
    for tc in tests:
        result = runner.run_one(tc)
        results.append(_result_to_dict(result, tc))
    return JSONResponse(results)


async def _heartbeat_until_done(
    task: asyncio.Task, interval: float
) -> AsyncIterator[str]:
    """Yield SSE comments until *task* completes.

    Args:
        task: Task wrapping the blocking test run.
        interval: Seconds to wait for the task before emitting a heartbeat.

    Yields:
        ``": ping"`` SSE comment frames.
    """
    while True:
        done, _ = await asyncio.wait({task}, timeout=interval)
        if task in done:
            return
        yield ": ping\n\n"


@app.post("/api/run/stream")
async def run_tests_stream(request):
    """Stream test results as SSE events."""
    _body, fmt, tests, runner = _parse_run_body(request)

    async def generate():
        _metrics.runs_started += 1
        request.state.stream_run = True
        passed = failed = skipped = warned = 0
        for i, tc in enumerate(tests):
            start_data = json.dumps({"id": tc.id, "name": tc.name, "index": i})
            yield f"event: test_start\ndata: {start_data}\n\n"

            task = asyncio.create_task(asyncio.to_thread(runner.run_one, tc))
            try:
                async for ping in _heartbeat_until_done(
                    task, _STREAM_HEARTBEAT_SECONDS
                ):
                    yield ping
                result = task.result()
            finally:
                if not task.done():
                    # Cancelling the task cannot interrupt the worker thread,
                    # but it lets the stream close without waiting for it.
                    task.cancel()

            result_dict = _result_to_dict(result, tc)

            if result.status == TestStatus.PASSED:
                passed += 1
                if result.warnings:
                    warned += 1
            elif result.status == TestStatus.SKIPPED:
                skipped += 1
            else:
                failed += 1

            yield f"event: test_result\ndata: {json.dumps(result_dict)}\n\n"

        summary = {
            "total": len(tests),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "warned": warned,
        }
        yield f"event: suite_complete\ndata: {json.dumps(summary)}\n\n"

    return StreamingResponse(
        generate(),
        content_type="text/event-stream",
        disconnect_check_interval=_STREAM_HEARTBEAT_SECONDS,
    )


def _build_ssl_context(certfile: str, keyfile: str) -> ssl.SSLContext:
    """Build a server-side TLS context from a certificate chain and key.

    Args:
        certfile: Path to the PEM certificate chain.
        keyfile: Path to the PEM private key.

    Returns:
        A configured :class:`ssl.SSLContext` with TLS 1.2 as the minimum.

    Raises:
        OSError: If the certificate or key cannot be loaded.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    return context


def serve(
    host: str = "127.0.0.1",
    port: int = 8090,
    *,
    tls_cert: str | None = None,
    tls_key: str | None = None,
) -> None:
    """Run the web UI server, optionally terminating TLS.

    Args:
        host: Interface to bind.
        port: TCP port to bind.
        tls_cert: Path to a PEM certificate chain. Requires *tls_key*.
        tls_key: Path to the PEM private key. Requires *tls_cert*.

    Raises:
        ValueError: If only one of *tls_cert* and *tls_key* is provided.
        OSError: If the certificate or key cannot be loaded, or the address
            cannot be bound. ``ssl.SSLError`` is an ``OSError`` subclass.
    """
    if bool(tls_cert) != bool(tls_key):
        raise ValueError("tls_cert and tls_key must be provided together")

    context = None
    if tls_cert is not None and tls_key is not None:
        context = _build_ssl_context(tls_cert, tls_key)

    from llm_comply import __version__

    print(f"llm-comply web UI v{__version__}")
    scheme = "https" if tls_cert else "http"
    print(f"Open {scheme}://{host}:{port} in your browser")

    app.run(host=host, port=port, ssl_context=context)


def main():
    import argparse

    parser = argparse.ArgumentParser(prog="llm-comply-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument(
        "--tls-cert",
        metavar="PATH",
        help="PEM certificate chain (enables HTTPS)",
    )
    parser.add_argument(
        "--tls-key",
        metavar="PATH",
        help="PEM private key (required with --tls-cert)",
    )
    args = parser.parse_args()

    try:
        serve(
            host=args.host,
            port=args.port,
            tls_cert=args.tls_cert,
            tls_key=args.tls_key,
        )
    except ValueError as exc:
        parser.error(str(exc))
    except OSError as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    main()
