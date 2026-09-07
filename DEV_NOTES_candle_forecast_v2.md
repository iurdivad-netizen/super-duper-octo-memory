# Candle Forecast v2 — Dev Notes

`candle_forecast_v2.pine` — Pine v6 indicator.
`backtest_candle_forecast_v2.py` — pure-stdlib bar-for-bar replica used to validate it.

A ground-up rebuild of the next-candle predictor. It shares no code with v1 and
reaches a stronger version of the same conclusion, plus a materially better size
model.

## The short version

| | v1 | v2 | measured on |
|---|---|---|---|
| Direction | no edge | **still no edge — but now proven, not merely unfound** | 7 files, 5 asset classes |
| Size skill | +10.7% vs its own EWMA anchor | **+5.9% to +18.0% vs ATR(14)**, a baseline it cannot flatter | same |
| Band coverage | 79–80% | 76–86%, centred on 80% | same |

## Why start over

v1's model saw only the last N candle **colours**. That is at most N bits per
prediction, spread over `2^N` buckets. When such a model reports "no edge", it
cannot distinguish *there is no signal in colour sequences* from *there is no
signal at all* — and the second is the claim anyone actually cares about.

v2 replaces the colour-bucket state with a 16-dimensional continuous feature
vector and an online logistic regression. The model now has access to size,
location, volatility, participation and regime — and still finds nothing. That
is a far stronger negative result, and it is the main deliverable here.

The second reason: v1's 75/20/5 split gave the middle window a job
(hyperparameter selection) that requires **multiple passes over the data**, which
Pine cannot do. So the shipped Pine ran different semantics from the Python that
produced its published numbers. v2's protocol is single-pass by construction.

## Architecture

### Features (16 + bias), all scale-free

`ret1..ret3` (bodies / ATR) · `mom5`, `mom20` (momentum / ATR) · `clsPos` (close
location in bar) · `rngRatio` (log range/ATR) · `wickSkew` · `stochPos` (location
in 20-bar range) · `runLen` (signed run, capped) · `volZ` (log volume /
20-bar average) · `gap` (open − prev close, / ATR) · `acorr` (50-bar mean of
`sign(body_t)·sign(body_{t-1})` — a trending-vs-mean-reverting regime meter) ·
`bodyFrac` · and two interactions, `mom5 × acorr` and `stochPos × acorr`.

The interactions are the one deliberate non-linearity: whether momentum or
mean-reversion applies is regime-dependent, and a purely linear model cannot say
that. (The ablation below shows they earn nothing. That is itself informative.)

Every feature is z-scored by a **running Welford normaliser**, causal, updated
after the bar is used. This is what makes one script work on ES 3m and SPY daily
with no per-symbol settings — the model sees standardised units regardless of
whether a "big move" is 0.3 points or 300.

### Estimators

- **Direction** — logistic regression, AdaGrad SGD, L2. AdaGrad matters: it gives
  per-feature adaptive step sizes, so a rarely-informative feature is not
  swamped by a high-variance one, without any tuning.
- **Size** — linear model on `log(next TR / EWMA)`, same optimiser. Prediction is
  `EWMA · exp(w·x)`, clamped to `exp(±1.5)`.
- **Band** — the empirical 10th/90th percentiles of the rolling `realised/predicted`
  ratio. Non-parametric, so it does not assume a distribution that candle
  ranges do not have.

### The 75 / 20 / 5 protocol

| window | job |
|---|---|
| **TRAIN** 75% | SGD fits the weights |
| **TEST** 20% | weights frozen — one clean out-of-sample read |
| **CALIB** 5% | weights *still* frozen; a two-parameter Platt rescale of the logit is fitted, and nothing else |
| **LIVE** | past the chart's history: everything frozen, calibration applied |

Boundaries come from `last_bar_index`, captured on the first executed bar so
realtime bars cannot shift them.

