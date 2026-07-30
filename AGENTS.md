# AGENTS.md — Gaggle Integration Guide

> **One-liner**: `gaggle` is a Home Assistant custom integration that pulls
> AGL Australia **gas** smart-meter data from AGL's undocumented mobile API
> and feeds it into HA's Energy dashboard via `import_statistics()`.
>
> **Status: pre-alpha.** Ported from
> [`haggle`](https://github.com/NaanyaBiz/haggle) (the same thing for AGL
> **electricity**, including solar feed-in and Time-of-Use — none of that
> applies here). Auth, contract discovery, and the statistics-import
> machinery work. The actual gas usage fetch is an explicit
> `NotImplementedError` stub, because nobody has captured AGL's real gas
> usage API traffic yet. See **`docs/gas-api.md`** — that capture (Phase 0)
> is the current blocking work, and nothing about usage/cost data should be
> "implemented" by guessing at it.

This file is the canonical documentation for both human contributors and AI
agents. `CLAUDE.md` is a symlink to this file.

---

## Dev Loop

```bash
# Install deps (once, or after pyproject.toml changes)
uv sync

# Run tests
uv run pytest

# Lint + format
uv run ruff check --fix custom_components/ tests/
uv run ruff format custom_components/ tests/

# Type-check
uv run mypy custom_components/gaggle

# Validate manifest
python scripts/validate_manifest.py custom_components/gaggle/manifest.json

# Run all pre-commit hooks
uv run pre-commit run --all-files

# Hassfest — easiest via CI (push a branch + open PR)
# Or use the dedicated image locally:
docker run --rm \
  -v "$(pwd)/custom_components:/github/workspace/custom_components:ro" \
  ghcr.io/home-assistant/hassfest \
  --integration-path /github/workspace/custom_components/gaggle
```

Test strategy: [docs/testing.md](docs/testing.md).

---

## Repo Map

