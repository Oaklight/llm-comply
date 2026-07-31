"""HTTP client helpers for compliance testing."""

from __future__ import annotations

import json
from typing import Any

from llm_comply._vendor.httpclient import (
    Response,
    StreamingResponse,
    post as http_post,
)
from llm_comply._vendor.sse import EventSource

from .config import ComplianceConfig
from .schema import TERMINAL_EVENTS


def make_request(
    config: ComplianceConfig,
    endpoint: str,
    body: dict[str, Any],
    streaming: bool = False,
) -> tuple[int, Any, list[dict[str, Any]] | None]:
    """Send a POST request to the compliance target.

    Returns:
        (status_code, response_body_or_final, sse_events_or_None)
    """
    url = f"{config.base_url}{endpoint}"
    headers = {
        config.auth_header: config.auth_value,
        "Content-Type": "application/json",
        "Accept-Encoding": "identity",
    }
    if config.extra_headers:
        headers.update(config.extra_headers)

    if streaming:
        return _streaming_request(url, headers, body, config.timeout)
    return _standard_request(url, headers, body, config.timeout)


def _standard_request(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
) -> tuple[int, Any, None]:
    raw = http_post(url, json=body, headers=headers, timeout=timeout)
    assert isinstance(raw, Response)
    try:
        data = raw.json()
    except Exception:
        data = raw.text
    return raw.status_code, data, None


def _streaming_request(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
) -> tuple[int, Any, list[dict[str, Any]]]:
    if "alt=sse" not in url:
        body["stream"] = True
    raw = http_post(url, json=body, headers=headers, timeout=timeout, stream=True)
    assert isinstance(raw, StreamingResponse)

    events: list[dict[str, Any]] = []
    final_response: Any = None

    with raw:
        if raw.status_code != 200:
            try:
                full = b"".join(raw.iter_bytes())
                data = json.loads(full)
            except Exception:
                data = (
                    full.decode("utf-8", errors="replace")
                    if isinstance(full, bytes)
                    else str(full)
                )
            return raw.status_code, data, events

        for sse in EventSource(raw.iter_lines()):
            if sse.data == "[DONE]":
                events.append({"type": "[DONE]", "data": "[DONE]"})
                break

            try:
                parsed = json.loads(sse.data)
            except json.JSONDecodeError:
                events.append(
                    {"type": sse.event, "data": sse.data, "_parse_error": True}
                )
                continue

            event_type = parsed.get("type", sse.event)
            events.append({"type": event_type, "data": parsed})

            if event_type in TERMINAL_EVENTS:
                final_response = parsed.get("response", parsed)

    return raw.status_code, final_response, events
