"""Atheris fuzz harness for custom_components/gaggle/agl/parser.py.

Threat model context (SECURITY.md): TLS pinning is warn-only by design, so
AGL response bodies are attacker-influenceable. The parsers must therefore be
TOTAL over arbitrary JSON — a parser crash is a MITM-triggerable failed poll
cycle. This harness enforces two invariants:

  1. No exception escapes any parse_* function for any json.loads() value.
  2. Every numeric field returned is finite and >= 0 (the _safe_float
     guarantee — protects the recorder's cumulative-sum statistics).

Run locally (needs the dev env for the homeassistant import chain):
    uv sync --extra dev
    uv pip install --require-hashes -r tests/fuzz/requirements.txt
    PYTHONPATH=. uv run python tests/fuzz/fuzz_parser.py tests/fixtures

CI: .github/workflows/fuzz.yml — weekly plus on parser/harness changes.
Deterministic crash regressions live in tests/test_parser.py
(TestParserTotality); add one there for every crasher this harness finds.
"""

from __future__ import annotations

import json
import math
import sys
from typing import Any

import atheris

# Instrument only the functions under test (instrument_func below):
# atheris.instrument_imports()/instrument_all() would sweep in the whole
# homeassistant import chain and make startup prohibitively slow.
from custom_components.gaggle.agl import parser

for _fn_name in (
    "parse_overview",
    "parse_gas_usage_basic",
    "parse_plan",
    "_safe_float",
    "_label_to_float",
    "_as_nonneg_int",
    "_as_dict",
    "_as_list",
    "_as_str",
    "_as_id",
):
    setattr(parser, _fn_name, atheris.instrument_func(getattr(parser, _fn_name)))


def _check_amount(value: float) -> None:
    if not math.isfinite(value):
        raise AssertionError(f"non-finite value escaped a parser: {value!r}")
    if value < 0:
        raise AssertionError(f"negative value escaped a parser: {value!r}")


def test_one_input(data: bytes) -> None:
    try:
        obj: Any = json.loads(data)
    except Exception:
        return

    summary = parser.parse_gas_usage_basic(obj)
    _check_amount(summary.cost_so_far_aud)
    _check_amount(summary.usage_so_far_mj)
    _check_amount(summary.projection_aud)
    for period in summary.past_periods:
        _check_amount(period.usage_mj)
        _check_amount(period.cost_aud)

    plan = parser.parse_plan(obj)
    _check_amount(plan.supply_charge_cents_per_day)
    for row in plan.unit_rates:
        _check_amount(row["price"])

    parser.parse_overview(obj)


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
