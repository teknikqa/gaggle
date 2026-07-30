# Roadmap

This roadmap states what `gaggle` intends to do — and deliberately will not do —
over roughly the next twelve months. It is a direction of travel, not a
contract: `gaggle` is a single-maintainer, best-effort open-source project, and
priorities shift as AGL changes its API and as users report issues. Tracked work
lives in [GitHub issues](https://github.com/NaanyaBiz/gaggle/issues); the
priority labels (`P1`/`P2`/`P3`) there are the live source of truth.

_Last reviewed: 2026-07. Reviewed at least annually and at each minor release._

## Direction (next ~12 months)

**Ship a v0.1.0 beta.** Phase 0 (capturing the real AGL gas API contract)
is done — see `docs/gas-api.md`. Real gas usage data flows for a basic
meter: current-period estimate/projection sensors plus a sparse
per-billing-period `gaggle:consumption_<contract>` / `cost_<contract>`
statistic, confirmed against the maintainer's own account. What's left
before a beta: broader validation across more real accounts (see
"Validate across meter types" below), and the standard release-acceptance
bar in `docs/releasing.md`.

**Validate across meter types.** The Phase 0 capture is from one basic
(manually/self-read) meter account. Most Australian gas meters are basic;
some networks run remotely-read digital meters that may expose different
(possibly interval) data — unconfirmed. Recruit a tester with a
digitally-read gas meter to find out whether that changes the product
story, and validate the tiered-plan rate parsing against more real plans.

**Consider computing the actual marginal tiered rate.** Today the unit-rate
sensor reads the highest ("Thereafter") tier as a documented
simplification. Parsing the usage thresholds out of plan titles (e.g.
"First 1644 MJ") and computing the real effective rate from usage-to-date
would be more accurate for light users — tracked as a real enhancement,
not required for a first release.

**Keep the engineering baseline healthy.** Carry forward `haggle`'s
secure-SDLC posture (CI gates, dependency review, gitleaks, coverage
ratchet) as the codebase and its user base grow.

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
- **No fabricated data.** A basic gas meter only gives AGL billing-period
  totals, not daily/interval reads — `gaggle` shows that honestly: sensors
  for the current period's real AGL estimate, and a sparse
  once-per-billing-period Energy-dashboard statistic built only from real,
  already-billed totals. It will never interpolate or estimate a daily
  chart to look smoother than the underlying data actually is.

## How priorities are set

Priority reflects consequence to users, not effort. Correctness of the
usage/cost data written to the recorder outranks new features; a defect that
writes wrong statistics or takes the integration down is always addressed
before enhancement work.
