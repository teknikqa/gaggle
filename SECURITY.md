# Security Policy

`gaggle` is a pre-release sibling of
[`haggle`](https://github.com/NaanyaBiz/haggle) (AGL electricity → HA Energy
dashboard). This document is intentionally lighter than haggle's — it covers
the essentials for a project at this stage; expect it to grow as the project
matures (see `haggle`'s `SECURITY.md` for the level of detail a mature
single-maintainer HACS integration eventually needs: risk-acceptance
register, Scorecard posture, supply-chain gating, continuity plan).

## Reporting a Vulnerability

Please report suspected security issues **privately** via either of:

1. **GitHub Private Security Advisories** —
   <https://github.com/NaanyaBiz/gaggle/security/advisories/new>
2. **Email** — `security@naanya.biz`.

Please do **not** open a public issue for security reports. We aim to
acknowledge reports within 5 business days.

## Scope

In scope:
- The Python code under `custom_components/gaggle/` and `tests/`.
- The CI workflows under `.github/workflows/`.
- The documented HACS install path.

Out of scope:
- Issues in upstream Home Assistant, `aiohttp`, or `cryptography` (report to
  those projects directly).
- Issues in AGL Energy's API itself — this is an unofficial client of an
  undocumented endpoint with no privileged relationship with AGL.
- Vulnerabilities requiring already-compromised local code execution on the
  HA host (the threat model assumes the HA process itself is trusted).

## Threat Summary

- **Auth**: Auth0 PKCE through the user's real browser (no portal scraping,
  no credential handling by the integration). Refresh token rotates on every
  use; access token is memory-only with a 15-minute expiry.
- **Storage**: the OAuth refresh token persists in HA's config-entry data
  (`.storage/core.config_entries`), which is plaintext JSON on disk on every
  HA install type — that's a platform ceiling (HA offers integrations no
  vault API), not a gap specific to this integration. If that concerns you,
  enable full-disk encryption on the HA host.
- **TLS**: Trust-On-First-Use SPKI pinning against AGL's auth and data
  hosts, captured during the config flow. Mismatch is warn-only (a
  persistent notification fires) rather than a hard failure, so a
  legitimate AGL cert rotation doesn't brick installs.
- **Supply chain**: `manifest.json` ships zero runtime requirements —
  everything imported at runtime (`aiohttp`, `voluptuous`, `cryptography`)
  is vendored by Home Assistant core itself.

See `docs/threat-model.md` for more detail; it will grow alongside the
project.

## Credential Exposure Response

If a secret (a refresh token, a real API capture) ever lands in a commit:

1. Treat it as compromised immediately.
2. Revoke: re-run the integration's Reconfigure/PKCE flow (Auth0's rotation
   invalidates the leaked refresh token); anything else, revoke at its
   issuer.
3. Rewrite the affected history before pushing; if it already reached the
   public repo, rewrite anyway and treat the value as public forever.
4. Re-scan full history (`gitleaks git .`) and require zero findings.
5. If any user could be affected, publish a GHSA advisory.

## Coordinated Disclosure

If you find a vulnerability that affects users on production HA instances,
please contact us privately first and allow at least 14 days before public
disclosure.

## Hall of Fame

If you reported an issue that landed in a release, you'll be listed here
unless you ask otherwise.

_(none yet — be the first.)_
