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

## 7. Test 3 — does the instrument matter? (NQ and gold)

Two reasons this was worth testing rather than assuming. First, gold is a
different asset class with different participants. Second — the substantive one
— **NQ has a structurally better cost ratio than ES**, and cost is the only
thing that has actually varied across every result so far:

| | Median 15m range | Round-trip friction | Cost as % of R | Net break-even @1.5R |
|---|---|---|---|---|
| ES 15m | 25 ticks | ~3 ticks | 12.0% | ~44.8% |
| **NQ 15m** | **~211 ticks** (52.7 pts @ 25,000) | ~2.5 ticks | **1.2%** | **~40.5%** |
| XAUUSD 15m | — | ~30 ticks | ~10.6% | ~44% |

NQ's tick is $5 against ES's $12.50 while its bar range is roughly 8× larger in
ticks, so friction nearly vanishes as a fraction of R. If the ES result were a
good signal buried under costs, NQ is exactly where it would surface.

### NQ (QQQ 15m as price proxy, 5,000 bars, Dec 2025 – Sep 2026)

| N | n | Hit rate | Optimistic | Ambiguous | z (cons) | z (opt) | Gross R | Net R |
|---|---|---|---|---|---|---|---|---|
| 2 | 840 | 35.7% | 37.1% | 1.4% | −2.59 | −1.71 | −0.107 | −0.124 |
| 3 | 407 | 35.9% | 36.9% | 1.0% | −1.74 | −1.32 | −0.103 | −0.120 |
| 4 | 193 | 36.8% | 37.8% | 1.0% | −0.93 | −0.62 | −0.080 | −0.096 |

Ambiguity is ~1%, so unlike the RR sweep this is not a tie-breaking artifact —
both conventions agree. NQ is **worse than ES**: gross −0.08 to −0.11 against
ES's 0.00, and the hit rate sits below the null under either convention.

The structural advantage is real and it does not help. Low friction moves net
*toward* gross; it cannot move net *above* gross. With gross negative, the
cheapest contract in the complex still loses. This is the cleanest confirmation
of the §5 ceiling argument: cost was never the binding constraint.

*Caveat:* QQQ is an RTH-only ETF standing in for a 23-hour futures contract, and
its penny spread is nothing like NQ's tick — which is why costs are modelled
separately above rather than taken from QQQ. It proxies NQ's price behaviour,
not its microstructure.

### Gold — and a second brush with the same artifact

XAUUSD ambiguity runs 4.6–6.2%, four to six times ES's, because gold's intrabar
noise is large relative to the stop distance. The two conventions therefore
disagree about the sign:

| Data | N | n | Conservative | Optimistic | z (cons) | z (opt) |
|---|---|---|---|---|---|---|
| XAUUSD 15m | 2 | 629 | 36.7% | 41.3% | −1.70 | **+0.68** |
| XAUUSD 15m | 3 | 304 | 36.5% | 41.8% | −1.26 | **+0.63** |
| XAUUSD 1h | 2 | 347 | 39.8% | 45.8% | −0.09 | **+2.18** |

A 2.18σ "edge" on gold 1h that exists only under optimistic tie-breaking is the
RR=0.5 mistake in a new costume. Resolved rather than assumed: 5m data fetched
for the same window, 15m bars rebuilt from it, every fill and exit walked on the
5m sub-bars (residual ambiguity 3–4%, not 0% — gold stays noisy even at 5m).

| N | RR | n | BE% | Hit rate | ±1se | z | Gross R | Net R |
|---|---|---|---|---|---|---|---|---|
| 2 | 1.0 | 631 | 50.0% | 46.8% | 2.0 | −1.64 | −0.065 | −0.158 |
| 2 | 1.5 | 631 | 40.0% | 38.2% | 1.9 | −0.93 | −0.043 | −0.136 |
| 3 | 1.0 | 305 | 50.0% | 49.8% | 2.9 | −0.06 | +0.001 | −0.105 |
| 3 | 1.5 | 305 | 40.0% | 39.7% | 2.8 | −0.12 | −0.004 | −0.110 |
| 3 | 2.0 | 305 | 33.3% | 35.7% | 2.7 | +0.88 | +0.070 | −0.036 |
| 4 | 1.5 | 153 | 40.0% | 43.1% | 4.0 | +0.78 | +0.085 | +0.028 |

The +2.18σ does not survive. Gold tracks `1/(1+RR)` exactly as ES does, gross is
zero within noise, and net is negative on the cost drag. The single positive net
cell (N=4) has n=153 and z=+0.78.

