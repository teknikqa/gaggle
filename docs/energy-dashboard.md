# Energy dashboard setup

> **Not yet functional.** Gas usage data isn't flowing yet — see the README
> status note and `docs/gas-api.md`. This doc describes the intended setup
> once Phase 0 (real API capture) lands, so it's ready to go at that point.

Gaggle feeds your AGL gas smart-meter history into Home Assistant as
**external statistics** — series named `gaggle:…` that carry your real
usage history, written to the periods the gas was actually used. These,
not the sensor entities, are what belongs in the Energy dashboard.

> **The one rule:** in the Energy dashboard, always pick a `gaggle:…`
> statistic. Never pick a `sensor.…` entity. The sensor entities update
> once per daily poll, so the dashboard would attribute a whole day's usage
> to the poll hour — one big bar, on the wrong day.

## Which sources to add

Find your exact statistic ID under **Developer Tools → Statistics** (filter
"gaggle"). `<contract>` below is your AGL contract number.

| Statistic | Add as |
|---|---|
| `gaggle:consumption_<contract>` | Energy dashboard *Gas consumption* source |
| `gaggle:cost_<contract>` | Used by the dashboard's cost tracking, if enabled |

## What the sensor entities are for

The sensors are for at-a-glance values, dashboard cards, and automations —
not for the Energy dashboard: current billing-period usage/cost,
cumulative totals, unit rate, and supply charge.

## Data timing — what "normal" looks like

Once real gas data flows, expect similar timing characteristics to
`haggle` (AGL's electricity sibling): a lag between "today" and the latest
available data, and a throttled backfill on first install. The exact
numbers depend on what Phase 0 discovers about gas data cadence (daily vs
basic-meter billing-period reads) — this section will be filled in once
that's known.

## Troubleshooting

**A whole day shows as one big bar, on the wrong day.**
The dashboard is charting a `sensor.…` entity instead of the `gaggle:…`
statistic. Remove the sensor from the dashboard's sources and add the
statistic (see the table above).

**Recent days are missing.**
Once implemented: check `home-assistant.log` for
`custom_components.gaggle` warnings and open an issue if it persists.
