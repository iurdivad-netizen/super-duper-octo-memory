# Momentum Run — consecutive-candle continuation

**Files:** `momentum_run_strategy.pine` (Pine v6, `strategy()`, `overlay=true`),
`backtest_momentum_run.py` (base-rate probe over `data/`)

The ask: take N consecutive same-colour candles, enter one tick beyond the last
candle's extreme on the continuation, stop at the candle's other extreme, target
1.5R.

It is straightforward to build. The reason this document leads with arithmetic
rather than with the code is that the arithmetic says the trade model is, on the
evidence available here, a coin flip with a commission attached — and the code
is only useful if it is used to test that rather than to decorate it.

---

## 1. The number the strategy has to beat

The stop and the target are both defined off the same candle. That makes the
bracket symmetric in R by construction:

- risk       = signal candle range + 2 ticks
- reward     = 1.5 × that

For a driftless random walk, the probability of touching `+kR` before `-1R` is
`1 / (1 + k)`. At k = 1.5 that is **40.0%**. So a 1.5RR bracket is not a
favourable structure and not an unfavourable one — it is a fair bet, and the
entire question is whether "N same-colour candles, then the high breaks" shifts
the hit rate above 40%.

It has to shift it above 40% *by enough to pay for friction*. Friction as a
fraction of R is the part that gets overlooked, because R here is one candle
range, which on a fast chart is small:

| Instrument / TF | Median R | ~Round-trip cost | Cost as % of R | Break-even hit rate |
|---|---|---|---|---|
| ES 15m | 25 ticks | ~3 ticks | 12% | 44.8% |
| ES 3m  | 12 ticks | ~3 ticks | 25% | 50.0% |
| SPY 1D | ~$4.57   | ~$0.03   | <1% | 40.3% |

On ES 3m the required hit rate is 50% against a 40% null. That is a 25% relative
improvement in accuracy demanded from the pattern alone. **The faster the chart,
the more the strategy is a bet on the broker rather than on the market.**

## 2. What the data says

`backtest_momentum_run.py` implements exactly the trade model above over the
CSVs already in `data/`. Intrabar ties (a bar whose range contains both stop and
target) are resolved conservatively — stop wins. `--optimistic` flips that; the
gap between the two runs is 0.5–3% of trades on ES and EURUSD, so the assumption
is not what produces the result.

Target 1.5R, break-even 40.0%, entry order valid for one bar:

| Market | N | Filled | Fill rate | Hit rate | vs 40% | R / trade after costs |
|---|---|---|---|---|---|---|
| ES 15m | 2 | 6575 | 63.4% | 37.5% | −2.5 | −0.204 |
| ES 15m | 3 | 3049 | 61.9% | 38.9% | −1.1 | −0.166 |
| ES 15m | 4 | 1470 | 63.5% | 36.7% | −3.3 | −0.216 |
| ES 15m | 5 | 679 | 62.5% | 37.7% | −2.3 | −0.189 |
| ES 3m | 3 | 1297 | 59.9% | 35.2% | −4.8 | −0.381 |
| EURUSD 1h | 3 | 337 | 59.2% | 29.4% | −10.6 | −0.316 |
| XAUUSD 1h | 3 | 166 | 50.2% | 33.7% | −6.3 | −0.201 |
| BTC 1h | 3 | 120 | 54.3% | 39.2% | −0.8 | −0.046 |
| SPY 1D | 3 | 139 | 65.3% | 47.5% | **+7.5** | **+0.179** |

Read that as three separate findings.

**a) Intraday, the raw pattern has no continuation edge.** ES 15m sits 1–3
points below the driftless null across every N, on 12,000 filled trades. Under
optimistic tie-breaking it sits *at* the null (40.0% at N=3), and the 3m
bar-magnifier run in §6 puts it at 39.1% — so read this as "no edge", not as
"negative edge"; the earlier reading of these cells as meaningfully below the
null was leaning on the conservative assumption. Either way there is no edge to
eat. N is
irrelevant — 2, 3, 4 and 5 are indistinguishable, which is itself the tell. A
real momentum effect would strengthen or decay monotonically with run length.
A flat line across N means the conditioning variable carries no information.

**b) The stop-entry is doing real work, just not enough of it.** Fading the same
setups (entering one tick *below* the low after a green run) produces 29–31% hit
rates on ES 15m against 37–39% for continuation. So there *is* short-horizon
directional persistence — breaking the high of a run predicts more upside than
downside. It is simply smaller than the 1.5R bracket needs. Worth knowing,
because it means the answer to "should I fade it instead" is also no.

Note also the ~62% fill rate: nearly 40% of setups never trigger. Those unfilled
setups are disproportionately the immediate reversals, so the trigger is already
acting as a filter. The 37.5% is what survives *after* that filtering.

