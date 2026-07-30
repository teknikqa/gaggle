# AGL Gas Usage API — Phase 0 (TODO)

`gaggle` cannot fetch real gas usage data yet. Nobody has captured AGL's
actual gas smart-meter API traffic — the equivalent of the `Electricity`
usage endpoints (`/mobile/bff/api/v2/usage/smart/Electricity/{contractNumber}/...`)
documented for the sibling `haggle` integration has no confirmed gas
counterpart. Until a human does a live capture against a real AGL gas
account (a mitm session against the AGL mobile app, the same way the
electricity endpoints were originally documented), `AglClient.async_get_gas_usage_summary`
and `async_get_gas_usage_hourly[_previous]` stay explicit
`NotImplementedError` stubs rather than guesses — inventing an endpoint
path or response shape risks either a wrong integration or, worse, a
plausible-looking one that silently calls `/Electricity/...` and reports
electricity numbers as gas.

## What the capture needs to answer

- **URL path(s)**: the gas equivalent of `Current/Hourly` and
  `Previous/Hourly` (and the bill-period summary endpoint) — does AGL use a
  `Gas` resource segment analogous to `Electricity`/`ElectricitySolar`, and
  is the URL shape otherwise identical (`{contractNumber}/{Current|Previous}/Hourly?period=...&scaling=...`)?
- **Headers**: do the gas endpoints require the same `Client-Flavor` /
  `Client-Device` / `Accept-Features` / `scaling` headers as the electricity
  ones, or a different `Accept-Features` feature-flag list?
- **Response envelope**: same `sections[].items[]` shape with a per-item
  block keyed by type (`consumption` on electricity), or something else
  entirely for gas?
- **Units and field names**: is usage reported in MJ (megajoules — the AGL
  gas-billing norm) or m³ (raw meter units, sometimes converted client-side)?
  Confirm the exact field the app treats as ground truth, the same way
  `consumption.quantity` (outer) was confirmed against a portal CSV export
  for electricity — don't assume an inner/outer field pair behaves the same
  way without reconciling against a real bill or app figure.
- **Granularity**: does gas report in 30-minute intervals like electricity's
  smart meters, or daily/other granularity (many residential gas meters are
  not interval-metered the way electricity smart meters are)?

Once a capture answers these, replace the stubs in `agl/client.py` following
the pattern in `AGENTS.md` → "Contributing — Adding a New Endpoint": add an
anonymised fixture, a parser in `agl/parser.py`, the real `AglClient`
method, and tests against the fixture.