### Verdict

**No. Three instruments, three cost structures, one answer.** ES ≈ 0 gross,
gold ≈ 0 gross, NQ slightly negative gross. The only thing that varies
meaningfully across markets is net, and net is fully explained by
cost-as-a-fraction-of-R — a broker fact, not a market edge.

### A note on how much testing has now happened

Across the three tests this file records: 6 instruments × 4 run lengths ×
8 R multiples × several filter grids. That is several hundred cells. At the
conventional 5% threshold, dozens of them should look positive by chance alone,
and dozens have: ES 3m at min-risk 30, BTC at 25k, gold 1h N=2 optimistic, gold
5m N=4. Every one shares the same three properties — n < 200, no replication at
neighbouring parameters, and a position at the edge of a grid.

That pattern is the finding. **Further instrument search is no longer a test of
the strategy; it is a search for the noisiest cell in a large grid.** Any future
candidate needs to be pre-registered, sized for the effect being claimed, and
validated out of sample before it means anything.

## 8. Test 4 — stop placement and trailing exits

Two claims under test: (a) a wider stop — the previous candle's low — helps;
(b) failing that, a tight trail on each candle's low or an ATR distance helps.

Claim (b) deserved a real test rather than an extrapolation. Tests 1–3 all used
**fixed** brackets, and a fixed bracket is blind to path shape: it only asks
which of two levels is touched first. A trailing stop is a different functional
of the same forward distribution, sensitive to the serial correlation of
increments. Nothing established so far rules it out.

### First, a correction to the framing — the entry does carry information

The exit test needed a benchmark for path-dependent exits, so it uses a
**random-entry control**: the identical exit logic fired from randomly chosen
bars in the same data, which absorbs the instrument's drift and volatility and
leaves only what the signal adds. The control came back at −0.130R gross, not
zero, which is worth its own table:

| Entry condition | n | Hit rate | Gross (cons) | ±se | Gross (opt) | vs random |
|---|---|---|---|---|---|---|
| random bar & direction | 18611 | 34.8% | −0.130 | 0.009 | −0.095 | — |
| N=1 (any coloured bar) | 13823 | 36.7% | −0.082 | 0.010 | −0.058 | +0.048R (3.6σ) |
| N=2 | 6572 | 37.5% | −0.062 | 0.015 | −0.036 | +0.068R (3.9σ) |
| **N=3** | 3048 | 38.9% | −0.028 | 0.022 | **−0.000** | **+0.102R (4.3σ)** |
| N=4 | 1470 | 36.7% | −0.084 | 0.031 | −0.055 | +0.046R (1.4σ) |
| N≥5 | 1274 | 37.0% | −0.076 | 0.034 | −0.060 | +0.054R (1.6σ) |

**A generic breakout entry on ES 15m loses about 0.10–0.13R gross.** Buying one
tick above an arbitrary bar's high with a stop at its low is a losing structure
before any cost — short-horizon adverse selection at the breakout. The run
filter is not neutral against that: at N=3 it recovers the whole penalty, at
4.3σ on 3,048 trades. That is the only statistically solid positive finding in
this file.

It changes the story of §2 and §6 in one specific way. "The hit rate tracks
`1/(1+RR)`" is still true, but the correct reading is not "the signal does
nothing" — it is **"the signal does exactly enough to cancel the breakout
penalty and no more."** The ceiling is zero gross, and it is reached, not
approached.

Two cautions. The progression is not monotone: N=4 and N≥5 fall back to −0.08,
so this is not "more consecutive candles, better conditioning" — N=3 is a peak
in a five-cell grid, and N=3 vs N=1 is only 2.2σ. And zero gross is still zero:
recovering a penalty is not the same as generating an edge.

### Claim (a): a wider stop

On 3m-resolved paths, 274 trades:

| Stop | Hit rate | Gross | ±se | Net |
|---|---|---|---|---|
| signal candle low | 39.1% | −0.024 | 0.074 | −0.152 |
| previous candle low | 39.1% | −0.024 | 0.074 | −0.113 |
| min(both lows) | 38.7% | −0.033 | 0.074 | −0.119 |

Gross is unchanged to three decimals. Net improves by 0.039R — and that is the
Test 1 confound again, arriving through a different door: a wider stop means a
larger R, which means friction is a smaller fraction of it. Nothing about the
signal improved. The stop moved, the target moved with it (both are defined off
R), and the bracket geometry is scale-invariant.

