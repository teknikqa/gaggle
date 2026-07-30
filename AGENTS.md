# AGENTS.md — Gaggle Integration Guide

> **One-liner**: `gaggle` is a Home Assistant custom integration that pulls
> AGL Australia **gas** smart-meter data from AGL's undocumented mobile API
> and feeds it into HA's Energy dashboard via `import_statistics()`.
>
> **Status: pre-release, functional against a basic (non-smart) gas
> meter.** Ported from [`haggle`](https://github.com/NaanyaBiz/haggle) (the
> same thing for AGL **electricity**, including solar feed-in and
> Time-of-Use — none of that applies here). Auth, contract discovery, the
> real gas usage fetch, and the statistics-import machinery all work,
> confirmed against a real AGL account (Phase 0 capture, 2026-07-30 — see
> **`docs/gas-api.md`**). The confirmed shape turned out to be fundamentally
> different from `haggle`'s: a basic gas meter has no interval data at all,
> so gaggle imports one sparse statistic point per completed billing period
> (~bimonthly), not an hourly chart. No release has shipped yet — see
> `docs/releasing.md` for what's left before one does.

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
uv run python scripts/validate_manifest.py custom_components/gaggle/manifest.json

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
├── const.py               # all constants — DOMAIN, API hosts, config-entry keys, GAS_FUEL_TYPE, GAS_USAGE_UNIT ("MJ", confirmed), GAS_RATE_TYPE
├── config_flow.py         # PKCE authorize URL → user pastes callback → exchange → select_contract (filtered to GAS_FUEL_TYPE)
├── diagnostics.py         # anonymized config-entry diagnostics (schema v3) — public-safe
├── coordinator.py         # GaggleCoordinator: ONE usage call + ONE plan call per poll (no per-day backfill loop — AGL returns the whole current+past-periods window in one shot); imports past_periods as sparse per-billing-period statistics with baseline continuity
├── sensor.py               # 7 SensorEntityDescription entries; GaggleEnergySensor
├── agl/
│   ├── __init__.py
│   ├── client.py           # AglAuth (JWT expiry + token rotation) + AglClient: overview/plan/gas-usage-basic all REAL, confirmed endpoints
│   ├── models.py           # TokenSet, Contract, GasPastPeriod, GasUsageSummary, PlanRates
│   ├── parser.py           # JSON → typed dataclasses; parse_overview/parse_plan/parse_gas_usage_basic all real, confirmed
│   └── pinning.py          # SPKI extraction helper for Trust-On-First-Use TLS pinning
├── strings.json            # translatable config-flow strings
└── translations/en.json    # English strings (must mirror strings.json)

tests/
├── conftest.py                      # _auto_enable_custom_integrations fixture
├── fixtures/
│   ├── PROVENANCE.md                 # fixture provenance — gas_usage_basic/gas_plan are real anonymised captures (Phase 0, 2026-07-30); rest synthetic
│   ├── overview_response.json        # /v3/overview with accounts + a contract
│   ├── plan_response.json            # /v2/plan/energy — generic/flat shape (fuel-agnostic parser test)
│   ├── gas_plan_response.json        # real captured gas plan — TIERED c/MJ pricing
│   └── gas_usage_basic_response.json # real captured /v2/usage/basic/Gas response
├── test_init.py                      # setup/unload smoke tests
├── test_config_flow.py               # PKCE step navigation (user → exchange → select_contract, gas-only filtering)
├── test_agl_client.py                # AglAuth token rotation + AglClient HTTP methods (overview/plan/gas-usage-basic, all real) + pin-check wiring
├── test_const.py                     # base64 sanity-check on AGL_AUTH0_CLIENT
├── test_parser.py                    # parse_overview, parse_plan (incl. tiered gas), parse_gas_usage_basic, _safe_float — 100% coverage
├── test_pinning.py                   # SPKI extraction + host-name guards
├── fuzz/
│   ├── fuzz_parser.py                # atheris harness — parser totality + numeric guards (run by fuzz.yml)
│   └── requirements.txt              # hash-pinned atheris (Scorecard Pinned-Dependencies)
├── test_coordinator_statistics.py    # period-statistics aggregation, baseline continuity, tiered-rate tier selection, failure-aware cadence
├── test_recorder_statistics.py       # sum-chain scenarios vs the REAL recorder (recorder_mock) — incl. the aged-out-period baseline regression guard
├── test_sensor.py                    # sensor descriptions, registration, native values
└── test_diagnostics.py               # leak tests (token/contract/account/SPKI never serialize) + schema shape

