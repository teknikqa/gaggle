# Energy dashboard setup

Gaggle feeds your AGL gas billing history into Home Assistant as an
**external statistic** — `gaggle:consumption_<contract>` — carrying real
usage totals for each completed billing period. This, not the sensor
entities, is what belongs in the Energy dashboard.

> **The one rule:** in the Energy dashboard, always pick the
> `gaggle:consumption_<contract>` statistic. Never pick a `sensor.…`
> entity. The sensor entities update once per poll, so the dashboard
> would attribute a period's usage to the poll hour — one bar, on the
> wrong day.

## What "normal" looks like: sparse, not daily

**A basic (non-smart) gas meter has no interval or daily data.** AGL only
exposes a current-period estimate and a window of already-billed past
periods — there's no underlying data to build a smooth daily chart from.
So the Energy dashboard gets **one bar per completed billing period**,
typically every ~2 months (bimonthly billing), not one bar per day. Don't
expect the same granularity `haggle` (the electricity sibling) provides.

If you have a smart-metered gas account and it turns out to expose
interval data, that's not yet supported — see
[`docs/gas-api.md`](./gas-api.md) for the current state.

## Which source to add

Find your exact statistic ID under **Developer Tools → Statistics** (filter
"gaggle"). `<contract>` is your AGL contract number.

| Statistic | Add as |
|---|---|
| `gaggle:consumption_<contract>` | Energy dashboard *Gas consumption* source |
| `gaggle:cost_<contract>` | Used by the dashboard's cost tracking, if enabled |

## What the sensor entities are for

The sensors are for at-a-glance values, dashboard cards, and automations —
not for the Energy dashboard:

| Sensor | What it shows |
|---|---|
| **Consumption** | Cumulative usage ever imported (mirrors the statistic's running total). |
| **Consumption this period / Consumption cost** | AGL's own current-period ESTIMATE — not a meter read. Updates roughly daily; only becomes "real" once the period completes and lands in the statistic. |
| **Bill projection** | AGL's own forecast for the full current bill. |
| **Unit rate / Supply charge** | Your plan's rate (AUD/MJ) and daily supply charge. Gas plans are usually tiered — the unit rate sensor reads the highest ("Thereafter") tier as a simplification; it may not match your actual marginal rate if you're a light user who stays in a lower tier. |

## Data timing

- The current-period sensors are AGL's estimate, updated roughly daily —
  don't expect them to move in real time.
- A new statistic bar appears once AGL closes out a billing period, which
  the integration picks up on its next poll after that happens.
- Re-polling never double-counts: imports are idempotent per
  `(statistic_id, period)`.

## Troubleshooting

**A billing period shows as one big bar, instead of daily bars.**
Expected — see "What normal looks like" above. This isn't a bug.

**The dashboard shows nothing at all yet.**
New installs backfill whatever periods AGL currently returns (about 5,
roughly a year) on first poll. If it's still empty after a day, check
`home-assistant.log` for `custom_components.gaggle` warnings.

**Suspect a recently-updated Gaggle version rather than your dashboard
config?** See [releasing.md](./releasing.md) once a release exists to roll
back to.
