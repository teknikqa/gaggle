# Release acceptance policy

Mechanics: [`release-please`](https://github.com/googleapis/release-please)
(`.github/workflows/release-please.yml`) watches Conventional Commits on
`main` and maintains a standing PR that bumps
`custom_components/gaggle/manifest.json`'s `version` and generates the
matching `CHANGELOG.md` section. It never tags or creates a GitHub Release
itself (`skip-github-release` in `release-please-config.json`) — merging
that PR (squash, like any other PR) just lands the version bump on `main`.
A human then signs and pushes the release tag exactly as before (see
`.claude/agents/release-manager.md`), which is what `release.yml` actually
gates on and publishes from. `release.yml` marks any tag containing `-` as
a prerelease.

This is a lighter version of `haggle`'s release policy, appropriate for a
pre-release project with no shipped stable tag yet. Grow it (a formal
acceptance-evidence record, a beta channel) as gaggle picks up real users —
`haggle`'s `docs/releasing.md` is the reference for what that looks like at
maturity.

## Before the first release

The gas usage endpoint is implemented against a real captured API contract
(`docs/gas-api.md`) — that gate is cleared. No stable or beta tag should
ship until:

1. At least one full billing period on a real account (beyond the
   maintainer's own, which the Phase 0 capture already validated)
   reconciles against the AGL app or a real gas bill to within the API's
   own rounding.
2. CI is green: ruff, mypy, pytest, hassfest, HACS validation.

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