docs/
├── gas-api.md            # CONFIRMED Phase 0 findings — real endpoint, real response shape, what's still open (smart-meter gas)
├── energy-dashboard.md   # user guide — which statistic to add, what "sparse per-period bars" means
├── releasing.md          # release acceptance policy (lightweight; grow once a release actually ships)
├── testing.md            # test strategy — four layers, coverage floor, when live-HA manual testing is required
├── diagnostics.md        # diagnostics schema reference
└── threat-model.md       # lightweight living threat model — grow once this has real users

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
│   ├── ci.yml              # ruff + mypy + pytest (Python 3.14, coverage floor 87, see the file's comment) + gitleaks full-history scan + dependency-review + shellcheck/actionlint/zizmor
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
ROADMAP.md                  # direction + explicit non-goals (gas-only, single-retailer AGL, read-only, no telemetry)
```

Note on what's *not* here versus `haggle`: no `docs/compliance/` (the
19-control secure-SDLC framework), no `docs/agents/triage-routine.md` or
`injection-corpus.md` (no automated triage routine runs against this repo),
no `docs/delivery-metrics.md` / `scripts/delivery_metrics.py`. These are
deliberately deferred while the project is pre-release — see `haggle`'s
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

**If a smart-metered gas account is ever captured**: that's a sprint
boundary. Do the full sweep — move completed `## [Unreleased]` items into a
dated entry, do a full Repo Map audit, add the new endpoint facts to this
file's AGL API section, and re-read `docs/testing.md`'s coverage-floor note
against the actual post-implementation number.

---

## Subagent Triggers

| Agent | File | Trigger condition |
|---|---|---|
| `ha-integration-architect` | `.claude/agents/ha-integration-architect.md` | Edits to `__init__.py`, `config_flow.py`, `coordinator.py`, `sensor.py`; HA-pattern questions |
| `agl-api-explorer` | `.claude/agents/agl-api-explorer.md` | Any work in `agl/`; new AGL endpoints; raw HTTP questions — **also owns the "don't guess at an unconfirmed endpoint" rule** |
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
./scripts/wt new feat/tiered-rate-threshold   # create
./scripts/wt rm feat/tiered-rate-threshold    # remove when done (refuses if dirty)
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

All CONFIRMED via a live mitmproxy capture against the project maintainer's
own AGL account, 2026-07-30 (Phase 0). Full narrative + what's still open:
[`docs/gas-api.md`](docs/gas-api.md).

### Auth + contract discovery — fuel-agnostic, unchanged from `haggle`

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
  `.type` (`"gasContract"` for gas), `.meterType` (`"basic"` confirmed on
  the captured account — non-smart, manually/self-read meter).
  `contractNumber` ≠ `accountNumber` — use `contractNumber` in all data
  paths. The config flow filters discovered contracts to `GAS_FUEL_TYPE`
  (`const.py`) since gaggle is gas-only.
- **Required headers on data endpoints**: `Client-Flavor`, `Client-Device`,
  `Accept-Language`, `Accept-Features` (see `AGL_ACCEPT_FEATURES` in
  `const.py` — includes solar/electricity feature-flag strings because
  it's the real header AGL's BFF expects, not gaggle logic; don't "clean"
  it). Confirmed sent alongside overview/plan/gas-usage calls in the
  capture; not confirmed to be strictly *required* on the gas usage
  endpoint specifically (untested without them).

### Gas usage — CONFIRMED, basic (non-smart) meter

**The real endpoint does NOT mirror `haggle`'s electricity shape.**
`haggle`'s pattern is
`GET /api/v2/usage/smart/Electricity/{contractNumber}/Current/Hourly?period=...&scaling=...`.
The real, confirmed, implemented gas endpoint is:

