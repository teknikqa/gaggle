# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project bootstrapped as a gas-only sibling of
  [`haggle`](https://github.com/NaanyaBiz/haggle) (electricity), ported from
  `haggle` commit `04ebc21b53315ec9b176b71c2abfbe69d80ce8d7`: Auth0 PKCE auth
  flow, refresh-token rotation, TLS Trust-On-First-Use pinning, and contract
  discovery (`gasContract` filtering).
- Solar and Time-of-Use code paths removed (not applicable to gas).
- **Real gas usage data implemented**, confirmed against a live AGL gas
  account capture (Phase 0, 2026-07-30 — see `docs/gas-api.md`):
  `AglClient.async_get_gas_usage_basic` calls the confirmed real endpoint
  (`GET /v2/usage/basic/Gas/{contractNumber}`), which turned out to be
  fundamentally different from the sibling electricity integration's
  interval-fetch shape — a basic (non-smart) gas meter has no interval or
  daily data at all.
- New sensors: current billing-period usage/cost (AGL's own estimate),
  bill projection, cumulative usage/cost, unit rate, supply charge (7
  total). Unit rate reads the highest tier of AGL's confirmed
  tiered/block `c/MJ` gas pricing as a documented simplification.
- `gaggle:consumption_<contract>` / `gaggle:cost_<contract>` Energy
  dashboard statistics now import real data: one sparse point per
  completed billing period (~bimonthly), not hourly/daily — there's no
  underlying interval data for a basic gas meter to build a smoother chart
  from. Baseline continuity is preserved across polls even as AGL's
  returned window of past periods ages older periods out (regression test
  against the real HA recorder, not mocked).
- Coordinator rewritten: replaced the sibling electricity integration's
  per-day throttled backfill/rewindow loop with a single usage-summary
  call per poll (AGL returns the whole current-period-plus-history window
  in one shot for this meter type).

### Removed

- The per-day backfill/rewindow machinery, `IntervalReading`/`DailyReading`/
  `BillPeriod` models, and `parse_interval_readings`/`parse_daily_readings`/
  `parse_bill_period` parsers — all modeled a shape that turned out not to
  apply to gas. `GasUsageSummary`/`GasPastPeriod` and `parse_gas_usage_basic`
  replace them with the confirmed real shape.
