"""llm-comply web UI server — single HTML file, vendored httpserver."""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import time
from typing import Any

from llm_comply._vendor.httpserver import (
    App,
    JSONResponse,
    Response,
    StreamingResponse,
    abort,
)
from llm_comply.config import ComplianceConfig
from llm_comply.result import TestStatus
from llm_comply.runner import TestRunner
from llm_comply.schema import SpecLoader
from llm_comply.tests import get_tests

logger = logging.getLogger(__name__)

_HTML_PATH = pathlib.Path(__file__).parent / "web.html"

FORMATS = {
    "open-responses": "openresponses.json",
    "openai-chat": "openai_chat.json",
    "anthropic": "anthropic.json",
    "google-genai": None,
    "google-interactions": None,
}

EXTRA_HEADERS_MAP = {
    "anthropic": {"anthropic-version": "2023-06-01"},
}

_spec_cache: dict[str, SpecLoader] = {}


def _get_spec(fmt: str) -> SpecLoader:
    spec_file = FORMATS.get(fmt)
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
    fmt = body.get("format", "open-responses")
    base_url = body.get("base_url", "").rstrip("/")
    api_key = body.get("api_key", "")
    model = body.get("model", "gpt-4o-mini")
    auth_header = body.get("auth_header", "Authorization")
    use_bearer = body.get("use_bearer", True)
    ignore_str = body.get("ignore", "")

    if not base_url or not api_key:
        abort(400, "base_url and api_key are required")

    extra = EXTRA_HEADERS_MAP.get(fmt)
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
    return JSONResponse({"error": exc.message, "status": 400}, status_code=400)


@app.errorhandler(404)
async def handle_not_found(request, exc):
    return JSONResponse({"error": exc.message, "status": 404}, status_code=404)


@app.errorhandler(405)
async def handle_method_not_allowed(request, exc):
    return JSONResponse({"error": exc.message, "status": 405}, status_code=405)


@app.errorhandler(500)
async def handle_internal_error(request, exc):
    return JSONResponse(
        {"error": "Internal server error", "status": 500}, status_code=500
    )


@app.errorhandler(Exception)
async def handle_exception(request, exc):
    logger.exception("Unhandled exception in %s %s", request.method, request.path)
    return JSONResponse({"error": str(exc), "status": 500}, status_code=500)


# ── Middleware ────────────────────────────────────────────────────────────────

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


@app.before_request
async def handle_cors_and_timing(request):
    request.state.start_time = time.monotonic()
    if request.method == "OPTIONS":
        return Response(
            status_code=204,
            headers={**_CORS_HEADERS, "Access-Control-Max-Age": "86400"},
        )


@app.after_request
async def add_cors_and_log(request, response):
    for k, v in _CORS_HEADERS.items():
        response.headers[k] = v
    start = getattr(request.state, "start_time", None)
    if start is not None:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
    return response


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

    return JSONResponse({"status": "ok", "version": __version__})


@app.get("/api/tests")
async def list_tests(request):
    fmt = (
        request.query_params.get("format", ["open-responses"]) or ["open-responses"]
    )[0]
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


@app.post("/api/run/stream")
async def run_tests_stream(request):
    """Stream test results as SSE events."""
    _body, fmt, tests, runner = _parse_run_body(request)

    async def generate():
        passed = failed = skipped = warned = 0
        for i, tc in enumerate(tests):
            start_data = json.dumps({"id": tc.id, "name": tc.name, "index": i})
            yield f"event: test_start\ndata: {start_data}\n\n"

            result = await asyncio.to_thread(runner.run_one, tc)
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

    return StreamingResponse(generate(), content_type="text/event-stream")


def main():
    import argparse

    parser = argparse.ArgumentParser(prog="llm-comply-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    from llm_comply import __version__

    print(f"llm-comply web UI v{__version__}")
    print(f"Open http://{args.host}:{args.port} in your browser")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
