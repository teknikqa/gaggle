# Diagnostics

Gaggle supports Home Assistant's built-in diagnostics download. When filing
a bug, attaching this file answers most triage questions (version, plan
type, backfill state, timezone) in one step.

## How to download

**Settings → Devices & Services → Gaggle → ⋮ (three-dot menu) →
Download diagnostics.** Drag the resulting `.json` file into the
"Diagnostics file" box of the
[bug report form](https://github.com/teknikqa/gaggle/issues/new?template=bug.yml).

## What is (and isn't) in the file

The file is built to be posted publicly:

| Data | Treatment |
|---|---|
| AGL refresh token | **Redacted** (`**REDACTED**`) — never included. |
| Account number / contract number | **Never included.** Replaced everywhere (including inside statistic IDs and the entry unique_id) by stable anonymous references like `anon-3f9c2a81d0`. References are HMAC-keyed to your Home Assistant install's private instance id, so the same install always produces the same reference (repeat reports correlate) but the number cannot be recovered. |
| TLS SPKI pins | Reduced to presence booleans (`pin_present_auth` / `pin_present_bff`). |
| Usage figures, rates, timestamps | Included — they are the diagnostic payload and are not personally identifying. |
| HA core / Python / OS versions | Added automatically by Home Assistant's diagnostics wrapper (`home_assistant` block). |

## Schema field reference

The integration's payload is under the standard HA wrapper's `"data"` key.
`schema_version` gates parsing — if it is missing or greater than the
version documented here, treat the file as opaque JSON.

| Field | Meaning | Diagnostic signal |
|---|---|---|
| `schema_version` | Payload shape contract (currently `DIAGNOSTICS_SCHEMA_VERSION` in `custom_components/gaggle/diagnostics.py`). | Gate parsing on it. |
| `integration.version` | Installed Gaggle version. | Satisfies the "Gaggle version" triage check. |
| `contract_ref` / `account_ref` | Stable anonymous install identifiers (HMAC-keyed per install). | Correlate multiple reports from the same install. |
| `runtime_available` | Whether setup succeeded far enough to have runtime state. | `false` → the setup failure itself is the bug (auth/network); don't chase data-shape theories. |
| `timezone` | HA's configured timezone. | Timezone-sensitive bug classes (e.g. wrong-day imports) hinge on this. |
| `entry.pin_present_auth` / `entry.pin_present_bff` | TOFU TLS pins captured? | `false` on both → entry predates pinning or Reconfigure never ran. |
| `coordinator.last_update_success` | Did the most recent poll succeed? | `false` → look at auth/network before data-shape theories. |
| `coordinator.last_exception` | Message of the most recent failed update (body-scrubbed at raise time). | Distinguishes rate-limit vs auth vs transport. |
| `coordinator.bill_period_start` | Start date of the current AGL bill period (last seen). | Required context for any "period sensor ≠ app tile" report. |
| `statistics.<series>.first_date` / `last_date` / `row_count` / `last_sum` | Coverage and baseline health per statistics series. | Gaps, stalls, or baseline mismatches show up here first. |

The `<series>` keys are the real statistic IDs with the contract number
replaced by `contract_ref` — e.g. `gaggle:consumption_anon-3f9c2a81d0`.

**When the shape changes:** bump `DIAGNOSTICS_SCHEMA_VERSION` in
`custom_components/gaggle/diagnostics.py` and update this table in the same
PR.
