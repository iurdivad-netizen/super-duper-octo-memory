# Next Candle Predictor — Dev Notes

`next_candle_predictor.pine` — Pine Script **v6**, `indicator("Next Candle Predictor", overlay=true)`.
`backtest_next_candle_predictor.py` — bar-for-bar Python replica used to validate it.

## The short version

Two forecasts for the bar that is currently forming:

| | model | measured out-of-sample result (ES 15m, ~42k bars) |
|---|---|---|
| **Colour** | hierarchical Markov chain over the last 1..N candle colours, empirical-Bayes back-off | **no edge.** 50.29% vs 50.61% for always-predicting-the-majority. Brier skill score −0.0005 |
| **Size** | EWMA of range × state-conditional multiplier, shrunk toward 1.0 | **real.** 10.7% lower MAE than plain EWMA; 79.6% coverage on the 80% band |

Both are shipped, both are scored live on the chart. The colour half is included
because you cannot conclude "no edge" from a script that does not compute the
colour probability — and because the answer changes by symbol and timeframe, so
the panel measures it on *your* chart rather than asserting it.

## Why this exists

The starting point was a published TradingView script that counts, for each
pattern of the last N candle colours, how often the next candle was green, and
combines levels 1..7 with a prior. The mechanism is sound; the question was
whether the output is worth acting on. It is not, on the data available here —
and the reason is worth stating precisely, because it is not "the model is
badly built".

## Colour model

State is the last `k` candle colours, `k = 1..N`. Each level shrinks toward its
parent instead of reporting its raw frequency:

```
p0 = (green_total + s0 * 0.5) / (total + s0)          // unconditional rate
pk = (green_k + s * p(k-1)) / (total_k + s)            // level k, parent p(k-1)
```

This is a hierarchical empirical-Bayes estimator. `s` is a prior weight in
pseudo-observations: a pattern seen 5 times contributes almost nothing and the
estimate stays at the parent's value; a pattern seen 5,000 times dominates its
prior. That is the correct fix for the failure mode of raw pattern counting,
where `RRRGRGG` shows up 11 times, was green 8 of them, and the panel prints
73%.

Storage is one flat array. Level `k` owns `2^k` slots at offset `2^k − 2`, so
levels 1..8 occupy 510 slots; the optional regime split doubles that to 1,020.
Pattern ids are read from a pre-filled bit buffer rather than the history
operator, so every array index stays constant-qualified — this sidesteps
"cannot determine referencing length" entirely.

Optional exponential decay is implemented as a *growing observation weight*
rather than by rescanning the array each bar: add `w` instead of 1, and read
counts back as `count / w`. O(1) per bar instead of O(510), with a rescale when
`w` approaches float overflow.

### What it measures

`python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --sweep`:

```
N       accuracy   edge vs majority        Brier skill
1        50.45%    −0.16 pp  (z −0.67)     +0.00010
2        50.38%    −0.23 pp  (z −0.95)     −0.00009
3        50.29%    −0.33 pp  (z −1.36)     −0.00049
4        50.41%    −0.20 pp  (z −0.84)     −0.00121
5        50.21%    −0.41 pp  (z −1.67)     −0.00198
6        49.79%    −0.82 pp  (z −3.40)     −0.00363
7        50.01%    −0.60 pp  (z −2.49)     −0.00594
8        50.25%    −0.37 pp  (z −1.52)     −0.00926
```

Two things to read here:

1. **No level beats the trivial benchmark.** Predicting the majority colour every
   bar scores 50.61%; the model never does. The base rate itself is the whole
   signal, and the base rate is not tradable.
2. **The Brier skill score degrades monotonically with N.** That is overfitting,
   measured rather than argued: each extra candle of context splits the sample
   in half and buys nothing, so the estimator gets noisier while its mean stays
   put. An indicator defaulting to a 7-deep pattern is at the worst point of
   this curve.

ES 3m (~20k bars) and the close-vs-previous-close basis reproduce it: −0.59 pp
and −0.09 pp respectively, both with negative skill scores. The conclusion is
stable across timeframe and colour definition.

The honest framing: candle direction over one bar is close to a fair coin, and
the small deviations that exist are not stationary enough for a frequency count
to capture. This is what you should expect, and the panel says so.

## Size model

