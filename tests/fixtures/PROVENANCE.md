# Fixture provenance

All fixtures in this directory are synthetic or anonymised to the canonical
placeholders (`1234567890` / `9999999999` / `1 Sample Street SUBURB QLD
4000`). None are real captures at this time.

Rule for future fixtures: a real capture requires (1) zero direct
identifiers, (2) a documented reconciliation purpose that anonymised data
cannot serve, and (3) a provenance entry here linking the account holder's
own public contribution (or recording their explicit consent). Otherwise
use the placeholders.

Gas usage fixtures specifically are blocked on a live capture against a
real AGL gas account (Phase 0 — see docs/gas-api.md) before any can be
added; until then, `agl/client.py`'s gas usage-fetch methods stay explicit
stubs with no fixture to test against.
