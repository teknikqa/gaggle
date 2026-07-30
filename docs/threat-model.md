# Threat Model — gaggle

**Status**: living document, intentionally lightweight while the project is
pre-alpha (gas usage fetch is a stub — see `docs/gas-api.md`). Re-review
once real gas data starts flowing, and again before any HACS submission.
`haggle`'s `docs/threat-model.md` shows the level of detail this should grow
into (STRIDE register, AI-agent grant analysis, resilience targets) as the
project matures — port from there rather than re-deriving from scratch.

## 1. System description

Gaggle is a Home Assistant (HA) custom integration that will pull
smart-meter gas data from AGL Energy's (Australia) undocumented mobile-app
API and feed it into the HA Energy dashboard via recorder long-term
statistics. Distributed via HACS; runs entirely inside the user's own HA
process; ships zero third-party runtime packages (`manifest.json`
`"requirements": []`).

Core data flow (auth and contract discovery work today; the usage fetch is
a stub):

    HA user browser  →[PKCE callback URL paste]→  config_flow.py
    config_flow.py   →[POST /oauth/token, PKCE]→  AGL Auth0 (secure.agl.com.au)
    AGL Auth0        →[access + rotating refresh token]→  config_flow.py
    config_flow.py   →[persists refresh_token]→   HA config entry (.storage, plaintext JSON)
    AglAuth          →[refresh grant, JIT]→        AGL Auth0
    AglAuth          →[Bearer JWT, 15-min]→        AGL BFF (api.platform.agl.com.au)
    AGL BFF          →[overview + plan JSON]→      GaggleCoordinator (parser: total over arbitrary JSON)
    AGL BFF          →[gas usage — NOT YET IMPLEMENTED]→  GaggleCoordinator
    Coordinator      →[StatisticData rows]→        HA recorder (idempotent on (statistic_id, start))

Attacker-relevant properties (carried over from `haggle`, apply identically
here since it's the same AGL mobile API surface):

- `gaggle` impersonates the AGL iOS app (shared public `client_id` + header
  set in `const.py`); the refresh token is the long-lived credential and
  rotates on every use.
- Both AGL hosts are TLS-pinned Trust-On-First-Use by SPKI hash; mismatch is
  warn-only by design (a strict reject would brick users on legitimate cert
  rotation), so AGL response JSON is treated as attacker-influenceable and
  the parser aims to be total over arbitrary JSON.
- HA typically shares a LAN with IoT devices: LAN adjacency is a realistic
  attacker position for the initial PKCE flow.
- HACS distribution makes supply-chain compromise a multi-victim event —
  the one factor worth grading above the project's otherwise low-impact
  consequence class.

## 2. Data classification

| Class | Data | Where it may live | Requirements |
|---|---|---|---|
| **A — secret** | AGL/Auth0 refresh token (rotating); access token (15-min JWT) | refresh token: `entry.data` only; access token: memory only | Never committed, logged, or serialized. Diagnostics redact it; secret scanning guards commits (pre-commit gitleaks + GitHub push protection + CI full-history gitleaks). Error bodies are stripped before exceptions propagate. |
| **B — personal** | account number, contract number, service address, meter-read timeseries | the user's own HA instance | Never in the repo — fixtures use canonical placeholders (`1234567890` / `9999999999` / `1 Sample Street SUBURB QLD 4000`). HMAC-anonymised in diagnostics, including inside composite strings. Never in exception text (BFF URLs carry the contract number — strip before raising). |
| **C — operational** | usage figures, rates, timestamps, SPKI-presence booleans | diagnostics, statistics, logs | Permitted — not personally identifying on its own. |
| **D — public** | code, docs, CI config | repo | Normal review. |

## 3. Trust boundaries

| Boundary | Control |
|---|---|
| AGL HTTPS API → HA coordinator | TLS + Trust-On-First-Use SPKI pinning |
| HA user browser → config flow | OAuth state nonce + PKCE S256 |
| AGL JSON → HA recorder/statistics | Allowlist-style parsing; numeric values clamped to non-negative finite floats |
| GitHub Actions → HACS installers | Actions SHA-pinned; release artifacts to be attested once a release flow ships |
| HA diagnostics → public GitHub issue | Built to be public: refresh token redacted, account/contract HMAC-anonymised |

## 4. Known residual risks (honest bounds)

- **Refresh token storage**: plaintext JSON in HA's config-entry store on
  every install type. Platform ceiling — HA offers integrations no vault
  API. Mitigated by short-lived access tokens and rotate-on-use refresh
  tokens, not eliminated.
- **First-install MITM**: a LAN attacker present during the initial PKCE
  flow could pin their own certificate (TOFU). Requires compromising both
  the user's browser and HA host simultaneously to matter.
- **Single-maintainer governance**: no independent code review, no second
  responder. Same shape as `haggle`'s accepted risk; not re-litigated here
  in detail while the project is pre-alpha — revisit before any HACS
  submission.
- **Gas API contract unverified**: the entire usage-fetch path is unbuilt
  pending a real device capture (Phase 0). Until then there's no attack
  surface there to model beyond "don't guess at the endpoint" — see
  `docs/gas-api.md`.