**c) SPY daily is the one positive cell, and it is the weakest evidence here.**
n = 139, so the standard error on the hit rate is ~4.2 points; 47.5% is about
1.8σ from 40%. That is suggestive, not established. The sample is 2018–2026 —
one regime, strongly trending. Long and short both print positive (48.9% /
43.9% at N=2), which argues against pure index drift, but at n = 57 on the short
side that is not a number to act on. Costs are also near zero at this R, which
is precisely why it clears when nothing else does.

## 3. What would change the conclusion

The honest framing is that "N same-colour candles" is the wrong conditioning
variable, not that momentum continuation is fake. A run of four small-bodied
bars inside a 20-tick range and a run of four expanding bars breaking out of a
week's consolidation are the same signal to this script and completely different
trades. The inputs that exist to test that are, in order of how much I expect
them to matter:

1. **`Min risk (ticks)`** — the largest single lever. It removes the trades
   where R is so small that friction is 30–40% of the bet. Nothing else in the
   script changes the cost ratio.
2. **`Min body / range`** — stops counting indecision bars as momentum.
3. **`Require range expansion`** — the run must be going somewhere, measured
   against ATR.
4. **`Trend filter (EMA)`** — tests whether continuation only works aligned
   with the larger move.
5. **`Max risk (ATR multiples)`** — drops the late entry after a climax bar.
6. **`Run extreme` stop mode** — a wider, structurally better stop. Note it
   *lowers* the required hit rate arithmetic not at all (R scales, so does the
   target) but it does change what fraction of R the costs are.

The filters are not there to be swept until something is green. With 3,000
trades and six binary-ish filters you will find a positive combination by
chance. The test that matters: pick the filter *before* looking, then check that
the improvement holds on ES 15m **and** ES 3m **and** a non-equity instrument,
and that neighbouring parameter values are also positive. See `/backtest-expert`
guidance in this repo's skills for the full protocol.

## 4. Implementation notes

**Order handling.** `strategy.entry(..., stop=trigger)` places a stop-market
order at the trigger. The protective bracket is issued with the entry, not after
it — an entry that fills intrabar is otherwise unprotected until the next bar's
open, which quietly inflates results on the bars that gap through the stop.
Unfilled orders are cancelled once `pendingAge >= i_validBars`, so the default
of 1 means "the next bar only".

**Run tracking.** `runHi` / `runLo` are maintained as `var float` in the run
state machine rather than via `ta.highest` / `ta.lowest`, so the lookback never
needs to be a series length. The state machine runs unconditionally on every
bar, as v6 requires.

**Doji handling.** `Min body / range` at 0 treats any close above the open as
green. Above 0, a candle failing the body test is neutral and *breaks* the run
rather than being skipped — a stalling bar is information, not noise to ignore.

**Sizing.** `Fixed` makes the equity curve a function of stop width: the
wide-stop trades dominate P&L and the backtest tells you about candle-size
distribution rather than about the signal. `Risk % of equity` is the mode to
read results in, because there every trade is exactly 1R.

**The stats table** reports realised hit rate against `1/(1+RR)` directly, with
the difference signed and coloured. That comparison, not net profit, is the
output of this script.

**Backtest realism.** TradingView's broker emulator guesses intrabar order from
where the open sits relative to the high and low, which can resolve
stop-and-target bars in your favour. Enable the bar magnifier, and treat the
Python probe (which books the stop on ambiguous bars) as the floor and the
strategy tester as the ceiling.

## 5. Test 1 — the min-risk filter (result: rejected)

Pre-committed hypothesis: *min risk in ticks lifts ES 15m past the ~45% net
break-even, and the improvement holds on ES 3m and a non-equity instrument with
neighbouring parameter values also positive.*

The confound to control for is mechanical. Raising the minimum stop distance
selects for larger candles, which shrinks friction as a fraction of R whether or
not the signal improves. So `net R` will improve under this filter even if the
pattern is pure noise. The test therefore has to be run on **gross** expectancy
(cost-free), with net reported only to size the drag.

### ES 15m, N=3, sweep over min risk

| Min risk (ticks) | Filled | Hit rate | ±1se | Gross R/trade | Net R/trade |
|---|---|---|---|---|---|
| 0 | 3049 | 38.9% | 0.9 | −0.028 | −0.166 |
| 15 | 2462 | 39.4% | 1.0 | −0.015 | −0.118 |
| 20 | 1999 | 39.4% | 1.1 | −0.016 | −0.102 |
| 25 | 1583 | 40.1% | 1.2 | +0.001 | −0.071 |
| **30** | **1279** | **40.5%** | **1.4** | **+0.012** | **−0.050** |
| 40 | 862 | 39.2% | 1.7 | −0.020 | −0.070 |
| 50 | 592 | 39.9% | 2.0 | −0.004 | −0.045 |
| 60 | 424 | 38.7% | 2.4 | −0.034 | −0.070 |
| 80 | 226 | 35.8% | 3.2 | −0.106 | −0.134 |

