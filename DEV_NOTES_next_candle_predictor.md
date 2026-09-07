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

## Train / holdout split

Walk-forward already makes every bar out-of-sample, so the split is not there to
fix a leak. It answers two things walk-forward structurally cannot:

1. **Is a parameter choice overfit?** If you tune `N`, `s`, `lambda` or the vol
   buckets by watching the panel, the panel is no longer an independent read —
   you have fitted to it. Tune on TRAIN, look at HOLDOUT once.
2. **Is the learned structure stable over time?** With learning frozen at the
   boundary, the holdout asks whether what the model learned years ago still
   describes the market now. Walk-forward can never answer this, because it
   keeps relearning.

`i_splitOn` turns it on; split by percent of chart (drifts as bars arrive) or by
a fixed date (stable, and what you want for a repeated read). The panel then
shows TRAIN and HOLDOUT side by side, the holdout region is tinted, and the
verdict row switches to reading the holdout column.

### What is frozen, and what is not

Frozen with `i_freeze`: the Markov counts, the size multiplier table, the
body/wick shares, and the band's error-ratio window — everything *fitted*.

**Not** frozen: the range EWMA. It is state, not a parameter. A frozen EWMA
would forecast the training window's volatility level forever, which would make
the holdout meaningless rather than honest.

### What it measures

`--split 0.75` on ES 15m (32,208 train / 10,737 holdout), defaults, frozen:

```
                            TRAIN         HOLDOUT
  model accuracy           50.21%          50.98%
  edge over majority      -0.43 pp        +0.43 pp
    z-score                 -1.52           +0.89
  Brier skill score      -0.00087        +0.00047
  size skill vs EWMA      +11.74%          +7.59%
  80% band coverage        79.67%          76.20%
```

Read carefully, because this is where people fool themselves. The holdout colour
BSS is **positive** — and it means nothing: z = +0.89 is well inside noise, and
running the identical split with `--no-freeze` flips the same holdout to
−0.05 pp (z −0.10). One switch, same data, the "edge" changes sign. That is the
signature of noise, and it is exactly why the panel prints the z-score next to
the edge rather than the edge alone.

The size half tells a different and more useful story. Skill decays from +11.74%
to +7.59% — real degradation, but it stays clearly positive on data the model
never saw. And band coverage falls to 76.2% frozen versus 79.5% still-learning:
**the multipliers are stable, the band calibration is not.** So freeze for the
stationarity test, but in live use let the band keep updating.

## Tuning without cheating

`--tune` grids parameters on the TRAIN portion only, picks the winner there, and
reads it once on the holdout. It also reports where the train-best config
*actually ranks* on the holdout, which is the diagnostic that matters:

```
colour — train-best: N=1  s_link=200    train BSS -0.00004  ->  holdout +0.00051
         holdout spread over the grid: -0.00133 .. +0.00059
         train-best lands at the 67th percentile on holdout

size   — train-best: lambda=0.97 shrink=40 size_n=2   train +16.90% -> holdout +11.76%
         holdout spread over the grid: +3.52% .. +12.29%
         train-best lands at the 92nd percentile on holdout
```

If tuning were pure noise-chasing the train-best config would land near the 50th
percentile on holdout — no better than picking at random. Colour lands at the
67th: barely distinguishable from chance, and its selected config still scores an
accuracy edge of −0.00 pp. **Do not tune the colour model.** Size lands at the
92nd: the selection transfers, and it lifts holdout skill from +7.59% at the
defaults to **+11.76%** — a 55% relative improvement that survives on data the
grid never touched.

The concrete finding: `lambda = 0.97` beats the 0.94 default. The RiskMetrics
convention is calibrated for daily returns, not 15-minute candle ranges, and a
slower EWMA fits this series better.

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

# train / holdout split, model frozen at the boundary
python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --split 0.75
python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --split 0.75 --no-freeze

# grid on train only, one read on the holdout (~65s)
python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --split 0.75 --tune
```

The replica shares the model exactly — same pattern encoding, same back-off,
same predict-then-update ordering — so a disagreement between it and the panel
is a bug in one of them.
