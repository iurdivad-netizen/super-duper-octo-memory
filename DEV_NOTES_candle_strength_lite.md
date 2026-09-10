# Next Candle Strength (Lite) — Dev Notes

`next_candle_strength_lite.pine` — Pine v6 indicator.
`probe_candle_strength.py` — bar-for-bar replica of the *original* formula, used
to decide what the rewrite should output.

A compact (354-line) correction of the widely-copied "Next Candle Predictor"
candle-strength script. It exists as an upgrade path for people running that
script; `candle_forecast_v2.pine` supersedes it on every axis except size.

## The short version

The pasted script's headline output is a next-candle **direction** call. Measured
across 10 instrument/timeframe files:

| | result |
|---|---|
| direction edge vs running majority | **negative in 55 of 66 configurations**; no configuration reaches z > +2 |
| worst cases | ES 15m z = −5.31, XAU 15m z = −4.71, XAU 5m z = −3.84, SPY daily z = −3.76 |
| inverting the signal | gross PnL ≈ 0 in train; **net negative in every configuration** at a 1-tick round trip |
| `\|pressure\|` vs next-bar range | **+0.03 .. +0.28**, positive on 9 of 10 files |

So the rewrite promotes the range forecast to the headline and demotes the
direction call to a row that scores itself and prints a verdict.

## What was actually wrong with the original

Ten defects, in descending order of how much they matter.

### 1. `ta.sma()` called from inside a `for` loop — silently wrong

```pinescript
getCandleStrength(_open, _high, _low, _close, _volume) =>
    avg_vol = math.max(ta.sma(_volume, len), 1)      // <-- here
    ...
for i = 1 to len
    total_strength += getCandleStrength(open[i], ..., volume[i])
```

Pine allocates one series instance per **call site**. The call site is inside
the loop, so a single SMA instance is fed `len` different values per bar. Its
window therefore holds the last `len` *calls*, not the last `len` *bars*, and
its value differs on every iteration. `avg_vol` is the average of nothing
meaningful, and `vol_factor` — the term the whole signal is multiplied by — is
garbage. No compile error; wrong numbers.

Fix: compute `ta.sma(volume, len)` once, at global scope, unconditionally.

### 2. Not scale-free — the default threshold cannot work on two instruments

`strength` carries **price units**. `prediction_threshold = 0.05` therefore
means something different on every symbol. Measured against typical
`|strength|` on the last 500 bars of each file:

```
es1_15m      threshold 0.05 =    0.1x typical strength
spy_1day     threshold 0.05 =    0.1x typical strength
eurusd_1h    threshold 0.05 =  639.0x typical strength   <- permanently Neutral
btcusd_1h    threshold 0.05 =    0.0x typical strength   <- never Neutral
xauusd_1h    threshold 0.05 =    0.0x typical strength   <- never Neutral
```

Fix: normalise every term by ATR and express the gate in ATR units.

### 3. The wick is added with the body's sign — backwards

```pinescript
strength = (body * body_weight + wick * wick_weight) * vol_factor * vol_weight * direction
```

`wick` is the *whole* non-body range and it is multiplied by the body's
`direction`. A green candle with a long upper wick — rejection at the highs —
scores as **more bullish** than a clean green marubozu with the same body. The
sign is wrong for the upper wick on green candles and for the lower wick on red
ones, i.e. half of each candle, on every bar.

Fix: split the wicks and give them opposing signs. Upper wick subtracts from
bullish pressure, lower wick adds:
`press = bodyN + wickW * (loWick - upWick)`.

### 4. Three weights, one and a half degrees of freedom

`vol_weight` multiplies the entire expression, so it only rescales `strength` —
and `strength` is compared against `prediction_threshold`, which also rescales.
`vol_weight` and `prediction_threshold` are the same knob. Likewise only the
*ratio* `body_weight : wick_weight` matters after that rescaling. Four inputs
expose about two real parameters, and the redundant pair is pure overfitting
surface.

Fix: one `wick_weight` and one ATR-unit gate.

### 5. Units error in the projected line

```pinescript
price_change := math.abs(avg_strength) * (high - low) * 2
```

`avg_strength` already carries price units, so this is price² × 2. On ES that
is roughly (5 pts)·(5 pts)·2 = 50 "points" of projected move for an ordinary
bar — about ten times the bar's own range. The drawn slope is not a forecast of
anything; its magnitude is a unit mistake.

Fix: the projection is the EWMA range forecast, in price units, drawn as a box.

