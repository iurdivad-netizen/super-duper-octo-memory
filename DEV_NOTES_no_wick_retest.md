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
3. **Retest / arm** — the first touch back at the level arms the setup.
4. **Entry** — per `Entry Model` (all four options are the real dropdown list):
   * `Confirmation Close` *(default)* — the first bar from the arming bar to
     expiry whose close satisfies the enabled confirmations; filled at that close.
   * `Armed Level Retest` — that confirmation close only **arms** a limit at the
     level; the fill happens when a *later* bar trades back to the level, at the
     level. This is the model `Show Armed Labels` is really for.
   * `Rejection Close` — the bar must wick into the level and close back out of
     it with the rejection wick ≥ 50% of the bar's range, plus the enabled
     confirmations; filled at that close.
   * `Immediate Level Touch` — filled at the level on the retest bar, no close
     required.
5. **Expiry** — `Maximum Candles to Retest` bars after the no-wick candle, the
   setup is dropped and `Last Rejection` reads `Expired after N candles`.
   Every setup therefore ends as an entry, a bad stop, or an expiry — which is
   why `Setups = Entries + Expired + Bad Stop` on the dashboard.

### Where each filter runs
`Use No-Wick MA Location Filter` gates the **level**, so it runs when the no-wick
candle forms: a level on the wrong side of its direction's MAs never becomes a
setup at all. Everything else runs at entry. This matters for the dashboard —
it roughly halves `No-Wick Setups`, and it keeps "wrong side of MAs" out of
`Last Rejection`, which is why the original's last rejection is an expiry.

`Use MA Ribbon Filter` requires the entry price to be clear of the whole ribbon
(above all five MAs for a long), not that the five MAs are perfectly stacked —
stacking is a far rarer condition and starves the entry count.

### Filter order at entry
Confirmations → day filter → session blocks → trend filters → free trade slot →
valid structural stop. The first failure is what `Last Rejection` shows, and
`Show Rejection Diagnostics` prints it on the bar.

### Risk
* Stop structure:
  * `Recent Swing` — nearest qualifying confirmed pivot, searched over the last
    `Closest Swing Search` pivots and picked by `Swing Selection`
    (`Most Recent Swing` or `Closest Swing by Price`).
  * `Recent CHOCH` — the swing the last change-of-character came from (for a
    long: the swing low that preceded the bullish CHOCH break).

  These are the only two options in the real dropdown. Both fall back the same
  way when the chosen structure is missing or no longer beyond the entry price:
  frozen → live equivalent → nearest qualifying swing.
* `Swing Anchor Timing`: `Freeze at Setup` captures the structure (both the
  swing and the CHOCH swing) on the no-wick candle itself so it cannot drift
  while the setup waits; `Recalculate at Entry` re-reads it on the entry bar.
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
| Estimated Costs | per trade: `fees × qty / $ per 1R` **+** `2 × slippage ticks × mintick / stop distance` |
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

### Why costs are split that way
Fees are a cash cost, so they belong against the cash value of 1R. Slippage is a
*price* cost, so it belongs against the trade's own stop distance — that ratio
is position-size independent, which is the whole point of scoring in R.
Charging slippage as `ticks × dollar tick value ÷ $per1R` instead mixes the two
and overstates costs by ~10× on a tick-heavy instrument (it silently assumes the
position was sized so that the stop distance equals exactly $1R).

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

## Calibration against the original

Same chart, same settings, 2025-09-30 → 2026-08-25. "v1" is the first build,
"v2" after moving the MA location filter to level creation, relaxing the ribbon
filter and fixing the cost model, "v3" after setting the MA location line to the
fast/slow midpoint.

| Row | v1 | v2 | v3 target | Original |
|---|---|---|---|---|
| No-Wick Setups | 803 | 303 | ~408 | 408 |
| Confirmed Entries | 38 | 105 | | 126 |
| Positive Exit Rate | 55.26% | 62.86% | | 63.49% |
| Entries / Active Day | 1.06 | 1.13 | | 1.18 |
| Estimated Costs | 4.16R | 2.09R | | 1.36R |
| Gross Net Profit | 0.01R | 15.05R | | 11.11R |

### What the remaining gap says
The cost row is a usable probe of the average stop distance, because slippage is
charged as `2 × slipTicks × mintick / stopDistance`. Backing that out:

* ours: `(2.09/105 − 0.0095) = 0.0104R` per trade → average stop ≈ **192 ticks**
* original: `(1.36/126 − 0.0095) = 0.0013R` per trade → average stop ≈ **1540 ticks**

So the original's structural stops are roughly **8× wider** than ours on the same
data. That single difference also explains the rest of the profile: wider stops
take longer to travel 75% of the way to target, which is why the original shows
more `Locked` exits (18.3% of closed trades against our 11.4%) and a lower TP
win rate (45.2% against our 51.4%), and why its drawdown is larger in R.

The suspect is what counts as a swing. With `Swing Pivot Strength 1` I take
every minor 1-bar pivot, so for a long the nearest pivot low under the level is
often one or two bars back. A stop 8× wider implies the original qualifies
swings at a higher structural degree — the phrase "Confirmed Pivots" in
`Closest Swing Search (Confirmed Pivots)` may mean pivots confirmed by a
structure break (the ones that produced BOS/CHOCH), not merely confirmed by the
pivot lookback. Reading one stop level off each indicator's R/R tool on the same
setup settles it, which is cheaper than guessing.

## Inputs still unknown

Every dropdown in the Entry Model and Risk Management groups has now been
confirmed from screenshots and is implemented verbatim. The only open items are
whether `Stop / Target Distance` continues past `2` (the crop ends there — the
list here follows the observed 0.25 step up to 3) and whether any input group
exists after `Style → Bearish Color`.

| Input | Status | Options used here |
|---|---|---|
| Entry Model | **confirmed** | Confirmation Close / Armed Level Retest / Rejection Close / Immediate Level Touch |
| Swing Selection | **confirmed** | Most Recent Swing / Closest Swing by Price |
| Swing Anchor Timing | **confirmed** | Freeze at Setup / Recalculate at Entry |
| Stop-Loss Structure | **confirmed** (list ends at `Recent CHOCH`) | Recent Swing / Recent CHOCH |
| Stop / Target Distance | confirmed to `2`, screenshot cut off there | 0.25 steps, 0.5 → 3 |
| Move Stop Beyond Breakeven At | **confirmed** | Off / 25% / 50% / 75% / 85% / 90% |

If the missing screenshots show different option lists (or extra groups after
`Style`), they can be swapped in without touching the engine.
