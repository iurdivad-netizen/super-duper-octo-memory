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
points *below* the driftless null across every N, on 12,000 filled trades. This
is not a marginal edge being eaten by costs; there is no edge to eat. N is
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

## 5. Known gaps

- The diagnostic counters miss a trade that fills and exits within the same bar
  (`justFilled` and `justClosed` both test against the previous bar's position).
  The strategy tester still books it correctly; only the table's hit rate is
  affected, and only on instruments where that is common.
- The Python probe has no session filter, so ES results include the overnight
  session where the pattern and the liquidity are both different.
- Fill assumptions in the probe are ideal: the stop order fills at the trigger
  price exactly. Slippage is charged as a flat tick cost rather than modelled.