### Claim (b): trailing

| Exit model | Hit rate | Avg win | Avg loss | Needs | **Gap** | Gross |
|---|---|---|---|---|---|---|
| candle low, fixed 1.5R | 39.1% | +1.50R | −1.00R | 1.56R | **−0.06R** | −0.024 |
| prev candle low, fixed 1.5R | 39.1% | +1.50R | −1.00R | 1.56R | −0.06R | −0.024 |
| candle low, trail prior low | 32.1% | +0.90R | −0.60R | 1.26R | −0.37R | −0.118 |
| prev low, trail prior low | 33.2% | +0.62R | −0.43R | 0.87R | −0.25R | −0.082 |
| trail low, 1.5R cap | 33.6% | +0.94R | −0.61R | 1.20R | −0.26R | −0.088 |
| ATR trail 1.5× | 31.4% | +1.24R | −0.77R | 1.68R | −0.44R | −0.138 |
| ATR trail 2.5× | 25.2% | +2.31R | −0.87R | 2.58R | −0.27R | −0.068 |
| ATR trail 3.5× | 22.3% | +2.83R | −0.94R | 3.28R | −0.45R | −0.101 |

"Needs" is the average win required to break even at that hit rate; "Gap" is how
far short the actual average win falls. **The fixed bracket is the closest
structure to break-even in the table, and all six trailing variants are three to
seven times further away.**

The mechanism is visible in the middle columns, and it is not what intuition
predicts. Trailing does exactly what it is supposed to: `prev low, trail prior
low` cuts the average loss from −1.00R to −0.43R, a 57% reduction. It also cuts
the hit rate from 39.1% to 33.2% and the average win from 1.50R to 0.62R. **The
saving on losers is real and it is smaller than the cost in winners.**

That is what a trailing stop does to a driftless distribution. Every bar the
trail advances is another level for noise to touch; without positive serial
correlation in the increments there is no compensating trend to ride. The wide
ATR trails show the same thing from the other end — ATR 3.5× correctly finds a
2.83R average winner, but drags the hit rate to 22.3% when 25.4% is needed.

### Verdict

Both claims rejected. The wider stop is a cost-ratio change, not a signal
change. Trailing is strictly worse than the fixed bracket at every setting
tested, by a mechanism the payoff table makes explicit.

The entry claim is **partly upheld and it matters**: the entry is not arbitrary,
it is worth +0.10R against a generic breakout. But §5's ceiling argument now has
a sharper form. The entry's demonstrated capability is cancelling the breakout
penalty exactly. Every exit model is a different way of reading the same forward
distribution, and that distribution has zero drift. **No exit can extract
positive expectancy from a driftless path — the exit only decides how the zero
is divided between hit rate and win size.** The fixed 1.5R bracket happens to
divide it most efficiently, which is why it sits closest to break-even.

*Sample caveat:* the trailing tests run on 274 magnified trades with ±0.074 on
gross, so no single row is individually significant. The ranking is uniform
across all six variants and the payoff decomposition is measured with much
better precision than the mean, which is what the conclusion rests on.

## 9. Test 5 — session-matched control

§8's control drew bars uniformly, so part of the +0.102R could have been a
time-of-day effect: N=3 runs may cluster in hours that behave differently from
the average hour. This replaces it with a control drawn from the **same 15-minute
slot of the day** as each signal, in the same direction.

| Entry set | n | Hit rate | Gross | ±se | vs signal |
|---|---|---|---|---|---|
| **SIGNAL — N=3 run** | 3048 | 38.9% | −0.028 | 0.022 | — |
| uniform random bar | 17813 | 35.2% | −0.120 | 0.009 | +0.092R (3.9σ) |
| session-matched, any bar | 18162 | 34.9% | −0.129 | 0.009 | +0.100R (4.2σ) |
| session-matched, excluding run bars | 18111 | 34.5% | −0.137 | 0.009 | **+0.109R (4.6σ)** |

**The effect is a run effect, not a session effect.** Matching on time of day
does not shrink it — it grows slightly, and grows again when run bars are
removed from the control pool (which is the cleanest contrast, since the
uniform pool was partly contaminated by the signal itself). §8's finding stands
at 4.6σ against the strictest control available here.

### Where the return sits, by session

