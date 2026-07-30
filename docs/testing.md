# Test strategy

The strategy in one sentence: every defect class that has ever escaped to
production gets a named, pinned regression test; the trust boundary gets
fuzzed; the recorder seam gets exercised for real; and no stable ships
without recorded acceptance on a live HA instance.

## The four layers

| Layer | What | Where | When it runs |
|---|---|---|---|
| 1. Unit | Parsers, client, models, const — pure Python against anonymised fixtures | `tests/test_parser.py`, `test_agl_client.py`, `test_const.py`, `test_pinning.py` | Every PR + push (CI required check) |
| 2. Harness integration | Real HA core via `pytest-homeassistant-custom-component`: setup/unload, config flow, coordinator, sensors, diagnostics — recorder mocked at the boundary; PLUS `tests/test_recorder_statistics.py`, which runs sum-chain scenarios against a **real** recorder (`recorder_mock`), because a mocked seam is exactly where `haggle`'s baseline/spike-class bugs escaped | `tests/test_*.py` | Every PR + push (CI required check) |
| 3. Fuzz | Atheris totality fuzzing of `agl/parser.py` — the trust boundary for attacker-influenceable JSON (TLS pinning is warn-only) | `tests/fuzz/`, `fuzz.yml` | Weekly deep run + smoke on every PR (required check) |
| 4. Acceptance (beta soak) | Beta prerelease soaked on a real HA instance against a real AGL gas account, validating against the AGL app / a real bill | HACS beta channel; recorded per `docs/releasing.md` | Every beta → stable promotion |

## Required depth per change type

- **Parser / client / models change**: layer-1 tests against an anonymised
  fixture. New endpoint ⇒ new fixture + parser tests (AGENTS.md § Adding a
  New Endpoint). Any change also gets the PR fuzz smoke automatically.
- **Coordinator / statistics change**: layer-2 tests; if the change touches
  cumulative-sum semantics (baselines, rewindow), extend
  `tests/test_recorder_statistics.py` — mocked-recorder tests alone are NOT
  sufficient evidence for sum-chain changes.
- **Config flow / sensor / setup change**: layer-2 tests + manual test on a
  real HA instance before merge.
- **Escaped defect (any severity)**: a named regression test pinned to the
  defect, cross-referenced in AGENTS.md.
- **Docs / CI-only change**: green CI is the definition of done.

## Coverage floor

Set `--cov-fail-under` in `ci.yml` once the surviving test suite has a
stable baseline post-strip (check actual coverage after Phase 1 lands; the
line lived at 89% in `haggle` but that number is meaningless carried over
verbatim to a much smaller, stub-heavy codebase). Treat it as a ratchet —
moves up as the total rises, never lowered to make a PR pass.

## When live-HA manual testing is required

Before merge: config-flow, sensor, and coordinator changes that touch real
AGL auth or data get a manual test on a real HA instance with a real AGL
gas account, until a volunteer/beta-tester process exists to cover this
(see `haggle`'s `docs/testing.md` for how that scales once the project has
external users).

## Fixtures

Committed fixtures use the canonical anonymised placeholders
(`1234567890` / `9999999999` / `1 Sample Street SUBURB QLD 4000`). Never
commit a capture with real customer identifiers — see
`tests/fixtures/PROVENANCE.md` and AGENTS.md § Adding a New Endpoint.