### 6. A wasted bar of lag

`for i = 1 to len` reads bars `t-len .. t-1`. The label says "Next:" and the
line starts at the current close, so the script forecasts bar `t+1` from data
ending at `t-1`, discarding the most recent and most informative bar. Genuine
anti-repaint would use `[1]` *and* forecast bar `t`; this does neither.

(The probe tests the *better* variant — window ending at `t` — so the measured
results above are not penalised by this bug.)

### 7. Flat average over the window

`avg_strength = total_strength / len` weights the bar 5 ago exactly as much as
the last one.

Fix: `ta.ema(press, len)` — recency-weighted, O(1), one call per bar.

### 8. No `na`-volume guard

Many index and some FX feeds report `volume = na`. Then `vol_factor` is `na`,
`strength` is `na`, `total_strength` is `na`, and the whole indicator prints
nothing with no indication why.

Fix: detect the feed and fall back to `volF = 1.0`.

### 9. `math.max(avg_vol, 1)` is an absolute floor

Wrong for any instrument whose volume is legitimately fractional — crypto
quoted in coin units, where 0.4 BTC is a normal bar. Floor relative to the
data, not at the constant 1.

### 10. Nothing is measured, and the live bar repaints the drawing

`plotshape(... and barstate.islast)` draws only on the final bar, so there is no
historical footprint to check. There is no hit rate, no base rate, no
comparison to anything. Separately, `price_change` reads the *live* `high`/`low`
of the forming bar, so the projection wanders on every tick.

This is the defect that matters most. Given that the direction call measures
*worse than a coin that always says "up"*, a display that cannot be falsified
by looking at it is the difference between a tool and a decoration.

## Why direction is demoted, in three measurements

### 1. Cross-instrument accuracy

`python3 probe_candle_strength.py --all` — walk-forward, dead-bar filter on,
scored against the **running majority** colour (not against 50%):

```
file                     len   thr      n     acc    base    edge      z   |s|~rng
es1_15m_tradingview        3  0.05  25332  49.07%  51.39%   -2.33  -5.31   +0.272
es1_15m_tradingview        5  0.00  41313  49.72%  51.12%   -1.40  -4.08   +0.276
xauusd_15m                 3  0.00   4555  50.34%  54.75%   -4.41  -4.71   +0.048
xauusd_5m                  3  0.00  14482  53.16%  55.13%   -1.97  -3.84   +0.030
spy_1day                   3  0.00   1796  48.00%  53.95%   -5.96  -3.76   +0.162
btcusd_1h                  5  0.00   1799  47.25%  49.97%   -2.72  -1.68   +0.181
eurusd_1h                 10  0.00   4647  48.91%  50.94%   -2.02  -2.03   +0.077
aapl_1h                    3  0.05   1641  47.17%  51.37%   -4.20  -2.45   -0.023
```

66 configurations over 10 files: **negative in 55, no |z| above 2 on the
positive side.** Every positive-looking cell is a tiny sample — EUR/USD shows
+8.82pp on n = 102 (z = +1.22) and QQQ shows −20.34pp on n = 59. That is the
confidence-tail trap, not a signal.

**Note the base-rate column.** XAU 5m is 55.13% green. Scored against 50%
instead of its own base rate, this script's 53.16% would read as an edge; it is
in fact 1.97pp *worse* than a coin that always says green. Any candle-direction
claim that does not name its base rate is measuring drift.

### 2. The negative edge is not tradable by inversion

The signal is significantly *anti*-predictive on ES 15m, which invites the
obvious trade. It does not survive costs. Signal predicts bar `t+1`
close-vs-open, so the tradable expression is enter at `t+1` open, exit at `t+1`
close. Parameters read on the first 70%, last 30% read once:

```
 len   thr  window       n  gross pts/tr  t-stat  net @1tk  net @1.5tk
   3  0.00  train    29851        0.0208    0.54   -0.2292     -0.3542
   3  0.00  TEST     12883        0.1191    1.96   -0.1309     -0.2559
   5  0.00  train    29861       -0.0161   -0.41   -0.2661     -0.3911
   5  0.00  TEST     12883        0.0506    0.83   -0.1994     -0.3244
  10  0.05  train    14982       -0.0458   -0.76   -0.2958     -0.4208
  10  0.05  TEST      6581        0.1990    2.21   -0.0510     -0.1760
```

Two readings:

1. **Net is negative in all 12 cells**, even at an optimistic one-tick
   (0.25 pt) round trip. ES 1 tick = $12.50; 1.5 ticks with commission is the
   realistic figure for a market order.
