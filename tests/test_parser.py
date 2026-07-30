"""Tests for custom_components/gaggle/agl/parser.py."""

from __future__ import annotations

import json
import pathlib
from datetime import date

import pytest

from custom_components.gaggle.agl.models import (
    Contract,
    GasPastPeriod,
    GasUsageSummary,
    PlanRates,
)
from custom_components.gaggle.agl.parser import (
    parse_gas_usage_basic,
    parse_overview,
    parse_plan,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# Numeric guard (SAST-008)
# ---------------------------------------------------------------------------


class TestSafeFloat:
    """Adversarial / corrupt API values must clamp to 0.0 instead of poisoning stats."""

    def test_finite_positive_passes_through(self) -> None:
        from custom_components.gaggle.agl.parser import _safe_float

        assert _safe_float(0.5) == 0.5
        assert _safe_float("12.34") == pytest.approx(12.34)

    def test_inf_nan_negative_clamp_to_zero(self) -> None:
        from custom_components.gaggle.agl.parser import _safe_float

        assert _safe_float(float("inf")) == 0.0
        assert _safe_float(float("nan")) == 0.0
        assert _safe_float(-1.0) == 0.0
        assert _safe_float("1e308") == pytest.approx(1e308)  # finite, allowed
        assert _safe_float(1e400) == 0.0  # overflow → inf → clamped

    def test_unparseable_clamps_to_zero(self) -> None:
        from custom_components.gaggle.agl.parser import _safe_float

        assert _safe_float(None) == 0.0
        assert _safe_float("not a number") == 0.0
        assert _safe_float({}) == 0.0


# ---------------------------------------------------------------------------
# parse_plan allowlist (SAST-007)
# ---------------------------------------------------------------------------


class TestParsePlanAllowlist:
    """Open-schema dict(rate) is gone — only four documented keys propagate."""

    def test_only_known_keys_land_in_unit_rates(self) -> None:
        data = {
            "productName": "Smart Saver",
            "gstInclusiveRates": [
                {
                    "kind": "detail",
                    "type": "c/kWh",
                    "title": "Peak",
                    "price": 33.792,
                    "validTo": "9999-12-31",
                    # Attacker-injected keys must NOT propagate.
                    "evil_callback": "https://attacker.example/x",
                    "__proto__": "polluted",
                }
            ],
        }
        plan = parse_plan(data)
        assert len(plan.unit_rates) == 1
        rate = plan.unit_rates[0]
        assert set(rate.keys()) == {"kind", "type", "title", "price"}
        assert "evil_callback" not in rate
        assert "validTo" not in rate

    def test_extreme_price_clamped_to_zero(self) -> None:
        data = {
            "productName": "Smart Saver",
            "gstInclusiveRates": [
                {
                    "kind": "detail",
                    "type": "c/kWh",
                    "title": "Peak",
                    "price": float("inf"),
                }
            ],
        }
        plan = parse_plan(data)
        assert plan.unit_rates[0]["price"] == 0.0


# ---------------------------------------------------------------------------
# parse_gas_usage_basic — confirmed real shape (Phase 0, 2026-07-30)
# ---------------------------------------------------------------------------


class TestParseGasUsageBasic:
    def test_returns_gas_usage_summary_instance(self) -> None:
        data = load_fixture("gas_usage_basic_response.json")
        summary = parse_gas_usage_basic(data)
        assert isinstance(summary, GasUsageSummary)

    def test_current_period_dates(self) -> None:
        data = load_fixture("gas_usage_basic_response.json")
        summary = parse_gas_usage_basic(data)
        assert summary.period_start == date(2026, 6, 12)
        assert summary.period_end == date(2026, 8, 14)

    def test_current_period_day_counters(self) -> None:
        data = load_fixture("gas_usage_basic_response.json")
        summary = parse_gas_usage_basic(data)
        assert summary.current_day == 48
        assert summary.max_days_in_period == 64

    def test_current_period_estimate_parsed_from_labels(self) -> None:
        """cost/usage-so-far only exist as formatted labels ('$159.20',
        '3441.21 MJ') in the real response — no numeric sibling field."""
        data = load_fixture("gas_usage_basic_response.json")
        summary = parse_gas_usage_basic(data)
        assert summary.cost_so_far_aud == pytest.approx(159.20)
        assert summary.usage_so_far_mj == pytest.approx(3441.21)

    def test_projection_amount_parsed(self) -> None:
        data = load_fixture("gas_usage_basic_response.json")
        summary = parse_gas_usage_basic(data)
        assert summary.projection_aud == pytest.approx(211.60)

    def test_past_periods_count_and_order_independence(self) -> None:
        """Fixture has 5 past periods; parser doesn't need to sort them."""
        data = load_fixture("gas_usage_basic_response.json")
        summary = parse_gas_usage_basic(data)
        assert len(summary.past_periods) == 5
        assert all(isinstance(p, GasPastPeriod) for p in summary.past_periods)

    def test_past_period_uses_numeric_fields_not_formatted_strings(self) -> None:
        """usage_mj/cost_aud must come from usageQuantity/usageAmount (clean
        floats), not the formatted quantity/amount display strings ("2,523
        MJ" / "$98.25") which would need fragile comma/unit stripping."""
        data = load_fixture("gas_usage_basic_response.json")
        summary = parse_gas_usage_basic(data)
        most_recent = max(summary.past_periods, key=lambda p: p.start)
        assert most_recent.start == date(2026, 4, 16)
        assert most_recent.end == date(2026, 6, 11)
        assert most_recent.usage_mj == pytest.approx(2523.0)
        assert most_recent.cost_aud == pytest.approx(98.252)

    def test_empty_response_degrades_to_today_and_no_periods(self) -> None:
        from datetime import UTC, datetime as _dt

        summary = parse_gas_usage_basic({})
        today = _dt.now(UTC).date()
        assert summary.period_start == today
        assert summary.period_end == today
        assert summary.current_day == 0
        assert summary.max_days_in_period == 0
        assert summary.cost_so_far_aud == 0.0
        assert summary.usage_so_far_mj == 0.0
        assert summary.projection_aud == 0.0
        assert summary.past_periods == []

    def test_blank_projection_quantity_degrades_to_zero(self) -> None:
        """Real AGL response has projection.quantity == "" (empty string) —
        must not crash and must degrade to 0.0."""
        data = {
            "billPeriod": {
                "start": {"date": "2026-06-12"},
                "end": {"date": "2026-08-14"},
                "usage": {"amount": "$1.00", "quantity": "1 MJ"},
                "projection": {"amount": "$2.00", "quantity": ""},
            }
        }
        summary = parse_gas_usage_basic(data)
        assert summary.projection_aud == pytest.approx(2.00)

    def test_past_period_missing_dates_is_dropped(self) -> None:
        data = {
            "pastUsage": {
                "items": [
                    {
                        "start": {"date": "not-a-date"},
                        "end": {"date": "2026-06-11"},
                        "consumption": {"usageQuantity": 1.0, "usageAmount": 1.0},
                    },
                    {
                        "start": {"date": "2026-04-16"},
                        "end": {"date": "2026-06-11"},
                        "consumption": {"usageQuantity": 2.0, "usageAmount": 2.0},
                    },
                ]
            }
        }
        summary = parse_gas_usage_basic(data)
        assert len(summary.past_periods) == 1
        assert summary.past_periods[0].usage_mj == 2.0


# ---------------------------------------------------------------------------
# parse_overview
# ---------------------------------------------------------------------------


class TestParseOverview:
    def test_extracts_contracts(self) -> None:
        data = load_fixture("overview_response.json")
        contracts = parse_overview(data)
        assert len(contracts) == 1

    def test_contract_fields(self) -> None:
        data = load_fixture("overview_response.json")
        contracts = parse_overview(data)
        c = contracts[0]
        assert isinstance(c, Contract)
        assert c.contract_number == "9999999999"
        assert c.account_number == "1234567890"
        assert c.address == "1 Sample Street SUBURB QLD 4000"
        assert c.fuel_type == "electricityContract"
        assert c.status == "active"
        assert c.meter_type == "smart"

    def test_empty_accounts_returns_empty(self) -> None:
        contracts = parse_overview({"accounts": []})
        assert contracts == []

    def test_multiple_contracts_in_one_account(self) -> None:
        data = {
            "accounts": [
                {
                    "accountNumber": "ACC1",
                    "address": "1 Test St",
                    "contracts": [
                        {
                            "contractNumber": "C1",
                            "type": "electricityContract",
                            "status": "active",
                            "meterType": "smart",
                        },
                        {
                            "contractNumber": "C2",
                            "type": "gasContract",
                            "status": "active",
                            "meterType": "basic",
                        },
                    ],
                }
            ]
        }
        contracts = parse_overview(data)
        assert len(contracts) == 2
        assert {c.contract_number for c in contracts} == {"C1", "C2"}
        assert all(c.account_number == "ACC1" for c in contracts)


# ---------------------------------------------------------------------------
# parse_plan
# ---------------------------------------------------------------------------


class TestParsePlan:
    def test_returns_plan_rates_instance(self) -> None:
        data = load_fixture("plan_response.json")
        plan = parse_plan(data)
        assert isinstance(plan, PlanRates)

    def test_product_name(self) -> None:
        data = load_fixture("plan_response.json")
        plan = parse_plan(data)
        assert plan.product_name == "Smart Saver"

    def test_supply_charge(self) -> None:
        data = load_fixture("plan_response.json")
        plan = parse_plan(data)
        assert plan.supply_charge_cents_per_day == pytest.approx(131.714)

    def test_unit_rates_contain_c_kwh_entries(self) -> None:
        data = load_fixture("plan_response.json")
        plan = parse_plan(data)
        kwh_rates = [r for r in plan.unit_rates if r.get("type") == "c/kWh"]
        assert len(kwh_rates) == 2
        for r in kwh_rates:
            assert r["price"] == pytest.approx(33.792)

    def test_header_entries_excluded_from_unit_rates(self) -> None:
        """kind='header' rows must not appear in unit_rates."""
        data = load_fixture("plan_response.json")
        plan = parse_plan(data)
        assert all(r.get("kind") != "header" for r in plan.unit_rates)

    def test_empty_rates_list(self) -> None:
        plan = parse_plan({"productName": "Test", "gstInclusiveRates": []})
        assert plan.product_name == "Test"
        assert plan.unit_rates == []
        assert plan.supply_charge_cents_per_day == 0.0


class TestParsePlanGasTiered:
    """Real confirmed gas plan (Phase 0, 2026-07-30): tiered/block c/MJ
    pricing, not one flat rate like the sibling electricity integration."""

    def test_supply_charge(self) -> None:
        data = load_fixture("gas_plan_response.json")
        plan = parse_plan(data)
        assert plan.supply_charge_cents_per_day == pytest.approx(79.9755)

    def test_all_three_tiers_present(self) -> None:
        data = load_fixture("gas_plan_response.json")
        plan = parse_plan(data)
        mj_rates = [r for r in plan.unit_rates if r.get("type") == "c/MJ"]
        assert len(mj_rates) == 3
        assert [r["title"] for r in mj_rates] == [
            "First 1644 MJ",
            "Next 1314 MJ",
            "Thereafter",
        ]

    def test_tier_prices_distinct(self) -> None:
        """Unlike a flat-rate plan, the three tiers must NOT collapse to one
        price — that would silently hide the tiered structure."""
        data = load_fixture("gas_plan_response.json")
        plan = parse_plan(data)
        prices = sorted(r["price"] for r in plan.unit_rates if r.get("type") == "c/MJ")
        assert prices == [
            pytest.approx(2.563),
            pytest.approx(3.7477),
            pytest.approx(3.9875),
        ]


# ---------------------------------------------------------------------------
# Totality (fuzz-enforced) — parsers must never raise on arbitrary JSON
# ---------------------------------------------------------------------------


class TestParserTotality:
    """Malformed/tampered JSON degrades to empty/default results, never raises.

    Response bodies are attacker-influenceable (TLS pinning is warn-only), so
    parser totality is a security invariant. The live enforcement is
    tests/fuzz/fuzz_parser.py; each case below is a crash class in the
    pre-hardened parser and pins the fix deterministically.
    """

    def test_gas_usage_whitespace_quantity(self) -> None:
        # Same whitespace-only-label crash class the sibling electricity
        # integration hit: "   ".split()[0] on an empty split result.
        data = {"billPeriod": {"usage": {"quantity": "   "}}}
        assert parse_gas_usage_basic(data).usage_so_far_mj == 0.0

    def test_gas_usage_numeric_quantity(self) -> None:
        # A bare JSON number where a formatted label is expected must not
        # crash on .replace()/.split().
        data = {"billPeriod": {"usage": {"quantity": 42.5}}}
        assert parse_gas_usage_basic(data).usage_so_far_mj == 0.0
        # (a bare number isn't the real shape — degrades to 0.0, not 42.5,
        # since _label_to_float expects a string; documents the behaviour
        # rather than asserting a crash)

    def test_gas_usage_non_dict_nodes(self) -> None:
        for weird in (["x"], "str", 3, {"usage": 7}, {"usage": []}):
            summary = parse_gas_usage_basic({"billPeriod": weird})
            assert summary.usage_so_far_mj == 0.0
            assert summary.cost_so_far_aud == 0.0

    def test_gas_usage_non_dict_past_periods(self) -> None:
        assert parse_gas_usage_basic({"pastUsage": {"items": 5}}).past_periods == []
        assert (
            parse_gas_usage_basic({"pastUsage": {"items": ["x", 3]}}).past_periods == []
        )

    def test_gas_usage_non_numeric_consumption_fields(self) -> None:
        data = {
            "pastUsage": {
                "items": [
                    {
                        "start": {"date": "2026-04-16"},
                        "end": {"date": "2026-06-11"},
                        "consumption": {
                            "usageQuantity": "not a number",
                            "usageAmount": None,
                        },
                    }
                ]
            }
        }
        summary = parse_gas_usage_basic(data)
        assert len(summary.past_periods) == 1
        assert summary.past_periods[0].usage_mj == 0.0
        assert summary.past_periods[0].cost_aud == 0.0

    def test_overview_malformed_contract_skipped_and_int_id_coerced(self) -> None:
        # Was KeyError on {} (missing contractNumber); junk entries crash-free.
        data = {
            "accounts": [
                "junk",
                {
                    "accountNumber": 12345,
                    "contracts": [{}, "junk", {"contractNumber": 999}],
                },
            ]
        }
        contracts = parse_overview(data)
        assert len(contracts) == 1
        assert contracts[0].contract_number == "999"
        assert contracts[0].account_number == "12345"

    def test_plan_non_dict_and_non_str_rows(self) -> None:
        # Was AttributeError: .get on non-dict rate rows.
        data = {
            "productName": 5,
            "gstInclusiveRates": ["x", {"kind": "header", "title": 7}, 3],
            "gstExclusiveRates": "nope",
        }
        plan = parse_plan(data)
        assert plan.product_name == ""
        assert plan.unit_rates == []
