"""Domain dataclasses for the AGL API layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import date, datetime


@dataclass(slots=True)
class TokenSet:
    """Holds a live access token + the current (rotated) refresh token."""

    access_token: str
    refresh_token: str  # MUST be persisted after every rotation
    expires_at: datetime  # UTC; derived from `expires_in`
    id_token: str = ""  # for identity claims if needed


@dataclass(slots=True)
class Contract:
    """One fuel/service contract from /api/v3/overview."""

    contract_number: str
    account_number: str
    address: str
    fuel_type: str  # "electricityContract" | "gasContract"
    status: str  # "active" | ...
    meter_type: str = "smart"


@dataclass(slots=True)
class GasPastPeriod:
    """One already-billed period from usage.basic.Gas's pastUsage.items[].

    Real, actual meter-read-derived totals (not an estimate) — confirmed
    against the maintainer's own AGL account, 2026-07-30 (Phase 0, see
    docs/gas-api.md). Used to seed the gaggle:* statistics import — one
    point per completed billing period, sparse (~bimonthly), NOT a daily
    or hourly series (no such data exists for a basic gas meter).
    """

    start: date
    end: date
    usage_mj: float  # consumption.usageQuantity
    cost_aud: float  # consumption.usageAmount


@dataclass(slots=True)
class GasUsageSummary:
    """Full response from GET /v2/usage/basic/Gas/{contractNumber}.

    Confirmed real shape (Phase 0, 2026-07-30) — NOT the interval/hourly
    shape the sibling electricity integration uses. A basic gas meter has
    no interval data at all: the current period is an estimate + a
    projection (both figures, not readings), and ``past_periods`` is the
    only source of real historical totals.
    """

    period_start: date
    period_end: date
    current_day: int  # billPeriod.currentDay
    max_days_in_period: int  # billPeriod.maximumDaysInPeriod
    cost_so_far_aud: float  # billPeriod.usage.amount ("$" stripped)
    usage_so_far_mj: float  # billPeriod.usage.quantity (" MJ" stripped)
    projection_aud: float  # billPeriod.projection.amount ("$" stripped)
    past_periods: list[GasPastPeriod] = field(default_factory=list)


@dataclass(slots=True)
class PlanRates:
    """Plan rates from /api/v2/plan/energy/{contractNumber} (fuel-agnostic)."""

    product_name: str
    unit_rates: list[dict[str, Any]] = field(default_factory=list)
    supply_charge_cents_per_day: float = 0.0
