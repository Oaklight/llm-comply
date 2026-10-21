#!/usr/bin/env python3
"""Verify checked-in schema verdict fixtures against the bundled specs.

Spec refreshes previously relied on ad-hoc differentials that were not kept.
Each entry here pins one ``(schema, instance)`` verdict, so a refresh that
flips validation for a representative payload turns CI red.
"""

from __future__ import annotations

import json
import pathlib
import sys

from llm_comply.formats import SCHEMA_VALIDATED_FORMATS, SPEC_FILES
from llm_comply.schema import SpecLoader
from llm_comply.tests import get_tests

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_PATH = ROOT / "tests/fixtures/schema_verdicts.json"
SPECS_DIR = ROOT / "src/llm_comply/specs"


def main() -> int:
    """Assert every fixture still has its recorded verdict."""
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    assert set(fixtures) <= set(SPEC_FILES), (
        f"fixtures for unknown formats: {sorted(set(fixtures) - set(SPEC_FILES))}"
    )

    covered: dict[str, set[str]] = {}
    for fmt, filename in SPEC_FILES.items():
        if filename is None:
            continue
        assert fmt in fixtures, f"{fmt}: no verdict fixtures"
        spec = SpecLoader(str(SPECS_DIR / filename))
        covered[fmt] = set()
        verdicts: set[bool] = set()
        for index, entry in enumerate(fixtures[fmt]):
            name = entry["schema"]
            assert name in spec.schema_names, f"{fmt}: unknown schema {name!r}"
            errors = spec.validate(entry["instance"], name)
            valid = not errors
            assert valid == entry["valid"], (
                f"{fmt}[{index}] {name}: expected valid={entry['valid']}, "
                f"got {errors[:3]}"
            )
            covered[fmt].add(name)
            verdicts.add(valid)
        assert True in verdicts, f"{fmt}: no valid fixture"
        assert False in verdicts, f"{fmt}: no invalid fixture"
        print(
            f"{fmt}: {len(fixtures[fmt])} verdicts across {len(covered[fmt])} schemas"
        )

    # Every schema the runner validates must have a checked-in verdict.
    for fmt in sorted(SCHEMA_VALIDATED_FORMATS):
        used = set()
        for tc in get_tests(fmt):
            if tc.schema_name:
                used.add(tc.schema_name)
            if tc.stream_schema_name:
                used.add(tc.stream_schema_name)
        missing = used - covered.get(fmt, set())
        assert not missing, f"{fmt}: no verdict fixtures for {sorted(missing)}"

    print("schema verdict fixtures match the bundled specs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
