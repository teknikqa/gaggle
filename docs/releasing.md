# Release acceptance policy

Channel model: every MINOR ships as `vX.Y.0-beta.N` prereleases on the HACS
beta channel first, then promotes to stable with zero code diff. PATCH
releases (hotfixes) may skip the ladder only under the hotfix rule below.
`release.yml` marks any tag containing `-` as a prerelease.

This is a lighter version of `haggle`'s release policy, appropriate for a
pre-release project with no shipped tag yet. Grow it (beta-soak duration
requirements, a formal acceptance-evidence record) as gaggle picks up real
users — `haggle`'s `docs/releasing.md` is the reference for what that looks
like at maturity.

## Before the first release

The gas usage endpoint is implemented against a real captured API contract
(`docs/gas-api.md`) — that gate is cleared. No stable or beta tag should
ship until:

1. At least one full billing period on a real account (beyond the
   maintainer's own, which the Phase 0 capture already validated)
   reconciles against the AGL app or a real gas bill to within the API's
   own rounding.
2. CI is green: ruff, mypy, pytest, hassfest, HACS validation.

## Hotfix rule (stables that skip the ladder)

A PATCH stable fixing a severe defect may ship without a beta soak ONLY
with recorded validation evidence in the release PR: what was verified,
against what ground truth, on which HA version. "CI is green" alone is not
validation evidence for a statistics-path fix.

## Downgrade test (once per stable line)

Before or with each stable `vX.Y.z`, run one manual downgrade test from the
new version to the previous stable and record the result in the release PR
+ CHANGELOG:

1. On an HA instance running the new version: note the last poll time and
   current Energy-dashboard totals.
2. HACS → Gaggle → ⋮ → Redownload → select the previous stable → restart
   HA.
3. Verify: config entry loads (no repair/setup error), a manual poll or the
   next scheduled poll succeeds, totals unchanged (no double-count —
   imports are idempotent on `(statistic_id, start)`).
4. Redownload back to the new version → restart → verify the entry loads
   cleanly.
