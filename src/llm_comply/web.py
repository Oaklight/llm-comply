"""llm-comply web UI server — single HTML file, vendored httpserver."""

from __future__ import annotations

import json
import pathlib
import time
from typing import Any

from llm_comply._vendor.httpserver import App, JSONResponse, Response
from llm_comply.config import ComplianceConfig
from llm_comply.http import make_request
from llm_comply.schema import SpecLoader
from llm_comply.test_case import TestCase, ValidatorContext

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


def _get_tests(fmt: str) -> list[TestCase]:
    if fmt == "openai-chat":
        from llm_comply.tests.openai_chat import OPENAI_CHAT_TESTS

        return OPENAI_CHAT_TESTS
    if fmt == "anthropic":
        from llm_comply.tests.anthropic import ANTHROPIC_TESTS

        return ANTHROPIC_TESTS
    if fmt == "google-genai":
        from llm_comply.tests.google_genai import GOOGLE_GENAI_TESTS

        return GOOGLE_GENAI_TESTS
    if fmt == "google-interactions":
        from llm_comply.tests.google_interactions import GOOGLE_INTERACTIONS_TESTS

        return GOOGLE_INTERACTIONS_TESTS
    from llm_comply.tests.open_responses import OPEN_RESPONSES_TESTS

    return OPEN_RESPONSES_TESTS


def _get_spec(fmt: str) -> SpecLoader:
    spec_file = FORMATS.get(fmt)
    if spec_file:
        specs_dir = pathlib.Path(__file__).parent / "specs"
        return SpecLoader(str(specs_dir / spec_file))
    return SpecLoader(None)


def _run_single_test(
    tc: TestCase,
    config: ComplianceConfig,
    spec: SpecLoader,
    ignore_list: list[str] | None,
) -> dict[str, Any]:
    if tc.skip_reason:
        reason = tc.skip_reason(config)
        if reason:
            return {
                "id": tc.id,
                "name": tc.name,
                "status": "skipped",
                "duration_ms": 0,
                "errors": [reason],
            }

    errors: list[str] = []
    request_body: dict[str, Any] = {}
    response_data: Any = None
    start = time.monotonic()

    try:
        request_body = tc.build_request(config)
        endpoint = request_body.pop("_google_endpoint", None) or tc.endpoint
        status_code, response_data, sse_events = make_request(
            config,
            endpoint,
            request_body,
            streaming=tc.streaming,
        )

        if status_code not in tc.expected_statuses:
            errors.append(f"HTTP {status_code} (expected {tc.expected_statuses})")

        if tc.schema_name and isinstance(response_data, dict) and not errors:
            errors.extend(spec.validate(response_data, tc.schema_name))

        if tc.streaming and tc.validate_stream_events and sse_events:
            for event in sse_events:
                etype = event.get("type", "")
                edata = event.get("data")
                if etype == "[DONE]" or not isinstance(edata, dict):
                    continue
                errors.extend(spec.validate_sse_event(etype, edata))

        ctx = ValidatorContext(streaming=tc.streaming, sse_events=sse_events)
        for validator in tc.validators:
            errors.extend(validator(response_data, ctx))

    except Exception as exc:
        errors.append(f"exception: {exc}")

    elapsed = (time.monotonic() - start) * 1000.0

    if errors and ignore_list:
        errors = [e for e in errors if not any(pat in e for pat in ignore_list)]

    _WARNING_PREFIX = "[warning] "
    warnings = [
        e[len(_WARNING_PREFIX) :] for e in errors if e.startswith(_WARNING_PREFIX)
    ]
    errors = [e for e in errors if not e.startswith(_WARNING_PREFIX)]

    status = "passed" if not errors else "failed"

    result: dict[str, Any] = {
        "id": tc.id,
        "name": tc.name,
        "status": status,
        "duration_ms": round(elapsed, 1),
        "errors": errors,
        "streaming": tc.streaming,
    }
    if warnings:
        result["warnings"] = warnings
    if status == "failed" and request_body:
        req_str = json.dumps(request_body, ensure_ascii=False)
        result["request"] = req_str[:800] if len(req_str) > 800 else req_str
    if status == "failed" and isinstance(response_data, dict):
        resp_str = json.dumps(response_data, ensure_ascii=False)
        result["response"] = resp_str[:800] if len(resp_str) > 800 else resp_str

    return result


app = App()


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
    tests = _get_tests(fmt)
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
    body = request.json()
    fmt = body.get("format", "open-responses")
    base_url = body.get("base_url", "").rstrip("/")
    api_key = body.get("api_key", "")
    model = body.get("model", "gpt-4o-mini")
    auth_header = body.get("auth_header", "Authorization")
    use_bearer = body.get("use_bearer", True)
    ignore_str = body.get("ignore", "")
    test_id = body.get("test_id")

    if not base_url or not api_key:
        return JSONResponse(
            {"error": "base_url and api_key are required"}, status_code=400
        )

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
    )

    tests = _get_tests(fmt)
    spec = _get_spec(fmt)

    if test_id:
        tc = next((t for t in tests if t.id == test_id), None)
        if not tc:
            return JSONResponse({"error": f"test {test_id} not found"}, status_code=404)
        result = _run_single_test(tc, config, spec, ignore_list)
        return JSONResponse(result)

    results = []
    for tc in tests:
        results.append(_run_single_test(tc, config, spec, ignore_list))
    return JSONResponse(results)


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
