#!/usr/bin/env python3
"""Verify per-format CLI transport defaults and explicit overrides."""

from __future__ import annotations

import sys

from llm_comply.cli import _build_parser
from llm_comply.config import ComplianceConfig

BASE = ("-u", "https://example.test", "-k", "test-key")


def _config(*argv: str) -> ComplianceConfig:
    return ComplianceConfig.from_args(_build_parser().parse_args(list(argv)))


def main() -> int:
    """Check auth headers, bearer prefixes, and extra headers per format."""
    cfg = _config("--format", "messages", *BASE)
    assert cfg.auth_header == "x-api-key"
    assert not cfg.use_bearer_prefix
    assert cfg.extra_headers == {"anthropic-version": "2023-06-01"}

    for fmt in ("google_generate", "google_interactions"):
        cfg = _config("--format", fmt, *BASE)
        assert cfg.auth_header == "x-goog-api-key", fmt
        assert not cfg.use_bearer_prefix, fmt
        assert cfg.extra_headers is None, fmt

    for fmt in ("open_responses", "openai_responses", "chat_completions"):
        cfg = _config("--format", fmt, *BASE)
        assert cfg.auth_header == "Authorization", fmt
        assert cfg.use_bearer_prefix, fmt
        assert cfg.extra_headers is None, fmt

    # Explicit flags override the format defaults.
    cfg = _config("--format", "messages", "--auth-header", "Authorization", *BASE)
    assert cfg.auth_header == "Authorization"
    assert not cfg.use_bearer_prefix

    cfg = _config("--format", "open_responses", "--no-bearer", *BASE)
    assert cfg.auth_header == "Authorization"
    assert not cfg.use_bearer_prefix

    # User headers override per-format defaults.
    cfg = _config("--format", "messages", "-H", "anthropic-version:2024-01-01", *BASE)
    assert cfg.extra_headers == {"anthropic-version": "2024-01-01"}

    # Legacy aliases resolve to the canonical format defaults.
    cfg = _config("--format", "anthropic", *BASE)
    assert cfg.auth_header == "x-api-key"
    assert not cfg.use_bearer_prefix

    print("CLI format defaults: auth headers, bearer, and extra headers OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
