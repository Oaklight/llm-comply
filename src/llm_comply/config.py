"""Compliance test configuration."""

from __future__ import annotations

import argparse
import dataclasses
import os


@dataclasses.dataclass(frozen=True)
class ComplianceConfig:
    """Configuration for a compliance test run."""

    base_url: str
    api_key: str
    model: str = "gpt-4o-mini"
    auth_header: str = "Authorization"
    use_bearer_prefix: bool = True
    filter_ids: list[str] | None = None
    verbose: bool = False
    json_output: bool = False
    timeout: float = 60.0
    spec_path: str | None = None
    ignore_errors: list[str] | None = None
    extra_headers: dict[str, str] | None = None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> ComplianceConfig:
        """Build from parsed argparse namespace."""
        api_key = getattr(args, "api_key", None) or os.environ.get(
            "OPENRESPONSES_API_KEY", ""
        )
        filter_ids = None
        raw_filter: str | None = getattr(args, "filter", None)
        if raw_filter:
            filter_ids = [s.strip() for s in raw_filter.split(",") if s.strip()]

        ignore_errors = None
        raw_ignore: str | None = getattr(args, "ignore", None)
        if raw_ignore:
            ignore_errors = [s.strip() for s in raw_ignore.split(",") if s.strip()]

        extra_headers: dict[str, str] | None = None
        raw_headers: str | None = getattr(args, "header", None)
        if raw_headers:
            extra_headers = {}
            for h in raw_headers.split(","):
                if ":" in h:
                    k, v = h.split(":", 1)
                    extra_headers[k.strip()] = v.strip()

        base_url: str = args.base_url
        return cls(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=getattr(args, "model", "gpt-4o-mini"),
            auth_header=getattr(args, "auth_header", "Authorization"),
            use_bearer_prefix=not getattr(args, "no_bearer", False),
            filter_ids=filter_ids,
            verbose=getattr(args, "verbose", False),
            json_output=getattr(args, "json", False),
            timeout=getattr(args, "timeout", 60.0),
            spec_path=getattr(args, "spec", None),
            ignore_errors=ignore_errors,
            extra_headers=extra_headers,
        )

    @property
    def auth_value(self) -> str:
        if self.use_bearer_prefix:
            return f"Bearer {self.api_key}"
        return self.api_key