```
GET /mobile/bff/api/v2/usage/basic/Gas/{contractNumber}?isRestricted=False&unit=MJ
```

Implemented in `AglClient.async_get_gas_usage_basic` / parsed by
`parse_gas_usage_basic` into `GasUsageSummary` (`agl/models.py`).

**No interval or daily data exists for this meter type.** The response
gives:
- The **current billing period** as an ESTIMATE (`billPeriod.usage`) plus
  AGL's own bill PROJECTION (`billPeriod.projection`) — not a meter read.
  Sensor-only data (`consumption_period_usage`/`cost_aud`,
  `projection_cost_aud`); never imported as statistics.
- A bounded **window of already-billed past periods**
  (`pastUsage.items[]`, 5 in the capture) — real, actual totals via the
  numeric `usageQuantity`/`usageAmount` fields (prefer these over the
  sibling formatted `quantity`/`amount` display strings, which need
  string parsing). This is the ONLY source of real historical data, and
  it's what feeds the `gaggle:*` statistics — one sparse point per
  completed billing period (~bimonthly), not hourly.

**Units: MJ, confirmed** (`unitOfMeasurement` and `quantity` suffixes
throughout). `GAS_USAGE_UNIT` in `const.py`.

**What's still open** (see `docs/gas-api.md` for detail): whether a
smart-metered gas account exposes a different endpoint with real interval
data (unconfirmed — this capture is from a basic meter); whether the
confirmed headers are strictly required on this endpoint.

### Plan / rates — CONFIRMED, tiered pricing

`GET /mobile/bff/api/v2/plan/energy/{contractNumber}` — real, fuel-agnostic
endpoint, returns `gstInclusiveRates` (supply charge as a `c/day` row) and
`gstExclusiveRates`. **Real gas plans use TIERED/block `c/MJ` pricing** —
multiple detail rows ("First N MJ" / "Next N MJ" / "Thereafter"), each a
different rate — not a single flat rate like the sibling electricity
integration's `type == "c/kWh"` assumption. `parse_plan` collects the raw
allowlisted rows generically (fuel-agnostic, unchanged); picking a single
"the" rate is a `coordinator.py` decision:
`_fetch_and_import` selects the LAST `c/MJ` detail row (`GAS_RATE_TYPE` in
`const.py`), typically "Thereafter", as a documented simplification —
computing the actual marginal tier from cumulative usage-to-date would
need parsing thresholds out of free-text titles (e.g. "First 1644 MJ"),
which is a real option for a future enhancement, not implemented to avoid
a fragile regex-in-title dependency.

### Polling cadence

| Data | Interval | Reason |
|---|---|---|
| Gas usage summary + plan | 24 h (`SCAN_INTERVAL`) | Keeps the current-period estimate reasonably fresh; the underlying data barely changes faster than daily |
| Token refresh | Just-in-time (< 2 min to `exp`) | tokens expire at 15 min |
| After a FAILED poll | 30 min (`RETRY_INTERVAL_ON_ERROR`) | Same self-healing pattern as `haggle` — a transient error shouldn't cost a full poll cycle and look like "the poll never ran" |

**No per-day backfill loop.** Unlike `haggle`, one `async_get_gas_usage_basic`
call returns the whole current-period-plus-past-periods window in one
shot — there's nothing to throttle or chunk across multiple requests.

**Baseline continuity — the one subtle bug class carried over from
`haggle` and still real here**: AGL's `pastUsage.items[]` is a bounded
WINDOW (5 periods in the capture), not full account history. An older
already-imported period can age out of a later poll's response. If the
cumulative-sum baseline were assumed to start at 0 for whatever's in the
CURRENT response, an aged-out period would make the sum reset and step
DOWN — breaking `TOTAL_INCREASING` monotonicity, the same defect CLASS as
`haggle`'s v0.3.0 phantom-spike bug (different root cause — that one was a
UTC/local-timezone cutoff, this one is a rolling window — same consequence
class). `coordinator._import_periods` looks the baseline up from the
recorder before the earliest period in each batch
(`_get_baseline_sums`/`_baseline_sums_before`, two-stage: cheap window then
reach-back), exactly like `haggle` does for its hourly rewindow. Regression
test: `tests/test_recorder_statistics.py::test_aged_out_period_baseline_continuity`
(real recorder, not mocked).