2. **Gross is ~0 in every train window** (+0.02, −0.02, −0.05 pts) while the
   accuracy edge was −1.7pp at z = −5. That gap is the lesson: the accuracy
   asymmetry lives entirely in small-magnitude bars. A statistically solid
   direction edge worth 1.7pp converted to zero points of PnL. Accuracy is not
   profitability, and this is a clean, large-sample demonstration of it.

The TEST column looks better than train, which is the wrong direction for a
real effect and is why nothing was built on it.

### 3. Magnitude does carry information

The `|s|~rng` column above is the correlation between `|pressure|` and the next
bar's range: **positive on 9 of 10 files**, +0.27 on ES 15m, +0.18 to +0.23 on
BTC / EUR/USD / QQQ, near zero on gold. Same formula, same inputs — the sign is
worthless and the magnitude is not.

## What the rewrite outputs

Headline: **expected range for the next bar**, as EWMA(TR, λ=0.94) × a
volatility-bucket multiplier shrunk toward 1.0, with a non-parametric band from
the rolling percentiles of `realised / predicted`. Reported against ATR(14), a
baseline the model's own anchor cannot flatter. λ = 0.94 rather than 0.97: see
the v2 notes, where 0.97 turned out to be an artifact of scoring against a
moving anchor.

Demoted: the **direction call**, with a live scorecard — hit rate, running base
rate, edge in pp, paired z against always-majority, and a verdict row that says
`NO DIRECTIONAL EDGE (|z| < 2)` until proven otherwise. Historical calls are
marked on every bar by default, so the claim is checkable across the chart
rather than only on the last bar.

Alerts are gated on the scorecard showing |z| > 2 over ≥ 200 bars. An indicator
that has measured itself to have no edge should not be able to fire a signal.

## Anti-repainting

Ordering inside a confirmed bar:

1. score the forecast locked at the previous close against this bar;
2. fold this bar's outcome into the running counts and the bucket multiplier,
   keyed on the bucket *before* it;
3. lock the forecast for the next bar.

The running majority baseline is read **before** `nUp`/`nDn` are updated, so it
never contains the bar it is being compared on. Every scorecard number is
walk-forward by construction; there is no in-sample mode to read by accident.

All 21 accumulator mutations sit inside `if barstate.isconfirmed` (verified
mechanically, not by eye). This matters more than it looks: `var` scalars roll
back on each realtime tick, so an ungated `+=` would permanently inflate the
counts on every tick of the forming bar. The four deliberate exceptions are the
range EWMA — a var scalar that *should* roll back and recompute per tick — and
the three drawing handles under `barstate.islast`.

## Known limitations

- **Compile status: linted, not compiled.** `tools_pinelint.py` reports 0
  errors; the 10 warnings are genuine continuation lines, which Pine requires
  to be indented by a non-multiple of 4. The linter is not a compiler.
- **The band is biased toward 1.0 during burn-in**, because
  `ta.percentile_nearest_rank` is fed `nz(ratio, 1.0)` on bars before the first
  forecast exists. It washes out within `i_bandWin` bars.
- **Only 3 volatility buckets and no other size features.** The v2 ablation
  found `volZ` and `rngRatio` carry the size model; this script uses the range
  bucket only. Expect less size skill than v2's +6..18% over ATR(14).
- **The paired z treats bars as independent.** Overlapping EMA windows are
  autocorrelated, so the effective sample is smaller than `n` and |z| is mildly
  optimistic. It does not change the conclusion — a correction only widens the
  interval around zero.
- **The dead-bar filter is a heuristic.** Check the skipped share before
  trusting anything; above a few percent, go and look at the feed.
- **This is the lite version.** If you want the argument made properly — 16
  features, online logistic regression, a regularisation sweep, an ablation and
  a confidence-decile table — read `candle_forecast_v2.pine`.

## Reproducing

```bash
python3 probe_candle_strength.py data/es1_15m_tradingview.csv
python3 probe_candle_strength.py --all
python3 tools_pinelint.py next_candle_strength_lite.pine
```

## Bottom line

The formula in the original script is a lagging momentum measure with a broken
volume term, presented as a forecast. Its direction call is worse than the base
rate on the two largest samples available here and unprofitable in both
directions after costs. Its magnitude predicts the next bar's *size*, which is
what the rewrite forecasts.

Same as v1 and v2 reached by other routes: size the trade, do not pick the
colour.
