# No Wick Retest — implementation notes

**File:** `no_wick_retest.pine` (Pine Script **v6**, indicator, `overlay=true`)
**Origin:** rebuilt from the settings + dashboard screenshots of "No Wick Retest"
by mogodfrey (https://www.tradingview.com/v/XvrNGxNk/).

The original script is protected/closed-source, so none of its code was used or
available. Everything here is derived from the visible input list and the
dashboard rows only. The *structure* (inputs, groups, dashboard metrics, state
machine) matches the screenshots; the *internal maths* is my own model, so the
statistics will not reproduce the original tick-for-tick.

---

## Trade model

1. **No-wick candle** — a candle with no wick on one side:
   * long level: `open == low` (no lower wick) → level = the low/open
   * short level: `open == high` (no upper wick) → level = the high/open
   * `Require Directional No-Wick Candle` additionally demands the body agrees
     (bull candle for a long level).
   * Equality uses a half-tick tolerance and rejects zero-range bars.
2. **Pull-away** — price must travel `Minimum Pull-Away Before Retest (ATR)`
   × ATR(14) away from the level before a touch counts as a retest. Without this
   a level that price never left would "retest" itself immediately.
3. **Retest / arm** — first touch back at the level arms the setup and (in
   `Freeze at Arming` mode) freezes the structural swing used for the stop.
4. **Entry** — per `Entry Model`:
   * `Touch (Immediate)` — filled at the level on the touch bar.
   * `Confirmation Candle` — any bar from the arming bar up to expiry whose
     close satisfies the enabled confirmations; filled at that close.
   * `Confirmation + Level Hold` — as above, but the confirmation bar must be a
     later bar that held the level (long: `low >= level`).
5. **Expiry** — `Maximum Candles to Retest` bars after the no-wick candle, the
   setup is dropped and `Last Rejection` reads `Expired after N candles`.
   Every setup therefore ends as an entry, a bad stop, or an expiry — which is
   why `Setups = Entries + Expired + Bad Stop` on the dashboard.

### Filters (all evaluated at entry, not at level creation)
Confirmations → day filter → session blocks → trend filters → free trade slot →
valid structural stop. The first failure is what `Last Rejection` shows, and
`Show Rejection Diagnostics` prints it on the bar.

### Risk
* Stop structure: recent swing pivot (`Swing Pivot Strength`, searched over the
  last `Closest Swing Search` confirmed pivots, picked by `Swing Selection`),
  or the no-wick candle, the signal candle, or the level itself.
* `raw = |entry − structure| + Stop Offset ticks`, `stop = raw × Stop Multiple`,
  `target = raw × Target Multiple` → dashboard header shows the resulting R
  multiple (1R with the screenshot defaults).
* `Move Stop Beyond Breakeven At X%` pushes the stop to
  `entry ± Profit Lock ticks` once price has travelled X% of the way to target.
  A trade closed on that stop is a **Locked** outcome, not a win or a loss.
* Fills are conservative: a bar that touches both stop and target is scored as a
  stop, and the breakeven move is applied *after* the exit test on that bar.

---

## Dashboard maths

| Row | Definition |
|---|---|
| TP Win Rate | `wins / closed` |
| Positive Exit Rate | `(wins + locked) / closed` |
| Profit Factor (Gross) | `Σ positive R / Σ negative R`, before costs |
| Gross Net Profit | `Σ R` before costs |
| Estimated Costs | `closed × (round-trip fees + 2 × slippage ticks × tick value) × qty / $ per 1R` |
| Net After Costs | gross − costs (this is the curve everything below uses) |
| Max Closed Drawdown | peak-to-valley of the net closed-trade R curve, and `× $ per 1R` |
| Prop DD Used | `drawdown $ / Account Max Drawdown` |
| DD Cushion Remaining | `Account Max Drawdown − drawdown $` (negative = the account would have blown) |
| Max $/R @ Hist. DD | `Account Max Drawdown / drawdown R` — the largest $ risk per trade this history would have survived |
| Worst Loss Streak | longest run of consecutive full stop-outs (locked exits reset it) |
| Entries / Active Day | entries ÷ calendar days on which at least one entry fired |
| NY AM / NY PM / Overnight | bucketed by **entry** time in `Performance Timezone`: 09:30–12:00, 12:00–16:00, everything else |

Session buckets and the session/day filters are independent: the filters use
`Session Filter Timezone`, the statistics use `Performance Timezone`.

---

## Deliberate implementation choices

* **Confirmed bars only.** The whole engine runs under `barstate.isconfirmed`,
  so nothing repaints — but it also means intrabar fills are approximated from
  bar highs/lows at the close.
* **Indicator, not strategy.** The dashboard needs "Locked" as a third outcome
  and R-denominated stats, which is simpler to own outright than to read back
  out of `strategy.closedtrades`. Automation goes out through `alert()` JSON
  instead of broker orders.
* **`Signal / Execution Timeframe` is a guard, not a `request.security()` call.**
  Running a stateful setup/trade machine inside `request.security` is where this
  class of script normally breaks (var state, repainting). Instead the engine
  only runs when the chart timeframe equals the input, and the dashboard Status
  row plus an on-chart label say so when it doesn't.
* **ATR is fixed at 14** — the screenshots expose ATR-based inputs but no ATR
  length input.

## Ghost webhook payload

`Enable Ghost JSON Webhook Alerts` emits on entry, on the profit-lock stop move
and on exit. Create one alert on the indicator with **Any alert() function call**:

```json
{"ticker":"NQ1!","exchange":"CME_MINI","strategy":"NO_WICK_RETEST","action":"entry",
 "side":"long","quantity":1,"price":20150.25,"stop":20125.75,"target":20174.75,
 "tradeId":"NWR-42","timeframe":"15","note":"no-wick retest","time":"2026-08-25 13:45:00"}
```

`action` is one of `entry` / `modify` / `exit`.

---

## Inputs still unknown

The screenshots stop after `Style → Bearish Color`, and a few dropdowns are
truncated in the images. Where the option list was cut off I chose a set that
fits the visible default:

| Input | Visible | Options used here |
|---|---|---|
| Entry Model | `Confirm…` | Touch (Immediate) / Confirmation Candle / Confirmation + Level Hold |
| Stop-Loss Structure | `Recent …` | Recent Swing Pivot / No-Wick Candle Extreme / Signal Candle Extreme / No-Wick Level |
| Swing Selection | `Most Re…` | Most Recent / Most Extreme / Closest to Entry |
| Swing Anchor Timing | `Freeze …` | Freeze at Arming / Live at Entry |
| Stop / Target Distance | `1` | 0.5 / 0.75 / 1 / 1.25 / 1.5 / 2 / 2.5 / 3 |
| Move Stop Beyond Breakeven At | `75%` | Off / 25% / 50% / 60% / 75% / 90% |

If the missing screenshots show different option lists (or extra groups after
`Style`), they can be swapped in without touching the engine.