This is the design that made the whole thing fit inside Pine. Gradient descent
learns its weights in one left-to-right pass, so no window is ever visited
twice — unlike a grid search. **The panel's TEST column is therefore the same
number the replica prints**, which was not true of v1.

### What is deliberately NOT frozen

The **intercept** and the **range EWMA**. Both are state, not fitted parameters.

This is not a detail. The unconditional green rate drifts hard — it is 55.7% in
the ES 3m TEST window. With a frozen intercept, the model scored **z = −2.68
against the trivial majority rule**, which reads as "the model is actively
harmful" but actually means "the model cannot track a base rate that moved."
Letting slot 0 keep updating moved it to z = −1.78, i.e. indistinguishable from
no signal, which is the honest reading. The majority baseline uses a *running*
base rate; the model must be allowed the same or the comparison is rigged
against it.

## Results

`python3 backtest_candle_forecast_v2.py --all`, defaults, TEST window:

```
file                         bars     edge      z   LLskill     size   cover
aapl_1h.csv                  3000   +3.67%  +1.39  -0.01183   +8.63%   76.3%
btcusd_1h.csv                2000   -1.75%  -0.50  -0.00734  +11.46%   85.5%
es1_15m_tradingview.csv     42945   -0.37%  -0.54  -0.00064  +16.31%   79.8%
es1_3m_tradingview.csv      20620   -1.02%  -1.75  -0.00191   +7.78%   80.0%
eurusd_1h.csv                5000   +0.90%  +0.40  -0.00504  +17.97%   81.7%
spy_1day.csv                 2000   -1.00%  -0.54  -0.00547  +14.31%   81.0%
xauusd_1h.csv                3000   +5.53%  +1.63  +0.00069   +8.41%   80.5%
```

`size` is MAE reduction against **ATR(14)** — a reference the model's own EWMA
anchor cannot flatter. Seven files, five asset classes, two orders of magnitude
of timeframe: **no |z| above 2 on direction, positive size skill on every one.**

## Three measurements that make the negative result stick

### 1. Regularisation sweep — the direction optimum is "no features"

TEST log-loss skill as L2 rises from 1e-5 to 1e-1:

```
                         1e-05     0.0001      0.001      0.003       0.01       0.03        0.1
es1_15m               -0.00075   -0.00075   -0.00074   -0.00071   -0.00064   -0.00048   -0.00018
es1_3m                -0.00217   -0.00217   -0.00214   -0.00209   -0.00191   -0.00153   -0.00079
eurusd_1h             -0.00535   -0.00535   -0.00532   -0.00526   -0.00506   -0.00457   -0.00331
spy_1day              -0.00658   -0.00657   -0.00646   -0.00623   -0.00547   -0.00373   -0.00046
aapl_1h               -0.01242   -0.01242   -0.01236   -0.01224   -0.01183   -0.01076   -0.00782
xauusd_1h             -0.02738   -0.02735   -0.02707   -0.02647   -0.02452   -0.02019   -0.01259
MEAN                  -0.00882   -0.00882   -0.00875   -0.00860   -0.00811   -0.00699   -0.00466
```

Direction improves **monotonically** as the weights are shrunk toward zero, on 6
of 7 files. Extrapolated, the optimum is L2 = ∞ — a model with no features. The
features are not underexploited; they are net noise.

Over the same sweep, **size skill is flat**: 11.78% → 11.57% mean. A signal that
survives four orders of magnitude of regularisation is real. One that improves
as you delete it is not.

### 2. Ablation — every direction feature is a liability

ES 15m, TEST, zeroing one feature at a time:

```
      (none)       -0.00075   size +18.30%
      bodyFrac     -0.00019   size +18.17%   (Δ +0.00056 / -0.13pp)
      mom5xAc      -0.00038   size +18.28%   (Δ +0.00037 / -0.01pp)
      stochPos     -0.00050   size +18.24%   (Δ +0.00025 / -0.06pp)
      acorr        -0.00051   size +18.31%   (Δ +0.00023 / +0.01pp)
      ...
      volZ         -0.00071   size +15.18%   (Δ +0.00004 / -3.12pp)
      rngRatio     -0.00073   size +16.88%   (Δ +0.00002 / -1.41pp)
```