Candle *size* is a different question, because volatility clusters and direction
does not.

```
ew   = λ·ew + (1−λ)·range                        // RiskMetrics-style baseline
m    = (Σ ratio + s·1.0) / (count + s)           // state multiplier, shrunk to 1
pred = ew · m
```

The state is `volatility bucket × colour pattern` — 3 buckets (range/EWMA below
0.75, between, above 1.30) times up to 8 colour patterns = 24 cells. Shrinking
`m` toward 1.0 means an unseen state falls back to the plain EWMA rather than to
noise.

The 80% band is not parametric. The rolling last `i_bandWin` values of
`realised / predicted` are kept, and the 10th and 90th percentiles of that
distribution scale the point forecast. Coverage then comes out at 79.6% (ES 15m)
and 79.0% (ES 3m) against an 80% target — the band means what it says.

Measured skill: **+10.67%** MAE reduction vs the plain EWMA on ES 15m, **+2.99%**
on ES 3m. Smaller on the faster timeframe, as expected — 3m bars are closer to
pure microstructure noise, so there is less conditional structure for the
multiplier to find.

The predicted body and wick split come from the same state, as shrunk means of
`body/range` and `upper wick / non-body range`, which is what makes the
projected ghost candle a shape rather than a bar.

## Train / validation / test split

Walk-forward already makes every bar out-of-sample, so the split is not there to
fix a leak. It answers two things walk-forward structurally cannot:

1. **Is a parameter choice overfit?** The moment you tune `N`, `s` or `lambda` by
   watching the panel, the panel is no longer an independent read.
2. **Is the learned structure stable over time?** With learning frozen at the
   boundary, the later windows ask whether what the model learned still holds.

Three windows, default 75 / 20 / 5:

| window | role |
|---|---|
| **TRAIN** (75%) | the model fits its counts here |
| **VALID** (20%) | compare parameter settings here — read it as often as you like |
| **TEST** (5%) | read **once**, at the end, and change nothing afterwards |

Learning freezes at the end of TRAIN, so VALID and TEST are both clean reads of
the same fitted model. The Python `--tune` runs the stricter two-pass variant:
pass 1 freezes at 75% to produce the VALID column used for selection, pass 2
freezes at 95% so the TEST column is read by a model fitted on everything before
it, which is what live deployment looks like. Pine is single-pass and so uses the
simpler freeze-at-TRAIN semantics.

### What is frozen, and what is not

Frozen: the Markov counts, the size multiplier table, the body/wick shares, and
the band's error-ratio window — everything *fitted*.

**Not** frozen: the range EWMA. It is state, not a parameter. A frozen EWMA would
forecast the training window's volatility level forever.

### What it measures

ES 15m, defaults, 31,707 / 8,589 / 2,148 scored bars:

```
                         TRAIN         VALID          TEST
  model accuracy        50.21%        51.25%        49.53%
  edge over majority   -0.43 pp      +0.73 pp      -1.16 pp
    z-score              -1.52         +1.36         -1.08
  Brier skill        -0.00087      +0.00071      -0.00001
  size skill vs EWMA   +11.74%        +7.35%        +8.99%
  80% band coverage     79.67%        76.11%        80.87%
```

The colour row wanders across zero — negative, positive, negative — with |z|
never reaching 2. That is what no signal looks like. The size row decays from
train but holds at +9% on data the model never learned from, and coverage lands
at 80.9% against an 80% target.

Note coverage sags to 76.1% in VALID when frozen but is fine still-learning: the
multipliers are stable, **the band calibration is not**. Freeze for the
stationarity test; in live use let the band keep updating.

## Tuning without cheating

`--tune` grids on TRAIN, selects on VALID, and reads TEST once. It also reports
where the *train*-best config would have ranked on VALID — the diagnostic that
says whether tuning transfers at all:

```
colour — selected on VALID: N=3 s_link=200     valid BSS +0.00071
         valid spread over 15 configs: -0.00100 .. +0.00071
         the TRAIN-best config would rank at the 47th percentile on valid

size   — selected on VALID: lambda=0.97 shrink=100 size_n=3   valid +12.06%
         valid spread over 36 configs: +3.22% .. +12.06%
         the TRAIN-best config would rank at the 89th percentile on valid
```