```
custom_components/gaggle/
├── __init__.py          # async_setup_entry / async_unload_entry / async_remove_entry + GaggleRuntimeData
├── manifest.json         # HACS/HA metadata; hassfest validates this
├── const.py               # all constants — DOMAIN, API hosts, config-entry keys, data keys, GAS_FUEL_TYPE, GAS_USAGE_UNIT
├── config_flow.py         # PKCE authorize URL → user pastes callback → exchange → select_contract (filtered to GAS_FUEL_TYPE)
├── diagnostics.py         # anonymized config-entry diagnostics (schema v3) — public-safe
├── coordinator.py         # GaggleCoordinator: 30-day backfill (throttled, 429-aware) + incremental statistics import; catches the gas-usage NotImplementedError once/cycle and leaves usage/cost data unpopulated rather than faking it
├── sensor.py               # 6 SensorEntityDescription entries; GaggleEnergySensor
├── agl/
│   ├── __init__.py
│   ├── client.py           # AglAuth (JWT expiry + token rotation) + AglClient (overview/plan — real; gas usage-fetch — NotImplementedError stubs, see docs/gas-api.md)
│   ├── models.py           # TokenSet, Contract, IntervalReading (generic, not yet wired), DailyReading, BillPeriod, PlanRates
│   ├── parser.py           # JSON → typed dataclasses; parse_overview/parse_plan are real; parse_interval_readings kept as generic fuzz-tested infra for when Phase 0 lands
│   └── pinning.py          # SPKI extraction helper for Trust-On-First-Use TLS pinning
├── strings.json            # translatable config-flow strings
└── translations/en.json    # English strings (must mirror strings.json)

tests/
├── conftest.py                      # _auto_enable_custom_integrations fixture
├── fixtures/
│   ├── PROVENANCE.md                 # fixture provenance — all synthetic/anonymised; gas fixtures blocked on Phase 0
│   ├── hourly_response.json          # generic 30-min interval shape (not currently exercised by any client method — kept as parser test input)
│   ├── overview_response.json        # /v3/overview with accounts + a gas contract
│   ├── plan_response.json            # /v2/plan/energy with gstInclusiveRates
│   └── bill_period_response.json     # usage summary shape (not currently exercised — parser test input)
├── test_init.py                      # setup/unload smoke tests
├── test_config_flow.py               # PKCE step navigation (user → exchange → select_contract, gas-only filtering)
├── test_agl_client.py                # AglAuth token rotation + AglClient HTTP methods + gas-stub NotImplementedError behaviour + pin-check wiring
├── test_const.py                     # base64 sanity-check on AGL_AUTH0_CLIENT
├── test_parser.py                    # parse_interval_readings, parse_overview, parse_plan, _safe_float
├── test_pinning.py                   # SPKI extraction + host-name guards
├── fuzz/
│   ├── fuzz_parser.py                # atheris harness — parser totality + numeric guards (run by fuzz.yml)
│   └── requirements.txt              # hash-pinned atheris (Scorecard Pinned-Dependencies)
├── test_coordinator_statistics.py    # backfill, incremental resume, idempotency, numeric guards, gas-stub handling
├── test_recorder_statistics.py       # sum-chain scenarios vs the REAL recorder (recorder_mock)
├── test_sensor.py                    # sensor descriptions
└── test_diagnostics.py               # leak tests (token/contract/account/SPKI never serialize) + schema shape

docs/
├── gas-api.md            # Phase 0 spec — what a real gas API capture needs to answer before the stubs can be implemented
├── energy-dashboard.md   # user guide (not yet functional — usage data doesn't flow)
├── releasing.md          # release acceptance policy (lightweight; grow once a release actually ships)
├── testing.md            # test strategy — four layers, coverage floor, when live-HA manual testing is required
├── diagnostics.md        # diagnostics schema reference
└── threat-model.md       # lightweight living threat model — grows once gas usage data flows

scripts/
├── access-review.sh          # quarterly access review (SECURITY.md) — read-only, maintainer-run
├── export-settings.sh        # admin-run: re-export control-plane baselines into .github/settings/
├── check_claude_coauthor.sh  # pre-commit hook script — enforces Co-Authored-By: Claude trailer
├── normalize-ruleset.jq / normalize-repo-public.jq  # shared normalizers (export script + settings-drift workflow)
├── validate_manifest.py      # used by the validate-manifest Claude hook
└── wt                        # bash worktree helper (new / list / rm)

.claude/
├── settings.json         # committed hooks config
├── agents/                # 8 subagent definitions (5 domain + 3 review)
└── commands/               # slash commands (new-entity, wt, release, hassfest, pr)

.github/
├── settings/              # declared state of the GitHub control plane (rulesets, repo settings) — see settings/README.md; weekly drift check
├── workflows/
│   ├── ci.yml              # ruff + mypy + pytest (Python 3.14, coverage floor 85 — reset post-strip, see the file's comment) + gitleaks full-history scan + dependency-review + shellcheck/actionlint/zizmor
│   ├── hacs.yml             # HACS validation
│   ├── hassfest.yml         # Home Assistant integration manifest validation
│   ├── release.yml          # tag-triggered Release (first-party gh CLI)
│   ├── codeql.yml           # weekly + per-PR CodeQL Python scan
│   ├── compat.yml           # weekly non-blocking suite vs latest phcc/HA (incl. beta)
│   ├── scorecard.yml        # weekly + on-push OpenSSF Scorecard self-assessment
│   ├── fuzz.yml              # weekly deep run + PR smoke; corpus cached across runs; crash artifacts uploaded
│   └── settings-drift.yml   # weekly: re-export rulesets + public repo settings, diff vs .github/settings/, issue on drift
├── CODEOWNERS               # @naanyabiz owns everything
└── dependabot.yml           # weekly pip + github-actions updates, grouped into one PR per ecosystem

# Repo-root posture files
.gitleaks.toml            # repo-specific secret rules layered on gitleaks defaults
SECURITY.md                # disclosure path + threat-model summary (lightweight — see the file for why)
CONTRIBUTING.md            # dev loop + commit conventions + PR checklist
CODE_OF_CONDUCT.md         # Contributor Covenant 2.1
ROADMAP.md                  # direction + explicit non-goals (Phase 0 first, gas-only, single-retailer AGL, read-only, no telemetry)
```

