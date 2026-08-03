# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Targets for next sprint

- No open GitHub issues tracked yet — see `ROADMAP.md` for direction
  (broader meter-type validation, opportunistic; computing the actual
  marginal tiered rate instead of the documented last-tier
  simplification).

---

## [0.1.0-beta.1] - 2026-08-03

**Escaped defects closed this release:** 0.

### First-release validation (`docs/releasing.md` gate)

- Account: maintainer's own AGL gas account (basic/non-smart meter).
- Billing period reconciled: 16 April 2026 – 11 June 2026.
- Compared: gaggle's imported `gaggle:consumption_<contract>` /
  `gaggle:cost_<contract>` totals for that period against the real AGL
  bill / app for the same period.
- Result: matched within the API's own rounding.
- Checked: 30 July 2026.
- Scope note: this validates gaggle's basic-meter import path against one
  real account. Broader validation (a second account, or a smart-metered
  account) remains opportunistic — see `ROADMAP.md`.

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
- Own brand assets (`custom_components/gaggle/brand/`): a "G" mark with a
  blue gas-flame glyph and a `gaggle` wordmark, light and dark variants —
  replacing placeholder PNGs that were byte-identical to `haggle`'s H+bolt
  mark.

### Fixed

- Config flow now aborts with a clear `no_gas_contract` reason when an AGL
  account has no gas contract (or only electricity contracts), instead of
  silently creating a config entry with `contract_number=""` that "succeeds"
  at setup and then fails every subsequent poll.

### Removed

- The per-day backfill/rewindow machinery, `IntervalReading`/`DailyReading`/
  `BillPeriod` models, and `parse_interval_readings`/`parse_daily_readings`/
  `parse_bill_period` parsers — all modeled a shape that turned out not to
  apply to gas. `GasUsageSummary`/`GasPastPeriod` and `parse_gas_usage_basic`
  replace them with the confirmed real shape.