**47th percentile is worse than picking at random.** Tuning the colour model is
provably noise-chasing, and the selected config still lands at −1.16 pp on TEST.
Size lands at the 89th: selection transfers, and it lifts TEST skill from +8.99%
at the defaults to **+13.49%**.

The concrete finding: `lambda = 0.97` beats the 0.94 default. RiskMetrics' 0.94 is
calibrated for daily returns, not intraday candle ranges.

## Other symbols — and the dead-bar trap

Nothing in the model is instrument-specific: colours are colours and sizes are
normalised by their own EWMA. It runs on any symbol and timeframe as-is. But one
data-quality problem will fabricate a spectacular fake edge, and it is worth
understanding before trusting any panel on a new market.

Walk-forward, defaults, one file per row:

```
symbol                bars   colour edge      z        BSS   size skill  coverage   dead
es1_15m_tradingview  42,744       -0.29%  -1.18   -0.00047      +10.65%     79.7%   0.0%
es1_3m_tradingview   20,419       -0.68%  -1.95   -0.00120       +3.04%     79.0%   0.0%
eurusd_1h             4,779       -0.65%  -0.90   -0.00300       +8.53%     80.1%   0.1%
xauusd_1h             1,959       -0.46%  -0.41   -0.00765       +2.65%     79.4%  27.5%
btcusd_1h             1,799       +1.72%  +1.46   +0.00011       +5.89%     79.0%   0.0%
aapl_1h               2,799       +0.39%  +0.42   -0.00420       +0.12%     79.8%   0.0%
spy_1day              1,799       -1.61%  -1.37   -0.00790       +5.46%     80.1%   0.0%
```

Five asset classes, two timescales, and **not one |z| above 2 on colour**. The
size model works everywhere but its magnitude varies a lot — ES 15m +10.7%,
EURUSD 1h +8.5%, SPY daily +5.5%, AAPL 1h +0.1%. Band coverage is 79–80% on all
seven, which is the strongest single result here: the uncertainty estimate is
calibrated across instruments without any per-symbol tuning.

### The dead-bar trap

XAU/USD 1h from one feed *originally* scored **+7.18 pp at z = 7.63**, BSS
+0.078 — an edge an order of magnitude larger than anything else, which is
exactly why it was worth distrusting rather than celebrating.

The diagnosis, in order:

1. Lag-1 transitions: `P(green | previous green) = 65.7%` vs
   `P(green | previous red) = 41.4%`. A 24-point spread; no liquid market does
   that at 1h.
2. XAU bar opens never equalled the previous close (0.0% of bars). Switching to
   the close-vs-previous-close basis, which ignores the open entirely, cut the
   edge to +4.47 pp — so a large part was an open-price construction artifact.
3. The remainder: **28.8% of the file was Saturday and Sunday bars**, with a
   median range of **0.27 against 14.12 on weekdays**. Gold does not trade on
   weekends. These are synthetic bars carrying a stale price.

Drop them and the edge becomes **−1.07 pp at z = −0.95** — indistinguishable
from every other instrument. The entire "edge" was dead bars.

The filter now ships on by default. Each bar is compared against a rolling
**median** range — a mean or an EWMA would be dragged down by the dead bars
themselves — and anything under `i_deadPct` (5%) of it is excluded from counting,
scoring, the EWMA, and any pattern containing one. It is inert on clean data
(0.0–0.1% flagged on six of the seven files) and removed 27.5% of the XAU file.
The panel reports the share it skipped; **above a few percent, go and look at
your data.**

### Using it on a new symbol

- Add it to any chart; there is nothing to configure per instrument.
- Check the **Dead bars skipped** row first. Orange means the feed is emitting
  synthetic bars.
- Set **Size basis** to *True range* on anything that gaps overnight (single
  stocks, ETFs, futures across sessions) so the forecast covers the gap.
- Expect the size skill to differ by market. Hourly single stocks were near zero
  in this sample; index futures and FX majors were strong.
- Let the scorecard fill before believing anything. Below ~200 scored bars the
  panel says so.

## Anti-repainting

## Anti-repainting

The ordering inside a confirmed bar is the whole design:

1. score the forecast that was locked at the previous close, against this bar;
2. fold this bar's outcome into the counts, keyed on the pattern *before* it;
3. advance the EWMA;
4. build the forecast for the next bar and lock it.

