"""Terminal output for compliance test results."""

from __future__ import annotations

import json
import sys
from typing import TextIO

from .config import ComplianceConfig
from .result import SuiteResult, TestResult, TestStatus


class Display:
    """Base display interface."""

    def __init__(self, out: TextIO = sys.stdout) -> None:
        self._out = out

    def print_header(self, config: ComplianceConfig, spec_version: str) -> None:
        pass

    def print_result(self, result: TestResult, verbose: bool = False) -> None:
        pass

    def print_summary(self, suite: SuiteResult) -> None:
        pass


class PlainDisplay(Display):
    """Plain text output with Unicode markers."""

    _ICONS = {
        TestStatus.PASSED: "✅",
        TestStatus.FAILED: "❌",
        TestStatus.SKIPPED: "⏭️ ",
    }

    def print_header(self, config: ComplianceConfig, spec_version: str) -> None:
        self._out.write(f"\nLLM API Compliance Test (spec v{spec_version})\n")
        self._out.write(f"Target: {config.base_url}\n")
        self._out.write(f"Model:  {config.model}\n")
        self._out.write("-" * 60 + "\n\n")

    def print_result(self, result: TestResult, verbose: bool = False) -> None:
        if result.status == TestStatus.PASSED and result.warnings:
            icon = "⚠️ "
        else:
            icon = self._ICONS.get(result.status, "?")
        duration = f" ({result.duration_ms:.0f}ms)" if result.duration_ms else ""
        self._out.write(f"  {icon} {result.name}{duration}\n")

        if result.errors and result.status != TestStatus.SKIPPED:
            for err in result.errors[:5]:
                self._out.write(f"     └─ {err}\n")
            if len(result.errors) > 5:
                self._out.write(f"     └─ ... and {len(result.errors) - 5} more\n")
        if result.warnings:
            for warn in result.warnings[:3]:
                self._out.write(f"     └─ ⚠ {warn}\n")

        if verbose and result.status == TestStatus.FAILED:
            if result.request:
                self._out.write(
                    f"     Request: {json.dumps(result.request, indent=2)[:500]}\n"
                )
            if result.response:
                resp_str = (
                    json.dumps(result.response, indent=2)
                    if isinstance(result.response, dict)
                    else str(result.response)
                )
                self._out.write(f"     Response: {resp_str[:500]}\n")

    def print_summary(self, suite: SuiteResult) -> None:
        self._out.write("\n" + "-" * 60 + "\n")
        self._out.write(f"Results: {suite.passed}/{suite.total} passed")
        if suite.failed:
            self._out.write(f", {suite.failed} failed")
        if suite.warned:
            self._out.write(f", {suite.warned} with warnings")
        if suite.skipped:
            self._out.write(f", {suite.skipped} skipped")
        self._out.write("\n\n")


class RichDisplay(Display):
    """Colored output using rich library."""

    def __init__(self, out: TextIO = sys.stdout) -> None:
        super().__init__(out)
        from rich.console import Console

        self._console = Console(file=out)

    def print_header(self, config: ComplianceConfig, spec_version: str) -> None:
        self._console.print()
        self._console.rule("[bold]LLM API Compliance Test[/bold]")
        self._console.print(f"  Spec version: [cyan]{spec_version}[/cyan]")
        self._console.print(f"  Target:       [cyan]{config.base_url}[/cyan]")
        self._console.print(f"  Model:        [cyan]{config.model}[/cyan]")
        self._console.print()

    def print_result(self, result: TestResult, verbose: bool = False) -> None:
        if result.status == TestStatus.PASSED and result.warnings:
            icon = "[yellow]✓[/yellow]"
        elif result.status == TestStatus.PASSED:
            icon = "[green]✓[/green]"
        elif result.status == TestStatus.FAILED:
            icon = "[red]✗[/red]"
        else:
            icon = "[yellow]⏭[/yellow]"

        duration = (
            f" [dim]({result.duration_ms:.0f}ms)[/dim]" if result.duration_ms else ""
        )
        self._console.print(f"  {icon} {result.name}{duration}")

        if result.errors and result.status != TestStatus.SKIPPED:
            for err in result.errors[:5]:
                self._console.print(f"     [dim]└─[/dim] [red]{err}[/red]")
            if len(result.errors) > 5:
                self._console.print(
                    f"     [dim]└─ ... and {len(result.errors) - 5} more[/dim]"
                )
        if result.warnings:
            for warn in result.warnings[:3]:
                self._console.print(f"     [dim]└─[/dim] [yellow]⚠ {warn}[/yellow]")

        if verbose and result.status == TestStatus.FAILED:
            if result.request:
                self._console.print(
                    f"     [dim]Request:[/dim] {json.dumps(result.request, indent=2)[:500]}"
                )
            if result.response:
                resp_str = (
                    json.dumps(result.response, indent=2)
                    if isinstance(result.response, dict)
                    else str(result.response)
                )
                self._console.print(f"     [dim]Response:[/dim] {resp_str[:500]}")

    def print_summary(self, suite: SuiteResult) -> None:
        self._console.print()
        if suite.failed == 0:
            style = "bold green"
            msg = f"All {suite.passed} tests passed!"
        else:
            style = "bold red"
            msg = f"{suite.passed}/{suite.total} passed, {suite.failed} failed"

        if suite.warned:
            msg += f", {suite.warned} with warnings"
        if suite.skipped:
            msg += f", {suite.skipped} skipped"

        self._console.rule(f"[{style}]{msg}[/{style}]")
        self._console.print()


class JsonDisplay(Display):
    """JSON output — collects results, dumps at the end."""

    def print_summary(self, suite: SuiteResult) -> None:
        self._out.write(json.dumps(suite.to_dict(), indent=2) + "\n")


def get_display(json_output: bool = False, out: TextIO = sys.stdout) -> Display:
    if json_output:
        return JsonDisplay(out)
    try:
        import rich  # noqa: F401

        return RichDisplay(out)
    except ImportError:
        return PlainDisplay(out)
