"""CLI entry point for llm-compliance."""

from __future__ import annotations

import argparse
import sys

from llm_comply import __version__
from llm_comply.formats import (
    DEFAULT_FORMAT,
    FORMAT_ALIASES,
    FORMATS,
    REFRESHABLE_CHOICES,
    REFRESHABLE_FORMATS,
    VALIDATION_SPEC_FILES,
    normalize_format,
)
from llm_comply.tests import get_tests as _get_tests


_FORMAT_CHOICES = FORMATS + tuple(FORMAT_ALIASES)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-comply",
        description="LLM API compliance tester",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command")

    # -- run (default) --
    run_parser = sub.add_parser("run", help="Run compliance tests (default)")
    _add_run_args(run_parser)

    # -- list --
    sub.add_parser("list", help="List available test IDs")

    # -- update-spec --
    update_parser = sub.add_parser(
        "update-spec", help="Fetch the latest upstream OpenAPI spec"
    )
    update_parser.add_argument(
        "--format",
        choices=REFRESHABLE_CHOICES,
        default=DEFAULT_FORMAT,
        dest="api_format",
        metavar="FORMAT",
        help=(
            "API format whose bundled spec to refresh: "
            f"{', '.join(REFRESHABLE_FORMATS)} (default: {DEFAULT_FORMAT})"
        ),
    )
    update_parser.add_argument(
        "--all",
        action="store_true",
        dest="specs_all",
        help="Refresh every format that has an upstream source",
    )

    # -- specs --
    specs_parser = sub.add_parser(
        "specs", help="Show bundled spec versions and validation modes"
    )
    specs_parser.add_argument(
        "--json",
        action="store_true",
        dest="specs_json",
        help="Print the raw spec manifest as JSON",
    )
    specs_parser.add_argument(
        "--check",
        action="store_true",
        dest="specs_check",
        help="Exit non-zero if the manifest is stale",
    )

    # Also allow run args on the top-level parser (default command)
    _add_run_args(parser)

    return parser


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-u", "--base-url", help="API base URL (e.g. http://localhost:8000/v1)"
    )
    parser.add_argument(
        "-k",
        "--api-key",
        help="API key (or set OPENRESPONSES_API_KEY env var)",
    )
    parser.add_argument(
        "-m", "--model", default="gpt-4o-mini", help="Model name (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--auth-header",
        default="Authorization",
        help="Auth header name (default: Authorization)",
    )
    parser.add_argument(
        "--no-bearer",
        action="store_true",
        help="Don't prepend 'Bearer ' to API key",
    )
    parser.add_argument(
        "-f",
        "--filter",
        help="Comma-separated test IDs to run",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show request/response on failure"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay in seconds between tests (default: 0, useful for rate-limited APIs)",
    )
    parser.add_argument("--spec", help="Path to custom OpenAPI spec JSON")
    parser.add_argument(
        "--format",
        choices=_FORMAT_CHOICES,
        default=DEFAULT_FORMAT,
        dest="api_format",
        metavar="FORMAT",
        help=(
            f"API format to test (default: {DEFAULT_FORMAT}); legacy aliases accepted"
        ),
    )
    parser.add_argument(
        "-i",
        "--ignore",
        help="Comma-separated substrings to ignore in errors (e.g. refusal,verbosity)",
    )
    parser.add_argument(
        "-H",
        "--header",
        help="Extra headers as key:value pairs (e.g. anthropic-version:2023-06-01)",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_tests", help="List available test IDs"
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Start the web UI server instead of running CLI tests",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8090,
        help="Port for web UI server (default: 8090)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for web UI server (default: 127.0.0.1)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "web", False):
        return _cmd_web(args)

    # Route subcommands
    fmt = normalize_format(getattr(args, "api_format", DEFAULT_FORMAT))
    if args.command == "list" or getattr(args, "list_tests", False):
        return _cmd_list(fmt)

    if args.command == "specs":
        return _cmd_specs(args)

    if args.command == "update-spec":
        return _cmd_update_spec(fmt, getattr(args, "specs_all", False))

    # Default: run tests
    return _cmd_run(args, parser)


def _cmd_web(args: argparse.Namespace) -> int:
    from .web import app

    print(f"llm-comply web UI v{__version__}")
    print(f"Open http://{args.host}:{args.port} in your browser")
    app.run(host=args.host, port=args.port)
    return 0


def _cmd_list(fmt: str) -> int:
    tests = _get_tests(fmt)
    print(f"\nAvailable compliance tests ({fmt}):\n")
    max_id = max(len(tc.id) for tc in tests)
    for tc in tests:
        stream = " [streaming]" if tc.streaming else ""
        print(f"  {tc.id:<{max_id}}  {tc.name}{stream}")
        print(f"  {'':<{max_id}}  {tc.description}")
        print()
    return 0


def _cmd_update_spec(fmt: str, refresh_all: bool = False) -> int:
    from .formats import REFRESHABLE_FORMATS
    from .schema import SpecLoader

    targets = REFRESHABLE_FORMATS if refresh_all else (fmt,)
    failures = 0
    for target in targets:
        try:
            print(SpecLoader.fetch_latest(target))
        except Exception as exc:
            failures += 1
            print(f"Error fetching {target} spec: {exc}", file=sys.stderr)
    return 1 if failures else 0


def _cmd_specs(args: argparse.Namespace) -> int:
    import json as json_module

    from .schema import SpecLoader

    if getattr(args, "specs_check", False):
        problems = SpecLoader.check_manifest()
        if problems:
            print("Spec manifest is stale:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            print(
                "Refresh with 'llm-comply update-spec --format <fmt>', "
                "or regenerate the manifest with SpecLoader.write_manifest().",
                file=sys.stderr,
            )
            return 1
        print("Spec manifest matches the bundled specs.")
        return 0

    manifest = SpecLoader.load_manifest()
    if not manifest.get("formats"):
        manifest = SpecLoader.assemble_manifest()
    if getattr(args, "specs_json", False):
        print(json_module.dumps(manifest, indent=2))
        return 0

    headers = (
        "Format",
        "Spec version",
        "Schemas",
        "Validation",
        "Source",
        "Refreshed",
    )
    rows = [
        (
            fmt,
            entry.get("spec_version") or "-",
            str(entry.get("schema_count", 0)),
            entry.get("validation", "semantic"),
            entry.get("source_type", "-"),
            entry.get("refreshed_at") or "-",
        )
        for fmt, entry in manifest["formats"].items()
    ]
    widths = [
        max([len(header), *(len(row[i]) for row in rows)])
        for i, header in enumerate(headers)
    ]
    print("  ".join(header.ljust(w) for header, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))

    notes = [
        (fmt, entry["note"])
        for fmt, entry in manifest["formats"].items()
        if entry.get("note")
    ]
    if notes:
        print()
        for fmt, note in notes:
            print(f"  {fmt}: {note}")

    print()
    print(f"Manifest: {SpecLoader.manifest_path()}")
    return 0


def _cmd_run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not getattr(args, "base_url", None):
        parser.error("--base-url is required")

    import os
    import pathlib

    api_key = getattr(args, "api_key", None) or os.environ.get(
        "OPENRESPONSES_API_KEY", ""
    )
    if not api_key:
        parser.error("--api-key is required (or set OPENRESPONSES_API_KEY env var)")

    from .config import ComplianceConfig
    from .display import get_display
    from .runner import TestRunner
    from .schema import SpecLoader

    fmt = normalize_format(getattr(args, "api_format", DEFAULT_FORMAT))
    tests = _get_tests(fmt)

    # Resolve spec path: explicit > format-specific bundled > None (no schema)
    spec_path = getattr(args, "spec", None)
    if not spec_path:
        spec_file = VALIDATION_SPEC_FILES.get(fmt)
        if spec_file:
            spec_dir = pathlib.Path(__file__).parent / "specs"
            spec_path = str(spec_dir / spec_file)

    config = ComplianceConfig.from_args(args)
    spec = SpecLoader(spec_path)
    display = get_display(
        json_output=config.json_output,
    )

    display.print_header(config, spec.spec_version)

    runner = TestRunner(
        config=config,
        test_cases=tests,
        spec_loader=spec,
        on_result=lambda r: display.print_result(r, verbose=config.verbose),
    )

    suite = runner.run_all()
    display.print_summary(suite)

    return 1 if suite.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