Removing a feature *improves* direction in 11 of 16 cases. For size, exactly
three features carry the model: `volZ` (−3.12pp when removed), `rngRatio`
(−1.41pp), `bodyFrac` (−0.13pp). The other thirteen are worth ~0.

A lean 3-feature size model matches or beats the full one on 5 of 7 files but
loses 6pp on SPY daily — daily ranges genuinely use trend context that intraday
ones do not. Rather than hard-code a feature set per timeframe, L2 = 0.01 lets
the regulariser shrink the dead features per instrument. That is the setting
that ships.

### 3. Confidence deciles — no edge hiding in the tails

The standard last hope is that the model is right when it is *confident*. It is
not. Scored against each window's own base rate:

```
file                    slice              n      acc  baserate     edge      z
es1_15m_tradingview.csv top 10%          858   50.12%    50.53%   -0.41  -0.24
                        top 25%         2147   51.23%    50.53%   +0.70  +0.65
es1_3m_tradingview.csv  top 10%          412   54.85%    55.65%   -0.80  -0.33
                        top 25%         1031   56.55%    55.65%   +0.90  +0.58
eurusd_1h.csv           top 10%          100   52.00%    52.50%   -0.50  -0.10
spy_1day.csv            top 10%           40   55.00%    53.00%   +2.00  +0.25
```

Every |z| below 1.

**The trap in this table is worth internalising.** Measured against 50% instead
of the base rate, ES 3m's top-25% slice reads *54.8% accurate, z = +3.08* — a
publishable-looking edge. But that window is 55.65% green, so a coin that always
says "green" beats it. Any candle-direction claim that does not name its base
rate is measuring the market's drift and calling it a model.

## The lambda finding — and a correction to v1

v1 concluded that `lambda = 0.97` beat the 0.94 default. That was measured
against the model's own EWMA anchor, which moves when lambda moves — a moving
target. Scored against a **fixed** reference (ATR(14)):

```
lam       own-anchor   vs EWMA.90   vs ATR14      <- es1_15m
0.99         +20.11%       -2.26%     +2.11%
0.97         +20.56%       +7.32%    +11.27%
0.94         +18.30%      +12.56%    +16.30%
0.90         +13.19%      +13.19%    +16.90%
0.80          +6.11%      +11.71%    +15.48%
```

The own-anchor column peaks at 0.99 — the slower the anchor, the more "skill" the
model appears to add, because it is being graded against a worse baseline. The
fixed-reference columns peak at 0.90–0.94.

Selected properly (best λ on **TRAIN** only, per file, then TEST read once):
TRAIN picks 0.90 on 5 of 7 files and 0.94 on another; TEST then confirms 0.94
beats 0.97 on 5 of 7. **0.94 ships.** v1's 0.97 was an artifact of its own
scoring convention.

## Anti-repainting

Ordering inside a confirmed bar:

1. score the forecast locked at the previous close, against this bar;
2. update the weights with that same (features, outcome) pair;
3. rebuild this bar's features and fold them into the normaliser;
4. lock the forecast for the next bar.

A forecast is therefore always produced by weights that never saw the bar it
forecasts. Every number in the scorecard is walk-forward by construction.

All array mutation sits inside `if barstate.isconfirmed`. This matters more than
it looks: `var` **scalars** roll back on each realtime tick, but array
**contents** do not, so an ungated `array.set` would permanently corrupt the
weights with every tick of the forming bar. There are 22 mutating call sites and
all 22 are inside that block (verified mechanically, not by eye).

## Reading the panel

Read the **TEST** column, then the **verdict** row, then stop.

- **edge vs majority / paired z** — the z is a paired test on per-bar
  correctness against always-predicting-the-majority-colour, not against 50%.
  Below |2| it is noise regardless of what the accuracy number looks like.