**The filter works on net and does nothing on gross.** Net improves
monotonically from −0.166 to about −0.05 — a 0.12R gain — while the hit rate
moves 38.9% → 40.5%, which at n = 1279 is 0.36 standard errors from the null.
Essentially the entire net improvement is cost drag being removed, exactly as
the confound predicts.

That also fixes the ceiling. Net expectancy can never exceed gross expectancy,
and gross sits at 0.00 ± 0.01 across the whole usable range of the filter. Even
a hypothetical zero-cost version of this strategy is a break-even coin flip. The
filter cannot rescue it, because there is nothing to rescue: **it removes the
losing part of the bet without making the remaining part winning.**

N = 2 and N = 4 behave the same way or worse (N = 4 degrades past min risk 50,
reaching 30.8% at 60+). There is no peak to find and no plateau above zero.

### Cross-market

| Market | Best gross cell | n | Hit rate | Gross R | Verdict |
|---|---|---|---|---|---|
| ES 15m | minR 30 | 1279 | 40.5% ±1.4 | +0.012 | flat, not significant |
| ES 3m | minR 30 | 95 | 45.3% ±5.1 | +0.132 | n too small, 1.0σ |
| EURUSD 1h | minR 110 | 112 | 34.8% ±4.5 | −0.129 | never crosses zero |
| XAUUSD 1h | minR 1600 | 68 | 38.2% ±5.9 | −0.044 | never crosses zero |
| BTC 1h | minR 25000 | 70 | 44.3% ±5.9 | +0.107 | non-monotone, noise |

Every market's gross expectancy climbs toward zero as min risk rises, and the
only cells that cross above it have n < 150 and standard errors of 4–6 points.
The two that look best sit on the shortest datasets in the repo: `es1_3m` covers
2026-06-28 to 2026-08-28 (two months) and `btcusd_1h` covers three months. One
regime, one window, sub-significant. BTC's sequence is also non-monotone
(37.0 → 44.3 → 40.8 → 46.7), which is what noise looks like and what an edge
does not.

### Stability of the best cell

ES 15m N=3 minR 30, by quarter:

| Quarter | n | Hit rate | Gross R | Net R |
|---|---|---|---|---|
| 2024Q4 | 57 | 52.6% | +0.316 | +0.244 |
| 2025Q1 | 178 | 39.3% | −0.024 | −0.085 |
| 2025Q2 | 226 | 35.4% | −0.129 | −0.185 |
| 2025Q3 | 85 | 48.2% | +0.215 | +0.145 |
| 2025Q4 | 153 | 46.4% | +0.160 | +0.101 |
| 2026Q1 | 234 | 39.7% | −0.013 | −0.075 |
| 2026Q2 | 217 | 39.6% | −0.009 | −0.073 |
| 2026Q3 | 116 | 37.1% | −0.073 | −0.139 |
| **pooled** | **1266** | | **+0.011** | **−0.051** |

Three positive quarters out of eight, and they are the three smallest samples
(n = 57, 85, 153). The four largest quarters (n = 178–234) are all negative and
all cluster at 35–40%. Hit rate swings 35.4% to 52.6% with no persistence.

**Verdict: abandon the min-risk filter as a rescue for this strategy on ES.**
It is a genuine improvement to the trade model — it should stay on, since paying
25% of R in friction is never right — but it addresses cost, not edge, and the
edge is what is missing.

### What this rules out

The hypothesis under test was not only "min risk helps" but the broader claim
that the intraday continuation edge exists and is being hidden by friction. The
gross column answers that directly: with friction set to zero, the pattern still
returns 0.00R per trade on 3,000 ES 15m trades. Filters that select *which*
setups to take cannot fix a signal whose cost-free expectancy is zero. Only a
different signal can.

## 6. Test 2 — the RR sweep (result: rejected, and one artifact corrected)

Pre-committed hypothesis: *the 1.5R bracket is the binding constraint. ES 15m
fade at 29–31% vs continuation at 37–39% says the directional persistence is
real but small, so a lower target — needing only 50% at 1R — should clear its
own break-even where 1.5R does not.*

### The artifact

The first pass, on 15m OHLC with conservative tie-breaking, appeared to reject
that hypothesis violently and in the opposite direction:

| RR | BE% | Hit rate (cons.) | z | Hit rate (opt.) | z | Ambiguous |
|---|---|---|---|---|---|---|
| 0.50 | 66.7% | 61.7% | **−5.67** | 66.0% | −0.77 | 4.3% |
| 0.75 | 57.1% | 53.2% | −4.31 | 56.0% | −1.30 | 2.7% |
| 1.00 | 50.0% | 47.3% | −2.96 | 49.3% | −0.82 | 1.9% |
| 1.50 | 40.0% | 38.9% | −1.29 | 40.0% | −0.02 | 1.1% |
| 2.00 | 33.3% | 32.8% | −0.66 | 33.6% | +0.27 | 0.8% |
| 3.00 | 25.0% | 24.0% | −1.26 | 24.4% | −0.75 | 0.4% |

A 5.7σ result is not a finding, it is a bug hunt. The tell is the last column:
the tighter the target, the more often a single 15m bar contains both the stop
and the target, and every one of those is booked as a loss by assumption. At
1.5R that assumption touches 1.1% of trades and does not matter. At 0.5R it
touches 4.3% and moves the hit rate 4.3 points. **The apparent gradient in z is
the assumption, not the market.** §2's claim that the conservative assumption is
"not what produces the result" holds at 1.5R and fails below it.

### Removing the assumption

`backtest_momentum_run_magnified.py` rebuilds 15m bars from `es1_3m` (so the
OHLC is exact) and resolves every fill, stop and target on the 3m sub-bars.
Residual ambiguity: 0.0% of trades.

| RR | BE% | Hit rate | ±1se | z | Gross R | Net R |
|---|---|---|---|---|---|---|
| 0.50 | 66.7% | 67.5% | 2.8 | +0.30 | +0.013 | −0.116 |
| 0.75 | 57.1% | 59.8% | 3.0 | +0.88 | +0.046 | −0.083 |
| 1.00 | 50.0% | 49.1% | 3.0 | −0.30 | −0.018 | −0.147 |
| 1.25 | 44.4% | 45.0% | 3.0 | +0.19 | +0.013 | −0.116 |
| 1.50 | 40.0% | 39.1% | 3.0 | −0.30 | −0.022 | −0.151 |
| 2.00 | 33.3% | 32.8% | 2.9 | −0.17 | −0.015 | −0.144 |
| 3.00 | 25.0% | 22.1% | 2.5 | −1.13 | −0.114 | −0.243 |

**The hit rate tracks `1/(1+RR)` at every target.** |z| ≤ 1.13 across the whole
sweep, gross expectancy is zero within noise, and net is negative everywhere.
The RR curve has no shape: there is no target distance at which this entry beats
a coin. n = 271 over two months, so this cannot *establish* anything — but it is
the only measurement here with no path assumption, and it agrees with the
midpoint of the conservative/optimistic bracket on the full 15m sample.

### The full 15m sweep, for completeness

All 27 cells (N ∈ {2,3}, min-risk ∈ {0,30}, RR 0.5→3.0) are net-negative. The
one panel that drifts positive on gross — N=3 with min-risk 30, reaching z=+1.06
and gross +0.050 at RR=3.0 — does not replicate at N=2, where the same filter
gives z between −1.15 and −4.68 across the same RR grid. Failing the
neighbouring-parameter check is the standard disqualifier.

### Verdict

**The exit is not the problem either.** Test 1 closed the filter path: selection
cannot fix a signal whose cost-free expectancy is zero. Test 2 closes the exit
path: no R multiple from 0.5 to 3.0 changes that, because the hit rate simply
tracks the geometry of the bracket. Together they say the entry carries no
information about the forward distribution at any horizon this trade model can
reach — which is the definition of no edge, and is not fixable by tuning either
end of the trade.

What remains untested is the *entry mechanism* rather than its parameters. Every
result here conditions on a stop order filled one tick beyond the extreme. A
limit entry on a pullback into the run is a different conditioning event and is
not covered by any of this. That is a new hypothesis, not a variation of this
one, and it needs its own signal, its own script and its own pre-commitment.

## 7. Known gaps

- The diagnostic counters miss a trade that fills and exits within the same bar
  (`justFilled` and `justClosed` both test against the previous bar's position).
  The strategy tester still books it correctly; only the table's hit rate is
  affected, and only on instruments where that is common.
- The Python probe has no session filter, so ES results include the overnight
  session where the pattern and the liquidity are both different.
- Fill assumptions in both probes are ideal: the stop order fills at the trigger
  price exactly. Slippage is charged as a flat tick cost rather than modelled.
- The magnifier probe resolves paths at 3m, not tick level. A 3m bar containing
  both levels is still booked as a loss; that is 0.0% of trades in the run
  above, but it would not stay at zero for targets tighter than 0.5R.
- `backtest_momentum_run.py` is fine at 1.5R and misleading below ~1.25R. Use
  the magnifier for anything in that range, or at minimum report both
  tie-breaking conventions and treat the gap as the error bar.
