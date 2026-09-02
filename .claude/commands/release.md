# /release

Cut a release by merging the standing release-please PR and tagging it.

## Usage

```
/release [expected-version]
```

`expected-version` is optional — release-please computes the version from
Conventional Commits merged to `main`. If given, it's used only as a
sanity check against the version the open release-please PR actually
proposes; a mismatch stops the command rather than silently overriding it.

Example:
```
/release
/release 0.2.0
```

## Pre-conditions (checked before proceeding)

1. Working tree is clean (`git status --porcelain` returns empty).
2. On `main` branch.
3. Latest CI run on `main` is green (`gh run list --branch main --limit 1`).
4. A release-please PR is open (`gh pr list --search "head:release-please--branches--main"`).
   If none is open, there's nothing to release — report that and stop.
5. If `expected-version` was given, it matches the version in that PR's
   diff of `custom_components/gaggle/manifest.json`. Mismatch stops the
   command.

If any pre-condition fails, report the failure and stop.

## Delegates to

The `release-manager` subagent, providing it the release-please PR number
found above. release-manager verifies CI on that PR, merges it (squash),
reads back the version release-please landed in `manifest.json`, then
creates a **signed tag on the squash-merge commit** and pushes it.

## After completion

Print the GitHub Release URL and confirm the seven attested assets exist
(`gaggle.zip` + provenance/SBOM sigstore bundles + SBOMs +
`check-runs.json`); verify with `gh attestation verify`.