| Session (ET) | n | Hit rate | Gross | ±se | Control | Net |
|---|---|---|---|---|---|---|
| RTH morning 0930–1200 | 386 | 42.5% | **+0.062** | 0.063 | −0.151 | −0.006 |
| RTH afternoon 1200–1600 | 557 | 39.3% | −0.017 | 0.052 | −0.125 | −0.104 |
| Europe 0300–0930 | 887 | 35.2% | **−0.121** | 0.040 | −0.168 | −0.258 |
| Asia/overnight 1600–0300 | 1218 | 40.2% | +0.006 | 0.035 | −0.085 | −0.180 |

Two things are visible and only one of them is useful.

**The Europe session is where the strategy bleeds.** Gross −0.121 ± 0.040 is
three standard errors below zero on 887 trades — the only cell in this entire
file that is significantly *negative* rather than merely not-positive. Net
−0.258. Whatever the run filter is doing in the US sessions, it is not doing it
between 03:00 and 09:30 ET.

**RTH morning is the best cell and it is not tradeable.** Gross +0.062 ± 0.063
is one standard error from zero, and friction eats it exactly: net −0.006.
Break-even, not profitable, arrived at after several hundred prior cells.

Its stability settles it:

| Half-year | n | Hit rate | Gross | ±se | Net |
|---|---|---|---|---|---|
| 2024H2 | 34 | 52.9% | +0.324 | 0.217 | +0.225 |
| 2025H1 | 102 | 35.3% | −0.118 | 0.119 | −0.180 |
| 2025H2 | 104 | 54.8% | +0.370 | 0.123 | +0.292 |
| 2026H1 | 105 | 35.2% | −0.119 | 0.117 | −0.176 |
| 2026H2 | 41 | 39.0% | −0.024 | 0.193 | −0.082 |

The sign alternates every half-year. 2025H2 at +0.370 is 3σ from zero on its
own, and means nothing: in a grid of 5 half-years × 4 sessions, sitting on top
of every test in §§5–8, a 3σ cell is expected rather than surprising.

Dropping the Europe session entirely — the one change the data actually
supports — moves overall gross from −0.028 to about +0.010 and leaves net near
−0.13, because the surviving overnight hours carry a small R and therefore a
large cost drag. Removing the worst cell does not make the rest positive.

### Verdict

The question is answered cleanly and in the strategy's favour: **the entry
conditioning is real, survives the strictest control, and is worth +0.109R
against a matched breakout.** The strategy still has no positive-expectancy
configuration. Those two statements are compatible because the effect's job is
to cancel a −0.13R penalty, and it cancels it to approximately zero everywhere
except Europe hours, where it fails outright.

## 10. Test 6 — full sweep with Europe excluded, and an out-of-sample check

Excluding the Europe session was a **data-driven** choice: §9 identified it as
the worst cell in this same sample. Sweeping parameters on the remaining data
therefore compounds the selection, and an in-sample result cannot settle
anything. The sample is split: **in-sample 2024-10 → 2025-12**, **out-of-sample
2026-01 → 2026-08**, with the out-of-sample half untouched until the in-sample
winners were fixed.

Grid: N ∈ {2,3,4} × min-risk ∈ {0,15,25,35} ticks × RR ∈ {1.0,1.25,1.5,2.0,2.5}
= 60 cells. Values are net R/trade after 3-tick friction.

### In-sample

```
  N=3      RR1.0    RR1.25    RR1.5     RR2.0     RR2.5
     0    -0.182   -0.161   -0.143    -0.101    -0.119
    15    -0.108   -0.082   -0.072    -0.005    -0.023
    25    -0.050   -0.033   -0.017    +0.041*   +0.056*
    35    -0.035   -0.032   -0.035    +0.016*   +0.033*
```

**8 of 60 cells net-positive (13%)**, and — this is the part that looks
convincing — they form a contiguous region rather than isolated spikes: N=3 and
N=4, min-risk 25–35, RR 2.0–2.5. That is exactly the "plateau, not a peak"
pattern the standard methodology says to look for. Excluding Europe genuinely
did move the whole grid up, by roughly 0.05–0.10R against the §5 numbers.

### Out-of-sample

```
  N=3      RR1.0    RR1.25    RR1.5     RR2.0     RR2.5
     0    -0.113   -0.082   -0.104    -0.123    -0.150
    15    -0.059   -0.025   -0.054    -0.088    -0.116
    25    -0.052   -0.015   -0.049    -0.056    -0.105
    35    +0.004*  +0.041*  +0.006*   -0.021    -0.058
```

**3 of 60 (5%)** — and in a different place. The out-of-sample positives sit at
RR 1.0–1.5 where the in-sample grid was solidly negative, and the in-sample
region at RR 2.0–2.5 has gone negative.

