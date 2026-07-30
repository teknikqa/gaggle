# Roadmap

This roadmap states what `gaggle` intends to do — and deliberately will not do —
over roughly the next twelve months. It is a direction of travel, not a
contract: `gaggle` is a single-maintainer, best-effort open-source project, and
priorities shift as AGL changes its API and as users report issues. Tracked work
lives in [GitHub issues](https://github.com/NaanyaBiz/gaggle/issues); the
priority labels (`P1`/`P2`/`P3`) there are the live source of truth.

_Last reviewed: 2026-07. Reviewed at least annually and at each minor release._

## Direction (next ~12 months)

**Phase 0 — capture the real AGL gas API contract.** Nobody has captured
AGL's gas usage endpoint yet. Until a real device capture documents the URL,
required headers, response envelope, units (MJ vs m³), and data granularity,
the usage-fetch path is an explicit `NotImplementedError` stub — see
`docs/gas-api.md`. This blocks everything below and is the current priority.

**Ship a working v0.1.0 beta** once Phase 0 lands: real gas interval/daily
data flowing into `gaggle:consumption_<contract>` and
`gaggle:cost_<contract>`, validated against the AGL app and a real gas bill
for at least one account.

**Validate across meter types.** Most Australian gas meters are basic
(manually read every 2-3 months); some networks run remotely-read digital
meters with daily data. Confirm what AGL's API actually serves for each, and
whether the product story needs to change for basic-meter accounts (see
Non-goals below).

**Keep the engineering baseline healthy.** Carry forward `haggle`'s
secure-SDLC posture (CI gates, dependency review, gitleaks, coverage
ratchet) as the codebase grows past the Phase 0 stub.

## Non-goals (what `gaggle` will *not* do)

These are deliberate scope boundaries, not backlog items:

- **One retailer only.** `gaggle` targets AGL Australia's customer API. It
  will not grow into a multi-retailer abstraction.
- **Gas only.** No electricity, water, or other utilities — that's
  [`haggle`](https://github.com/NaanyaBiz/haggle)'s scope, not this project's.
- **Read-only.** `gaggle` imports historical usage/cost statistics into the
  HA Energy dashboard. It will not control devices, change tariffs, or take
  any write action on the AGL account.
- **No telemetry.** No phone-home, analytics, or external telemetry vendors —
  in the integration or in CI.
- **No portal scraping or OTP flows.** Authentication is Auth0 PKCE through
  the user's real browser; `gaggle` will not automate the AGL web portal or
  handle credentials directly.
- **No destructive uninstall.** Removing the integration will not delete the
  user's accumulated `gaggle:*` energy history.
- **No fabricated data.** If AGL's API only serves billing-period totals for
  a given meter type (rather than daily/interval reads), `gaggle` will show
  that honestly — period sensors, no Energy-dashboard history import — rather
  than interpolate or estimate a daily chart. See the Phase 0 decision gate
  in the project handover plan.

## How priorities are set

Priority reflects consequence to users, not effort. Correctness of the
usage/cost data written to the recorder outranks new features; a defect that
writes wrong statistics or takes the integration down is always addressed
before enhancement work.
