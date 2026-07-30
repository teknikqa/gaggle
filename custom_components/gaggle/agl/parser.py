"""Parsers: AGL JSON API responses -> domain dataclasses.

Reference response shapes are mirrored under tests/fixtures/ (anonymised).
Field semantics are documented in AGENTS.md §AGL API — Key Facts.

Confirmed real shapes (Phase 0 capture, 2026-07-30, see docs/gas-api.md):

  - Contract discovery: ``GET /v3/overview`` — fuel-agnostic, unchanged from
    the sibling electricity integration.
  - Plan/rates: ``GET /v2/plan/energy/{contractNumber}`` — fuel-agnostic
    envelope; gas plans use tiered/block ``c/MJ`` pricing (multiple rows),
    not a single flat rate.
  - Gas usage: ``GET /v2/usage/basic/Gas/{contractNumber}`` — a BASIC
    (non-smart) gas meter has NO interval or daily data at all. The current
    billing period is an estimate + a projection (not a meter read); only
    ``pastUsage.items[]`` (already-billed, completed periods) carries real
    totals, at bimonthly granularity. There is no electricity-equivalent
    ``/Hourly`` shape for this endpoint — do not assume one exists for a
    smart gas meter without a capture proving it.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime
from typing import Any, cast

from .models import Contract, GasPastPeriod, GasUsageSummary, PlanRates

_LOGGER = logging.getLogger(__name__)


def _safe_float(raw: Any) -> float:
    """Coerce raw API value to a non-negative finite float.

    Treats inf/nan/negative as 0.0 with a warning, so adversarial or corrupt
    AGL responses cannot poison the recorder via async_add_external_statistics.
    """
    try:
        value = float(raw or 0.0)
    except TypeError, ValueError:
        return 0.0
    if not math.isfinite(value) or value < 0:
        _LOGGER.warning("Rejecting non-finite/negative AGL value: %r", raw)
        return 0.0
    return value


# --- totality guards -------------------------------------------------------
# AGL envelopes are dicts/lists/strings at known positions, but response
# bodies are attacker-influenceable (TLS pinning is warn-only by design), so
# every parser must be TOTAL over arbitrary JSON: malformed shapes degrade to
# empty/default results, never raise. Enforced by tests/fuzz/fuzz_parser.py
# and TestParserTotality in tests/test_parser.py.


def _as_dict(raw: Any) -> dict[str, Any]:
    """Return raw if it is a dict, else {}."""
    if isinstance(raw, dict):
        return cast("dict[str, Any]", raw)
    return {}


def _as_list(raw: Any) -> list[Any]:
    """Return raw if it is a list, else []."""
    if isinstance(raw, list):
        return raw
    return []


def _as_str(raw: Any, default: str = "") -> str:
    """Return raw if it is a str, else default."""
    return raw if isinstance(raw, str) else default


def _as_id(raw: Any) -> str:
    """Account/contract identifiers: accept str (or int, coerced), else ''."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, int) and not isinstance(raw, bool):
        return str(raw)
    return ""


def parse_overview(data: dict[str, Any]) -> list[Contract]:
    """Parse /api/v3/overview response.

    Real, already-documented AGL endpoint (not a Phase-0 guess) that returns
    every fuel contract on the account — ``type`` comes back as
    ``"electricityContract"`` or ``"gasContract"`` (both real observed
    values). Callers decide which fuel(s) they care about; gaggle's config
    flow filters to ``GAS_FUEL_TYPE`` only.

    A contract entry without a usable contractNumber is skipped — a
    malformed (or tampered) entry must drop out, not crash discovery.
    """
    contracts: list[Contract] = []
    for account_raw in _as_list(_as_dict(data).get("accounts")):
        account = _as_dict(account_raw)
        account_number = _as_id(account.get("accountNumber"))
        address = _as_str(account.get("address"))
        for c_raw in _as_list(account.get("contracts")):
            c = _as_dict(c_raw)
            contract_number = _as_id(c.get("contractNumber"))
            if not contract_number:
                continue
            contracts.append(
                Contract(
                    contract_number=contract_number,
                    account_number=account_number,
                    address=address,
                    fuel_type=_as_str(c.get("type")),
                    status=_as_str(c.get("status")),
                    meter_type=_as_str(c.get("meterType"), "smart"),
                )
            )
    return contracts


def _label_to_float(raw: Any) -> float:
    """Parse a display label ('$159.20', '3,441.21 MJ', or '') into a float.

    The current-period fields in usage.basic.Gas only carry formatted
    display strings, not a numeric sibling field (unlike past-period items,
    which have both). An empty string — seen for an in-progress period's
    projection quantity — degrades to 0.0, never crashes (fuzz-enforced,
    same class of bug as the old whitespace-only .split()[0] IndexError
    this replaces).
    """
    s = _as_str(raw).replace("$", "").replace(",", "")
    parts = s.split()
    return _safe_float(parts[0]) if parts else 0.0


def _as_nonneg_int(raw: Any) -> int:
    """Coerce to a non-negative int, else 0. bool is excluded (is-a-int)."""
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return raw
    return 0