**Row placement — a documented simplification, not a bug**: each period's
statistic row is keyed at midnight UTC of the period's END date
(`coordinator._midnight_utc`), not local midnight. This can place the
Energy-dashboard bar up to ~14h off the "true" boundary depending on the
contract's timezone. Unlike `haggle`'s hourly rewindow (where the
equivalent shortcut caused real double-counting because the same hour gets
overwritten repeatedly), a gaggle period row is written ONCE and never
revisited with a different baseline — so the consequence here is purely
cosmetic (which day a ~2-month bar renders on), not a correctness bug.

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

- `device_class = ENERGY`, `state_class = TOTAL_INCREASING`,
  `native_unit_of_measurement = GAS_USAGE_UNIT` (`"MJ"`, confirmed).
- Historical data MUST be fed via `async_add_external_statistics()`, never
  live state updates.
- Statistic IDs per contract:
  - `gaggle:consumption_<contract_number>` — `has_sum=True`,
    **`unit_class="energy"`** (required for the statistic to appear in the
    Energy dashboard's consumption-source picker — `unit_class=None`
    silently hides it). Sparse: one point per completed billing period,
    NOT hourly/daily — there's no underlying interval data for a basic
    gas meter to build a smoother chart from.
  - `gaggle:cost_<contract_number>` — AUD, `has_sum=True`,
    `unit_class=None`.
- Idempotent on `(statistic_id, start)` — safe to re-import the same
  period every poll.
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
- **Don't derive a statistics baseline by assuming it starts at 0 for
  whatever's in the current response** — see "Baseline continuity" above.
- **Don't let non-`AGLError` exception types escape `AglClient`** — every
  coordinator catch site is designed around the `AGLError` family.
  `AglClient._get` and `async_force_refresh` wrap transport/parse failures
  into `AGLError`.
- **Don't exact-pin `pytest-homeassistant-custom-component`** — keep it a
  range; `uv.lock` is the reproducibility authority.
- **Don't re-add remote ruff/mypy pre-commit hooks** — they'd run a second
  toolchain copy that drifts from `uv.lock`.
- **Don't lower `--cov-fail-under` in `ci.yml` to make a PR pass** — it's
  a ratchet gate. Raise it as coverage genuinely rises, never lower it to
  unblock a PR.

**Gas-specific**:

- **Don't guess at an unconfirmed AGL endpoint.** The basic-meter gas
  usage endpoint is now confirmed and implemented, but if you're adding
  support for a SMART-metered gas account, that's a different, unconfirmed
  endpoint — capture it for real (see "Contributing — Adding a New
  Endpoint" below) rather than assuming it mirrors either the basic-gas or
  electricity shape.
- **Don't compute a tiered-plan "effective rate" by parsing usage
  thresholds out of the free-text `title` string** without a real reason
  to — `coordinator.py`'s last-tier simplification is documented and
  intentional; if you do build the threshold-aware version, keep the
  simplification as a fallback for plans whose titles don't parse.

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
   in `agl/client.py`.
5. Add tests against the fixture. Do not commit any captures with real
   customer values.
6. Update this file's "AGL API — Key Facts" section with the confirmed
   fact, including the reconciliation evidence (date, what you checked it
   against).

---

## Commit Conventions

Conventional Commits, enforced by the `commitlint` pre-commit hook:

```
feat: compute effective tiered-plan rate from usage-to-date
fix: handle missing consumption field
chore(release): v0.1.0
ci: add hacs workflow
```

Every commit MUST include the `Co-Authored-By: Claude` trailer (enforced
by the `require-claude-coauthor` pre-commit hook):

```bash
git commit -m "feat: compute effective tiered-plan rate from usage-to-date

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Provenance

This codebase was ported from
[`haggle`](https://github.com/NaanyaBiz/haggle) (commit
`04ebc21b53315ec9b176b71c2abfbe69d80ce8d7`) by Claude Code, with solar and
Time-of-Use code paths removed and the gas usage fetch implemented against
a real captured API contract (Phase 0, 2026-07-30). Reviewed by the human
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