Note on what's *not* here versus `haggle`: no `docs/compliance/` (the
19-control secure-SDLC framework), no `docs/agents/triage-routine.md` or
`injection-corpus.md` (no automated triage routine runs against this repo),
no `docs/delivery-metrics.md` / `scripts/delivery_metrics.py`. These are
deliberately deferred while the project is pre-alpha — see `haggle`'s
equivalents for the level of process scaffolding to grow into once gaggle
has shipped a release and real users.

---

## Documentation Checklist — Required on Every PR

Every PR that ships code (not pure CI/tooling fixes) MUST include updates to
all of the following before it can be merged. The `/pr` command enforces this.

| Artifact | What to update | Where |
|---|---|---|
| `CHANGELOG.md` | Add bullet(s) under `## [Unreleased]` for every user-visible capability added, changed, or fixed | repo root |
| `AGENTS.md` — Repo Map | Add any new files; update descriptions if a file's role changed | this file |
| `AGENTS.md` — AGL API | Correct any API facts that were proven wrong (endpoints, field names, token lifetimes, headers) | this file |
| `AGENTS.md` — What NOT to Do | Add a new prohibition if a footgun was discovered | this file |
| Memory files | Record non-obvious decisions, confirmed API behaviour, or user preferences that should survive context resets | `~/.claude/projects/.../memory/` |
| `SECURITY.md` + `docs/threat-model.md` | Update when a change alters the security posture, trust boundaries, or accepted risks | repo root + `docs/` |

**When Phase 0 lands** (the gas usage endpoint is captured and confirmed):
this is a sprint boundary. Do the full sprint-boundary sweep — move
completed `## [Unreleased]` items into a dated entry, do a full Repo Map
audit, replace every "TBD"/"stub" claim in this file's AGL API section with
the confirmed fact, and re-read `docs/testing.md`'s coverage-floor note
against the actual post-implementation number.

---

## Subagent Triggers

| Agent | File | Trigger condition |
|---|---|---|
| `ha-integration-architect` | `.claude/agents/ha-integration-architect.md` | Edits to `__init__.py`, `config_flow.py`, `coordinator.py`, `sensor.py`; HA-pattern questions |
| `agl-api-explorer` | `.claude/agents/agl-api-explorer.md` | Any work in `agl/`; new AGL endpoints; raw HTTP questions — **also owns the "don't guess the gas endpoint" rule** |
| `energy-domain-expert` | `.claude/agents/energy-domain-expert.md` | `state_class`, `device_class`, `unit_of_measurement` changes; `import_statistics()` usage |
| `ha-test-writer` | `.claude/agents/ha-test-writer.md` | After every change in `custom_components/gaggle/`; proactively |
| `release-manager` | `.claude/agents/release-manager.md` | Only via `/release` command |
| `code-quality-reviewer` | `.claude/agents/code-quality-reviewer.md` | Non-trivial edits in `custom_components/gaggle/`; before opening a PR |
| `security-reviewer` | `.claude/agents/security-reviewer.md` | Edits in `config_flow.py`, `agl/`, `__init__.py`; any change touching tokens, auth, HTTP, or logging |
| `async-performance-reviewer` | `.claude/agents/async-performance-reviewer.md` | Edits in `coordinator.py`, `agl/client.py`, or any async function |

---

## Slash Commands

| Command | Usage | What it does |
|---|---|---|
| `/new-entity` | `/new-entity <key> <translation_key> <device_class> <state_class> <unit>` | Scaffolds sensor entity + test |
| `/wt` | `/wt new <branch>` \| `/wt list` \| `/wt rm <branch>` | Manages sibling git worktrees |
| `/release` | `/release 0.1.0` | Cuts a semver release via `release-manager` |
| `/hassfest` | `/hassfest` | Validates integration against hassfest rules |
| `/pr` | `/pr` | Documentation audit + push + open PR |

---

## Worktree Workflow

Main worktree is always on `main`. Feature work happens in sibling
worktrees at `../gaggle.wt/<branch>/`. Never commit directly to `main` from
a feature worktree — always open a PR (the `guard-main-branch` hook blocks
direct pushes).