- **log-loss skill / Brier skill** — above 0 means the probability beats the base
  rate. These will be negative on almost every symbol.
- **size skill vs ATR** — the honest headline. The "vs EWMA" row beside it is the
  flattering one, shown so the two can be compared.
- **band coverage** — should land near the target (80% by default). This is the
  most reliably calibrated output in the script.
- **dead bars** — orange above 3%. See below.
- **volume feed** — orange when absent. `volZ` is the single strongest size
  feature; on a feed without volume the size model runs on `rngRatio` alone and
  skill drops.

Alerts are gated on the TEST window having shown |z| > 2 with ≥200 bars. Leave
that gate on.

## Using it on a new instrument

There is nothing to configure per symbol — that is the point of the running
normaliser. In order:

1. Check **dead bars**. Above a few percent, go and look at your data. v1
   documented a case where 28.8% synthetic weekend bars on a gold feed
   manufactured a +7.18pp "edge" at z = 7.63. That filter is carried over here
   unchanged because the failure it prevents is spectacular.
2. Check **volume feed**.
3. Let the TEST window fill. Below 200 scored bars the verdict says so.
4. Expect the direction verdict to say "no edge". Expect size skill between
   roughly +5% and +18%.

## Known limitations

- **Not compiled by TradingView in this environment.** The script passes
  `tools_pinelint.py` (0 errors) and every shared constant is checked against the
  replica programmatically, but the replica validates the *model*, not Pine
  syntax. Compile it before trusting it.
- **ATR warmup differs slightly.** The replica seeds Wilder's RMA with the first
  TR; `ta.atr()` seeds with an SMA of the first 14. They converge within ~50
  bars and the difference is inside the burn-in.
- **Quantiles refresh every 20 bars, not every bar.** Sorting a 500-element
  window on every one of 40,000 bars is the slowest thing this script can do, and
  rolling quantiles barely move in 20 bars. Set `i_reQ = 1` for exact-per-bar at
  a large speed cost.
- **The 5% CALIB window is small.** On a 5,000-bar chart it is 250 bars — enough
  to fit two Platt parameters, nowhere near enough to resolve a direction edge.
- **Platt calibration is nearly a no-op here.** Fitted `a = 0.94, b = −0.04` on ES
  15m: the raw logit was already close to calibrated, because it is close to
  constant. On a model with real signal this window would matter more.
- **The paired z treats bars as independent.** Overlapping feature windows are
  autocorrelated, so the effective sample is smaller than `n` and |z| is mildly
  optimistic. It does not change the conclusion — a correction only widens the
  interval around zero.
- **BTC band coverage runs hot (85%)** — fat tails plus a 500-bar band window on a
  2,000-bar file. Shorten `i_bandWin` on short crypto charts.
- **`i_freeze` is an evaluation setting, not a live-trading one.** Leaving it on
  in live use means the model stops learning at the 75% boundary forever. Turn it
  off once you have read the TEST column.

## Reproducing

```bash
python3 backtest_candle_forecast_v2.py data/es1_15m_tradingview.csv --weights
python3 backtest_candle_forecast_v2.py --all
python3 backtest_candle_forecast_v2.py data/es1_15m_tradingview.csv --ablate
python3 backtest_candle_forecast_v2.py data/es1_3m_tradingview.csv --nofreeze   # frozen vs continuous
python3 backtest_candle_forecast_v2.py data/spy_1day.csv --l2 0.1               # the L2 sweep, by hand
python3 tools_pinelint.py candle_forecast_v2.pine
```

## Bottom line

Next-candle **direction** is not forecastable from chart data by this class of
model, and v2 spends most of its effort proving that in three independent ways
rather than asserting it. Next-candle **size** is forecastable, by 6–18% over
ATR(14), consistently, across every instrument tested — and the 80% band is the
best-calibrated thing in the script.

Size the trade, do not pick the colour.
