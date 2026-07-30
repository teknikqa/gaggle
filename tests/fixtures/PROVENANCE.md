# Fixture provenance

All fixtures in this directory are synthetic or anonymised to the canonical
placeholders (`1234567890` / `9999999999` / `1 Sample Street SUBURB QLD
4000`).

Rule for future fixtures: a real capture requires (1) zero direct
identifiers, (2) a documented reconciliation purpose that anonymised data
cannot serve, and (3) a provenance entry here linking the account holder's
own public contribution (or recording their explicit consent). Otherwise
use the placeholders.

## Real captures

- **`gas_usage_basic_response.json`**, **`gas_plan_response.json`**
  (2026-07-30): real captures from the project maintainer's own AGL gas
  account (mitmproxy capture, macOS, against the AGL app's iPad build via
  Apple Silicon compatibility — Phase 0, see `docs/gas-api.md`). The
  maintainer is the account holder and directed the capture; the contract
  number is replaced by the canonical placeholder (`9999999999`)
  everywhere it appears, including inside embedded URLs. No account
  number, address, or other Class B identifier appears in either response
  (the `usage/basic/Gas` and `plan/energy` endpoints don't return them).
  Usage/cost figures (Class C — operational data) are kept real since they
  are the reconciliation evidence for "this field is what it claims to
  be" — not personally identifying on their own, per
  `docs/threat-model.md` §2. This is the confirmed real shape referenced
  throughout `AGENTS.md` § AGL API — Key Facts.