def parse_gas_usage_basic(data: dict[str, Any]) -> GasUsageSummary:
    """Parse GET /v2/usage/basic/Gas/{contractNumber} — confirmed real shape.

    A basic (non-smart) gas meter has no interval data; this is the only
    usage endpoint that exists for one. The current period's cost/usage are
    an ESTIMATE and the bill total a PROJECTION — not real reads — so they
    are surfaced as sensor values only, never imported as statistics.
    ``past_periods`` (pastUsage.items[]) carries real, already-billed
    totals via the numeric usageAmount/usageQuantity fields (preferred over
    the sibling formatted amount/quantity display strings, which need
    string parsing and exist mainly for the app's own UI).
    """
    payload = _as_dict(data)
    bill_period = _as_dict(payload.get("billPeriod"))

    today = datetime.now(UTC).date()
    start_str = _as_str(_as_dict(bill_period.get("start")).get("date"))
    end_str = _as_str(_as_dict(bill_period.get("end")).get("date"))
    try:
        period_start = date.fromisoformat(start_str)
    except ValueError, TypeError:
        period_start = today
    try:
        period_end = date.fromisoformat(end_str)
    except ValueError, TypeError:
        period_end = today

    usage_block = _as_dict(bill_period.get("usage"))
    projection_block = _as_dict(bill_period.get("projection"))

    past_periods: list[GasPastPeriod] = []
    for item_raw in _as_list(_as_dict(payload.get("pastUsage")).get("items")):
        item = _as_dict(item_raw)
        p_start_str = _as_str(_as_dict(item.get("start")).get("date"))
        p_end_str = _as_str(_as_dict(item.get("end")).get("date"))
        try:
            p_start = date.fromisoformat(p_start_str)
            p_end = date.fromisoformat(p_end_str)
        except ValueError, TypeError:
            # No valid dates -> can't place this period on the statistics
            # timeline; drop it rather than guess.
            continue
        consumption = _as_dict(item.get("consumption"))
        past_periods.append(
            GasPastPeriod(
                start=p_start,
                end=p_end,
                usage_mj=_safe_float(consumption.get("usageQuantity")),
                cost_aud=_safe_float(consumption.get("usageAmount")),
            )
        )

    return GasUsageSummary(
        period_start=period_start,
        period_end=period_end,
        current_day=_as_nonneg_int(bill_period.get("currentDay")),
        max_days_in_period=_as_nonneg_int(bill_period.get("maximumDaysInPeriod")),
        cost_so_far_aud=_label_to_float(usage_block.get("amount")),
        usage_so_far_mj=_label_to_float(usage_block.get("quantity")),
        projection_aud=_label_to_float(projection_block.get("amount")),
        past_periods=past_periods,
    )


def parse_plan(data: dict[str, Any]) -> PlanRates:
    """Parse /api/v2/plan/energy/{contractNumber} response.

    Fuel-agnostic endpoint (works the same for electricity and gas
    contracts). Only the parts that don't require guessing a fuel-specific
    rate shape are extracted here:

    - The supply-charge row: a ``kind:"detail"``, ``type:"c/day"`` entry
      whose title contains "supply" — "c/day" is a time unit, not an energy
      unit, so this detection is fuel-agnostic and safe to keep as-is.
    - The raw, allowlisted list of rate rows (``kind``/``type``/``title``/
      ``price``) — no per-row classification is applied.

    What is deliberately NOT done here: picking a single "the" usage rate.
    Confirmed real gas plans (Phase 0, 2026-07-30) use TIERED/block pricing
    — multiple ``c/MJ`` detail rows ("First N MJ" / "Next N MJ" /
    "Thereafter"), not one flat rate like the sibling electricity
    integration's ``type == "c/kWh"`` row. Which tier is "current" depends
    on cumulative usage so far this billing period against thresholds that
    are only present as substrings of the free-text ``title`` (e.g. "First
    1644 MJ") — parsing them out is a real option for a future
    enhancement, not implemented here to avoid a fragile regex-in-title
    dependency. `coordinator.py` picks the LAST detail ``c/MJ`` row
    (typically "Thereafter") as a documented simplification; see its
    comment for the rationale and the limitation for light users who never
    reach that tier.
    """
    payload = _as_dict(data)
    product_name = _as_str(payload.get("productName"))
    unit_rates: list[dict[str, Any]] = []
    supply_charge: float = 0.0

    for rate_raw in _as_list(payload.get("gstInclusiveRates")):
        rate = _as_dict(rate_raw)
        kind = rate.get("kind")
        if kind != "detail":
            continue
        rate_type = _as_str(rate.get("type"))
        price = _safe_float(rate.get("price"))
        title = _as_str(rate.get("title"))
        if rate_type == "c/day" and "supply" in title.lower():
            supply_charge = price
        # Allowlist the four fields the coordinator actually consumes — drops
        # any extra keys an attacker-controlled (MITM) response could inject.
        unit_rates.append(
            {
                "kind": kind,
                "type": rate_type,
                "title": title,
                "price": price,
            }
        )

    return PlanRates(
        product_name=product_name,
        unit_rates=unit_rates,
        supply_charge_cents_per_day=supply_charge,
    )