```bash
./scripts/wt new feat/gas-usage-endpoint   # create
./scripts/wt rm feat/gas-usage-endpoint    # remove when done (refuses if dirty)
```

---

## GitHub Issues Workflow

GitHub issues are the canonical place to track non-trivial work that isn't
being done right now — a CHANGELOG entry, a memory note, or an inline
`# TODO` all rot quickly and are invisible to anyone who doesn't already
know to look.

**Open an issue when:** a docs gap or chore is discovered mid-sprint and
out of scope for the current PR; a footgun is found that future agents need
warning about (also add it to "What NOT to Do" if actionable); a
code-review note is "next round" not "now"; a bug reproduces but there's no
time to fix it this PR.

**Don't:** use `# TODO` comments for tracking work; use CHANGELOG
`## [Unreleased]` as a TODO list; use memory files for tracking work items
(memory is for durable decisions and confirmed API behaviour).

**PRs close issues explicitly** — `Closes #N` in the PR body.

---

## AGL API — Key Facts

### Contract discovery + auth — CONFIRMED, fuel-agnostic

These are real, working, unchanged from `haggle` (same AGL account, same
mobile API surface):

- **Auth host**: `https://secure.agl.com.au`. **Data host**:
  `https://api.platform.agl.com.au`.
- **Setup grant**: `authorization_code` + PKCE (`S256`). Config flow builds
  an `/authorize` URL, user opens it in their real browser (handles Akamai
  bot-protection + MFA), pastes back the callback URL.
  - `redirect_uri`: `https://secure.agl.com.au/ios/au.com.agl.mobile/callback`
  - `scope`: `openid profile email offline_access`
  - `audience`: `https://api.platform.agl.com.au/` (trailing slash required)
- **Ongoing grant**: `refresh_token` (stored in `entry.data`). **Token
  endpoint**: `POST /oauth/token`. **client_id**:
  `2mDkNcC8gkDLL7FTT1ZxF5rrQHrLTHL3`.
- **Access token**: JWT (RS256), 15-min expiry (`expires_in: 900`). Decode
  `exp`; refresh 2 min early.
- **CRITICAL — token rotation**: Auth0 rotates the refresh token on every
  exchange. MUST be persisted via `_persist_refresh_token` or the
  integration locks itself out on the next restart.
- **Contract discovery**: `GET /mobile/bff/api/v3/overview` →
  `accounts[].accountNumber`, `accounts[].contracts[].contractNumber`,
  `.type` (`"gasContract"` for gas — real observed value), `.meterType`.
  `contractNumber` ≠ `accountNumber` — use `contractNumber` in all data
  paths. The config flow filters discovered contracts to `GAS_FUEL_TYPE`
  (`const.py`) since gaggle is gas-only.
- **Plan/rates**: `GET /mobile/bff/api/v2/plan/energy/{contractNumber}` —
  real, fuel-agnostic, returns `gstInclusiveRates` (supply charge as a
  `c/day` row) and `gstExclusiveRates`. **Flat gas usage-rate extraction is
  intentionally NOT implemented** — the confirmed rate-type string for a
  gas usage row (`c/MJ`, `c/m³`, or something else) is unknown until Phase
  0 captures a real gas plan response; see the TODO in
  `coordinator._fetch_and_import`.