### The eight winners, carried forward verbatim

| Cell | IS n | IS net | ±se | OOS n | OOS net | ±se |
|---|---|---|---|---|---|---|
| N=3 minR 25 RR 2.0 | 654 | +0.041 | 0.057 | 497 | −0.056 | 0.064 |
| N=3 minR 25 RR 2.5 | 654 | +0.056 | 0.064 | 497 | −0.105 | 0.070 |
| N=3 minR 35 RR 2.0 | 452 | +0.016 | 0.068 | 351 | −0.021 | 0.076 |
| N=3 minR 35 RR 2.5 | 452 | +0.033 | 0.076 | 351 | −0.058 | 0.084 |
| N=4 minR 15 RR 2.0 | 516 | +0.025 | 0.064 | 360 | **−0.244** | 0.071 |
| N=4 minR 25 RR 2.0 | 338 | +0.027 | 0.079 | 262 | **−0.247** | 0.083 |
| N=4 minR 35 RR 2.0 | 239 | +0.031 | 0.093 | 175 | −0.182 | 0.103 |
| N=4 minR 35 RR 2.5 | 239 | +0.040 | 0.105 | 175 | −0.136 | 0.117 |

**0 of 8 survived.** Every one flipped negative. The N=4 cells swung by
0.2–0.27R between halves.

### What this settles

The in-sample plateau was real as a description of 2024-10 → 2025-12 and carried
no information about 2026. That is worth stating plainly because "seek plateaus,
not peaks" is the standard defence against curve-fitting, and here **the plateau
formed anyway and still meant nothing.** A contiguous positive region is what
noise looks like when neighbouring cells share most of their trades — the cells
are not independent draws, so their agreement is not corroboration.

The two positive rates tell the same story: 13% of cells positive in sample,
5% out of sample. The out-of-sample rate is what a distribution centred slightly
below zero produces by chance. Nothing is being detected.

Excluding Europe was still the right call on the merits — §9 established that
cell as significantly negative on 887 trades, and dropping it does lift the
grid. It lifts it from clearly negative to slightly negative. It does not lift
it above zero, and no parameter combination within it survives a walk forward.

### Verdict — end of the line for this strategy family

Six tests: filters, exits, instruments, stop placement, sessions, and a full
parameter sweep with out-of-sample validation. The one durable finding is §8/§9:
the N=3 entry is worth +0.109R against a session-matched breakout at 4.6σ, which
cancels the breakout penalty and reaches zero. Everything downstream of that
confirms the same ceiling from a different angle.

Further parameter search on this signal is not a test. Any future work needs a
second, independent condition supplying actual drift, benchmarked against the
N=3 baseline rather than against random entry, with the out-of-sample split
fixed before the first result is read.

## 11. Known gaps

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
- `backtest_momentum_run.py` is fine at 1.5R on ES and misleading below ~1.25R.
  On gold it is unreliable at *every* RR (4.6–6.2% ambiguity). Use the magnifier
  there, or at minimum report both tie-breaking conventions and treat the gap as
  the error bar.
- The gold magnifier resolves at 5m, leaving 3–4% residual ambiguity. Only ES,
  at 3m resolution, reaches 0.0%.
- `data/qqq_15m.csv` proxies NQ price behaviour but not its microstructure: it
  is RTH-only where NQ trades 23 hours, and its spread is pennies where NQ's is
  a $5 tick. NQ friction in §7 is modelled from tick geometry, not measured.
- `data/qqq_15m.csv`, `data/xauusd_15m.csv` and `data/xauusd_5m.csv` were pulled
  from Twelve Data in Sep 2026 and are point-in-time snapshots, not a maintained
  feed.
- Resolved in §9: the session-matched control leaves the effect intact at 4.6σ,
  so it is a run effect rather than a time-of-day effect.
- The session buckets in §9 are fixed clock windows and ignore DST shifts and
  half-days; a few trades are in the wrong bucket.
- The §10 split is a single walk-forward step, not a rolling one, and the
  out-of-sample half (8 months) is shorter than the in-sample half (14 months).
  A 0-for-8 failure needs no more resolution than that, but a positive result
  would have.
- Cells in the §10 grid share most of their trades, so the 60 tests are far from
  independent and no multiple-comparison correction is quoted; the out-of-sample
  split is what does the work instead.
- Trailing exits in §8 update at 15m close and are checked on 3m sub-bars. A
  trail that updates intrabar would behave differently and is not tested.