So a forecast is always produced by counts that cannot contain the bar it is
forecasting. Every number in the SCORECARD section is walk-forward
out-of-sample by construction — there is no in-sample mode to accidentally read.

All array mutation is gated on `barstate.isconfirmed`. This matters more than it
looks: `var` *scalars* roll back on each realtime tick, but array *contents* do
not, so an ungated `array.set` would permanently corrupt the counts with every
tick of the forming bar.

The panel shows the forecast locked at the previous close, describing the bar
now forming — it does not move while that bar forms. The two rows that do use
the live bar are labelled: the probability ladder, and the optional
"Next bar (provisional)" row.

## Reading the panel

- **Direction / P(green)** — the forecast. Compare with **Base rate P(green)**:
  if the edge row is ±0.5 pp, the model is telling you it has nothing.
- **95% CI (Wilson)** — small-sample bounds. If the interval straddles 50%, the
  point estimate is decoration.
- **Ladder** — per-level probabilities. If L1 through LN are all within a
  fraction of a point of each other, the deep pattern is adding nothing and you
  should lower N.
- **Expected range / band / body** — the part with measured skill. Useful for
  stop distance, target distance, position size, and option premium sanity.
- **SCORECARD** — Brier skill score above 0 means the probability forecast beats
  the base rate; the z-score tests the accuracy edge against always-majority.
  "Size MAE vs EWMA" above 0 means the state multiplier is earning its keep.
  With the split on, the left column is TRAIN and the right is HOLDOUT; the right
  column is the one that counts. **A positive BSS with |z| below 2 is noise, not
  an edge** — the split section above shows the same holdout flipping sign on a
  single setting change.
- **Size skill carried over** — holdout skill minus train skill. Above −3 pp the
  parameters generalise; below −8 pp they were fitted to the training window.
- **Verdict row** — collapses the above into one line, so the script cannot be
  mistaken for a signal generator on a symbol where it has no skill.

Alerts default to off and, when on, are gated on a positive Brier skill score.
Leave that gate on.

## Known limitations

- **Projected candle geometry assumes the Close-vs-Open colour basis.** Under
  Close-vs-Previous-Close the direction is exact but the body is anchored on the
  previous close, so the drawn shape is an approximation.
- **The regime split is untested.** It doubles the state space and needs far more
  history than a typical chart holds. Default off.
- **The 5% test window is small.** On a 5,000-bar chart it is 250 bars, where the
  standard error on accuracy is about 3 pp — enough to validate the size model,
  nowhere near enough to resolve a colour edge. Widen it, or judge colour on
  VALID, on short histories.
- **The dead-bar filter is a heuristic.** A genuinely quiet but real bar can be
  flagged on very illiquid instruments. Check the skipped share before trusting
  it, and lower `i_deadPct` if it is discarding live bars.
- **The z-score treats bars as independent.** Overlapping patterns are
  autocorrelated, so the true effective sample size is smaller than `n` and the
  z is mildly optimistic. It does not change the conclusion here — the edge is
  negative, and a correction only widens the interval around zero.
- **The split is an evaluation tool, not a live-trading mode.** Leaving
  `i_freeze` on during live use means the model stops learning at the boundary
  and never resumes. Turn the split off, or set freeze off, once you are done
  evaluating.
- **The band calibration window is a rolling sort.** At `i_bandWin` above ~1000
  on a long intraday chart this is the slowest part of the script.
- Compiled against the v6 language rules but not run through TradingView's
  compiler in this environment; the Python replica validates the *model*, not
  the Pine syntax.

## Reproducing

```bash
python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --nprev 3
python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --sweep
python3 backtest_next_candle_predictor.py data/es1_3m_tradingview.csv --basis close_close

# every dataset in data/, one row each
python3 backtest_next_candle_predictor.py --all

# 75 / 20 / 5 split
python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --split3

# grid on train, select on valid, read test once (~110s)
python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --tune

# turn the dead-bar filter off to see what it was protecting you from
python3 backtest_next_candle_predictor.py data/xauusd_1h.csv --dead-pct 0 --burn-in 200
```

The replica shares the model exactly — same pattern encoding, same back-off,
same predict-then-update ordering — so a disagreement between it and the panel
is a bug in one of them.