- **Required headers on data endpoints** (confirmed for
  overview/plan; **unconfirmed but assumed** for whatever gas usage
  endpoint gets captured, since all are served by the same BFF):
  `Client-Flavor`, `Client-Device`, `Accept-Language`, `Accept-Features`
  (see `AGL_ACCEPT_FEATURES` in `const.py` — includes solar/electricity
  feature-flag strings because it's the real header AGL's BFF expects, not
  gaggle logic; don't "clean" it).

### Gas usage — UNKNOWN, Phase 0 blocked

**Nobody has captured AGL's real gas usage API traffic.** `haggle`'s
electricity pattern is
`GET /api/v2/usage/smart/Electricity/{contractNumber}/Current/Hourly?period=...&scaling=...`.
Do **not** assume the gas equivalent substitutes `Gas` for `Electricity` in
that path, or that it shares granularity (30-min), response envelope, or
required query params — none of that is confirmed for gas.

`AglClient.async_get_gas_usage_summary`, `async_get_gas_usage_hourly`, and
`async_get_gas_usage_hourly_previous` are explicit `NotImplementedError`
stubs (`agl/client.py`). `GaggleCoordinator._fetch_and_import` catches that
once per cycle and leaves `consumption_period_usage`,
`consumption_period_cost_aud`, and interval-derived statistics unpopulated
— sensors read `unknown` rather than fabricated data.

**What Phase 0 needs to answer** — full detail in
[`docs/gas-api.md`](docs/gas-api.md): the real URL path(s), required
headers, response envelope shape, the outer/inner-field trap (see below),
units (MJ vs m³), and granularity (interval vs daily vs billing-period-only
for basic meters).

**One confirmed, cross-fuel lesson to apply once captured**: AGL's
electricity interval responses carry both an outer field
(`consumption.quantity` — the real meter read, confirmed against the AGL
portal CSV export) and an inner `consumption.values.quantity` (a
DPI/chart-scaled helper that undercounts by 4-73% with no consistent
ratio — reading it caused a real v0.1.0/v0.2.0-beta production bug in
`haggle`). **Assume the same trap exists for gas** and reconcile whichever
field looks like source of truth against the AGL app or a real gas bill
before trusting it — don't assume the electricity-side field name even
applies.

### Polling cadence (design carried over, numbers may need revisiting)

| Data | Interval | Reason |
|---|---|---|
| Gas usage (once implemented) | 24 h | Placeholder — `haggle`'s electricity data lags 24-48h behind AEMO; gas lag is unknown until Phase 0 (could be days for digital meters, months for basic-meter billing cycles) |
| Plan / overview | Same as `haggle` pattern, TBD | Rarely changes |
| Token refresh | Just-in-time (< 2 min to `exp`) | tokens expire at 15 min |
| After a FAILED poll | 30 min (`RETRY_INTERVAL_ON_ERROR`) | Same self-healing pattern as `haggle` — a transient error shouldn't cost a full poll cycle and look like "the poll never ran" |

**Trailing rewindow (self-healing) — design kept from `haggle`**: once
initial backfill is complete, every poll re-fetches the trailing
`REWINDOW_DAYS`. `async_add_external_statistics` is idempotent on
`(statistic_id, start)` so the overwrite is safe. This machinery is wired
and tested even though the usage fetch itself is a stub.

**Baseline lookup — the one subtle bug class to re-verify once real data
flows**: the cumulative-sum baseline is looked up in `_import_intervals`
using the actual earliest fetched-interval hour as the cutoff, NOT a
`fetch_start`-derived UTC midnight. This is what caused a real phantom-kWh
production bug in `haggle` (AGL's `period=` query is interpreted in the
contract's local timezone, so a UTC-midnight cutoff folds hours of
about-to-be-overwritten old sums into the baseline). The design is ported
unchanged in `coordinator._resolve_fetch_start` / `_import_intervals` — it
applies to any fuel, but has not yet been exercised against real gas data.

### TLS pinning (Trust-On-First-Use) — CONFIRMED, unchanged

Both `secure.agl.com.au` and `api.platform.agl.com.au` are pinned by SPKI
hash, captured inside `agl/pinning.py::GagglePinningConnector` (a
`TCPConnector` subclass — `resp.connection` is already released by the
time a response is constructed, so the subclass approach is required, not
optional; see `haggle`'s AGENTS.md history if this needs re-deriving).
Mismatch is warn-only (persistent notification `gaggle_pin_mismatch_<host>`
fires) so a legitimate AGL cert rotation doesn't brick installs.

---

## Energy Dashboard Contract

- `device_class = ENERGY` (or `GAS` if the real gas API turns out to
  return volume, m³), `state_class = TOTAL_INCREASING`,
  `native_unit_of_measurement = GAS_USAGE_UNIT` (currently `"MJ"` —
  **unconfirmed**, see `const.py`).
- Historical data MUST be fed via `async_add_external_statistics()`, never
  live state updates — AGL data is always historical.
- Statistic IDs per contract:
  - `gaggle:consumption_<contract_number>` — `has_sum=True`,
    **`unit_class="energy"`** (required for the statistic to appear in the
    Energy dashboard's consumption-source picker — `unit_class=None`
    silently hides it).
  - `gaggle:cost_<contract_number>` — AUD, `has_sum=True`,
    `unit_class=None`.
- Resume point: `get_last_statistics(hass, 1, stat_id, True, {"start",
  "sum"})`. Each import is idempotent on `(statistic_id, start)`.
- No solar, no per-tariff series — those were `haggle`-only (electricity
  solar feed-in / Time-of-Use). Gas has neither.

---

## What NOT to Do

Carried over from `haggle` (fuel-agnostic — still apply verbatim):

- **No `requests`** — always `aiohttp`. Blocking I/O in the event loop
  will freeze HA.
- **No blocking I/O in the coordinator** — `_async_update_data` must be
  fully async.
- **No OTP/portal flow** — auth is PKCE via the user's real browser, not
  portal scraping.
- **No hardcoded contract numbers** — they come from `/v3/overview` at
  config time.
- **Don't store `access_token` in `entry.data`** — it's transient (15
  min). Persist only `refresh_token`; keep `access_token` in memory only.
- **Don't use `async_add_executor_job`** for AGL API calls — they're
  already async.
- **Don't omit required headers** on data endpoints — omitting them
  returns HTTP 500 with no useful error body on the electricity side;
  assume the same for gas until proven otherwise.
- **Don't set `unit_class=None` on the consumption statistic** — silently
  hides it from the Energy dashboard picker.
- **Never add a diagnostics field without routing it through the scrub
  pass** (`diagnostics.py::_scrub`). Diagnostics files are attached to
  public GitHub issues. Bump `DIAGNOSTICS_SCHEMA_VERSION` and update
  `docs/diagnostics.md` in the same PR when the shape changes.
- **No committing directly to `main`** — the `guard-main-branch` hook
  blocks it. Use a feature branch + PR.
- **No mutable GitHub Action refs** — pin every `uses: owner/action@…` to
  a 40-char commit SHA with a `# vX.Y` comment.
- **Don't surface raw AGL/Auth0 response bodies in exceptions** that
  propagate to `ConfigEntryAuthFailed` / `UpdateFailed`. Pattern:
  `_LOGGER.debug("…body: %s", _redact_body(text)); raise AGLError(...)`.
- **Don't use unbounded `float()` coercion on AGL response values** — use
  `_safe_float`.
- **Don't "fix" a bare multi-type `except A, B:` by adding parentheses.**
  This is `ruff format`'s canonical PEP 758 output for the Python 3.14
  target — `except A, B:` means `except (A, B):` and catches every listed
  type. Adding parentheses is not idempotent; `ruff format --check` will
  fail.
- **Don't put `AGL` (or any close variant) in `DeviceInfo.manufacturer`.**
  Unofficial third-party integration — keep `manufacturer="Gaggle"`.
- **Don't pair `state_class=MEASUREMENT` with `device_class=MONETARY`** —
  only `None` or `TOTAL` are valid for MONETARY.
- **Don't use `device_class=MONETARY` for unit prices** — MONETARY is for
  cumulative amounts, not rates. Pair rate sensors with
  `state_class=MEASUREMENT` and a unit string like `"AUD/MJ"`.
- **Implement `async_remove_entry` if the integration creates entities** —
  otherwise deleting it leaves orphan entity-registry rows.
- **Don't clear `gaggle:*` external statistics in `async_remove_entry`** —
  that's the user's own historical data.
- **Don't fire backfill requests in a tight loop** — sleep
  `BACKFILL_INTER_REQUEST_DELAY` between days.
- **Don't derive the cumulative-sum baseline cutoff from a `fetch_start`
  UTC midnight** — see "Baseline lookup" above.
- **Don't let non-`AGLError` exception types escape `AglClient`** — every
  coordinator catch site is designed around the `AGLError` family.
  `AglClient._get` and `async_force_refresh` wrap transport/parse failures
  into `AGLError`.
- **Don't exact-pin `pytest-homeassistant-custom-component`** — keep it a
  range; `uv.lock` is the reproducibility authority.
- **Don't re-add remote ruff/mypy pre-commit hooks** — they'd run a second
  toolchain copy that drifts from `uv.lock`.
- **Don't lower `--cov-fail-under` in `ci.yml` to make a PR pass** — it's
  a ratchet gate. It was reset to 85 post-strip (see the file's comment);
  raise it as coverage genuinely rises, never lower it to unblock a PR.

**Gas-specific, new to this project**:

- **Don't guess at the gas usage endpoint.** Don't substitute `Gas` for
  `Electricity` in the known electricity path, don't invent a response
  shape, don't wire the usage-fetch stubs to call `/Electricity/...` as a
  "temporary" measure — that would silently report electricity data as
  gas data, which is worse than the feature not existing. See
  `docs/gas-api.md`.
- **Don't invent gas plan rate-shape parsing** (e.g. block pricing) without
  a real captured gas plan response. `coordinator._fetch_and_import`
  leaves `unit_rate_aud_per_unit` as `None` with a documented TODO rather
  than guessing at the rate-type string.
- **Don't assume `GAS_USAGE_UNIT = "MJ"` is confirmed.** It's a reasonable
  default (AGL bills gas in MJ) but unconfirmed until Phase 0. It's a
  single named constant precisely so this is a one-line change once
  confirmed — don't scatter the literal string elsewhere.

---

## Contributing — Adding a New Endpoint

1. **Identify the endpoint contract** from a real AGL account with an
   active gas contract. Any HTTP-debugging tool is fine — you need the URL
   path, required headers, and JSON response shape.
2. **Anonymise before committing**: redact `accountNumber`,
   `contractNumber`, address, product code, and any meter-read timeseries
   that fingerprints a real residence. Use the placeholders in
   `tests/fixtures/overview_response.json` as the canonical set
   (`1234567890` / `9999999999` / `1 Sample Street SUBURB QLD 4000`).
3. Add an anonymised fixture under `tests/fixtures/<name>_response.json`.
4. Add a parser in `agl/parser.py` and a corresponding `AglClient` method
   in `agl/client.py` — replacing the relevant `NotImplementedError` stub.
5. Add tests against the fixture. Do not commit any captures with real
   customer values.
6. Update this file's "AGL API — Key Facts" section: move the fact from
   "UNKNOWN" to confirmed, with the reconciliation evidence (date, what
   you checked it against).

---

## Commit Conventions

Conventional Commits, enforced by the `commitlint` pre-commit hook:

```
feat: implement gas usage interval fetch
fix: handle missing consumption field
chore(release): v0.1.0
ci: add hacs workflow
```

Every commit MUST include the `Co-Authored-By: Claude` trailer (enforced
by the `require-claude-coauthor` pre-commit hook):

```bash
git commit -m "feat: implement gas usage interval fetch

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Provenance

This codebase was ported from
[`haggle`](https://github.com/NaanyaBiz/haggle) (commit
`04ebc21b53315ec9b176b71c2abfbe69d80ce8d7`) by Claude Code, with solar and
Time-of-Use code paths removed and the electricity usage-fetch replaced by
an explicit stub pending a real gas API capture. Reviewed by the human
maintainer. All commits carry `Co-Authored-By: Claude` trailers.

### AI toolchain

| Tool | Role | Pinning / scope |
|---|---|---|
| **Claude Code (CLI)** | Interactive author of product code, operating under the maintainer's identity | Tool grants governed by `.claude/settings.json` (committed) plus a per-machine `.claude/settings.local.json` (gitignored). |
| **Claude Code subagents** | Domain + review agents invoked in-session (see Subagent Triggers above) | Model-pinned in `.claude/agents/*.md`. |
| **Codex (`chatgpt-codex-connector`)** | Cross-vendor PR reviewer, if configured | Advisory comments only — never a merge or approval authority. |

**Human-approved boundary.** Merging a PR and creating/pushing a release
tag always require a live human decision. The committed
`.claude/settings.json` grants no merge verb and `ask`-gates every
`Edit`/`Write`/`MultiEdit` touching `.claude/**`.
