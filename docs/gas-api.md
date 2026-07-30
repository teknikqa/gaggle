# AGL Gas Usage API — Phase 0 (CONFIRMED, 2026-07-30)

Confirmed by a live mitmproxy capture against the project maintainer's own
AGL account (real gas contract, **basic** — i.e. non-smart — meter). See
`tests/fixtures/PROVENANCE.md` for the capture provenance/consent note.

**The endpoint does NOT mirror `haggle`'s electricity shape.** It is not
`/usage/smart/Gas/{contractNumber}/Current/Hourly?...` — guessing that
would have been wrong. The real, implemented endpoint is:

```
GET /mobile/bff/api/v2/usage/basic/Gas/{contractNumber}?isRestricted=False&unit=MJ
```

Implemented in `AglClient.async_get_gas_usage_basic` / parsed by
`agl/parser.py::parse_gas_usage_basic` into `GasUsageSummary`. Reference
fixture: `tests/fixtures/gas_usage_basic_response.json` (anonymised real
capture).

## What was confirmed

- **No interval or daily data exists for a basic gas meter.** The response
  gives the current billing period as an ESTIMATE + AGL's own bill
  PROJECTION (not a meter read), plus a bounded window of already-billed
  PAST periods (5 in the capture) with real totals. There is no
  electricity-equivalent smooth hourly/daily series to build an Energy
  dashboard chart from — the `gaggle:*` statistics are therefore one
  sparse point per completed billing period (~bimonthly), not hourly. See
  `coordinator.py`.
- **Units: MJ**, confirmed throughout (`unitOfMeasurement`, `quantity`
  suffixes). No m³ ambiguity. `GAS_USAGE_UNIT` in `const.py`.
- **Headers**: the standard AGL BFF header set (`Client-Flavor`,
  `Client-Device`, `Accept-Features`, etc. — see `AGL_ACCEPT_FEATURES` in
  `const.py`) was sent alongside this call in the capture. Not confirmed
  to be strictly *required* (untested without them), but kept for
  consistency with the rest of the BFF.
- **Plan/rates**: real gas plans use TIERED/block `c/MJ` pricing ("First N
  MJ" / "Next N MJ" / "Thereafter"), each a different rate, plus a `c/day`
  supply charge — confirmed via `tests/fixtures/gas_plan_response.json`.
  Not a single flat rate like the sibling electricity integration assumes.
  `coordinator.py` picks the LAST tier (typically "Thereafter") as a
  documented simplification rather than parsing usage thresholds out of
  the free-text `title` strings.
- **Contract discovery**: `/v3/overview` already returns gas contracts
  with `meterType: "basic"` and `type: "gasContract"` — both real observed
  values, unchanged from what was already documented pre-capture.

## What is still open

- **Smart (interval-metered) gas contracts.** This capture is from a
  BASIC meter account. Whether AGL exposes a different endpoint with real
  interval data for smart gas meters is unconfirmed — do not assume the
  `basic` path covers that case. If you have access to a smart-metered gas
  account, a follow-up capture would answer this.
- **Whether the confirmed headers are strictly required** on this
  endpoint (untested without them — see above).
- **Tiered-rate threshold parsing.** The coordinator picks the last tier
  rather than computing which tier applies to the household's actual
  cumulative usage this period (the thresholds are only present as
  substrings of free-text titles, e.g. "First 1644 MJ") — a real option
  for a future enhancement, not implemented to avoid a fragile
  regex-in-title dependency. See the docstring in
  `coordinator.py::_fetch_and_import`.

## Adding support for a smart gas meter (if/when confirmed)

Follow `AGENTS.md` → "Contributing — Adding a New Endpoint": capture
against a real smart-metered gas account, add an anonymised fixture, a
parser function, and an `AglClient` method — do not assume it reuses
`parse_gas_usage_basic`'s shape without a capture proving it does.
