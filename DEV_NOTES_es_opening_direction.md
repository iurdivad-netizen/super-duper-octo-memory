# ES "08:00 candle decides, 09:30 entry, 10/40 bracket" — backtest notes

**Idea tested:** on ES 15m — the first 15-minute candle at 08:00 ET decides the
direction for the day; take that direction at the 09:30 open; 10-point stop,
40-point target.

**Verdict: it loses, and both halves are broken.** Run on real ES 15m data
(234 sessions, Oct 2025 – Aug 2026), the strategy as specified returns
**-1.64 points per trade, -$19,150 per contract, PF 0.80, max drawdown
-$22,925**. The 08:00 candle agrees with the session's direction **50.4%** of
the time — a coin flip — and the 10-point stop is hit inside the 09:30 entry
candle itself on **46%** of trades. The bracket needs a 21% target-first rate
to break even and gets 13.2%.

The proxy study that follows (520 sessions of S&P cash data) reached the same
conclusion about the bracket before the ES data arrived, and predicted the
target-first rate to within ~3 points.

---

## Run on real ES 15m data (the definitive test)

`data/es1_15m_tradingview.csv` — TradingView export of `CME_MINI:ES1!`, 15m,
21,512 bars, 2025-09-30 → 2026-08-28, timestamps in exchange time with the DST
offset per row. 234 sessions have both an 08:00 signal candle and an 09:30
entry.

```
python3 backtest_es_15m.py data/es1_15m_tradingview.csv
```

| resolution | n | TP% | SL% | EOD% | E[pts] | net $ | maxDD $ | PF |
|---|---|---|---|---|---|---|---|---|
| pessimistic / heuristic / optimistic | 234 | 13.2 | 76.5 | 10.3 | **-1.64** | **-19,150** | -22,925 | 0.80 |

All three columns are identical because **0.0%** of trades hit a 15m bar
containing both levels — a 50-point spread rarely fits inside one ES 15m bar.
The result is exact, not bounded.

Split out:

| cut | n | TP% | SL% | E[pts] | net $ |
|---|---|---|---|---|---|
| signal long | 121 | 11.6 | 78.5 | -2.34 | -14,138 |
| signal short | 113 | 15.0 | 74.3 | -0.89 | -5,012 |
| 2025 (from Oct) | 64 | 17.2 | 76.6 | -0.93 | -2,962 |
| 2026 (to Aug) | 170 | 11.8 | 76.5 | -1.90 | -16,188 |

### The 08:00 candle carries no directional information

This is the half the proxy study could not measure. Measured directly, against
the session's own 09:30-to-close direction:

| | |
|---|---|
| signal agrees with the session direction | **50.4%** of 234 sessions (z = +0.13) |
| mean move in the signal's direction | +0.80 pts (t = +0.27) |
| median favourable excursion | 28.4 pts |
| median adverse excursion | 26.5 pts |
| **stopped out inside the 09:30 entry candle** | **46.2%** |

A coin flip. And the excursion pair is the whole story in two numbers: the
median trade goes 28.4 points your way and 26.5 points against you at some
point in the session, so a 10-point stop with a 40-point target sits on the
wrong side of both — it is far inside the noise and far outside the reach.

### No stop/target pair rescues it

Expectancy in ES points per trade, net of 0.5 points cost, 08:00 signal and
09:30 entry held fixed:

| stop \ target | 10 | 15 | 20 | 25 | 30 | 40 | 50 | 60 |
|---|---|---|---|---|---|---|---|---|
| 5 | -0.99 | -0.86 | -1.09 | -1.11 | -1.66 | -1.85 | -1.80 | -2.22 |
| 10 | -0.88 | -0.94 | -0.70 | -0.68 | -1.14 | **-1.64** | -1.69 | -2.32 |
| 15 | -0.41 | -0.68 | 0.06 | 0.40 | -0.09 | -0.56 | -0.55 | -1.17 |
| 20 | -1.07 | -0.75 | 0.59 | *1.38* | 0.88 | 0.66 | 0.37 | 0.24 |
| 25 | -0.98 | -0.56 | 0.61 | 1.32 | 1.01 | 0.88 | 0.38 | -0.09 |
| 30 | -1.42 | -0.92 | -0.03 | 0.86 | 0.24 | 0.12 | -0.86 | -1.46 |
| 40 | -1.93 | -1.45 | -0.28 | 0.59 | -0.51 | -0.59 | -1.85 | -2.26 |

The best cell (20/25) is t = +0.97 and it is the best of 56 tried — that is
what the maximum of 56 noisy draws looks like, not an edge.

### Entering at 10:00 instead of 09:30

Delaying the entry does help mechanically — the opening noise is behind you, so
fewer trades are killed immediately:

| | 09:30 entry | 10:00 entry |
|---|---|---|
| stopped inside the entry candle | 46.2% | 33.3% |
| stop-first | 76.5% | 71.8% |
| target-first | 13.2% | **17.1%** (break-even is 21%) |
| expectancy | -1.64 pts | **+0.46 pts** |
| net, 1 contract | -$19,150 | **+$5,388** |
| profit factor | 0.80 | 1.06 |

That flips the sign, and it is a real effect rather than a fluke of one month —
but it does not make the strategy work, for three reasons.

**1. The signal still contributes nothing.** Run the same 10:00 entry with the
signal, with the signal inverted, and with the signal ignored entirely:

| entry | as specified | inverted | always long | always short |
|---|---|---|---|---|
| 09:30 | -1.64 (t -1.41) | +0.93 (t +0.71) | -0.68 (t -0.56) | -0.02 (t -0.02) |
| 09:45 | -1.38 (t -1.20) | +0.69 (t +0.54) | +0.30 (t +0.25) | -1.00 (t -0.83) |
| **10:00** | **+0.46 (t +0.37)** | +0.47 (t +0.37) | +0.29 (t +0.24) | +0.64 (t +0.50) |
| 10:15 | +0.99 (t +0.78) | +0.62 (t +0.49) | +0.91 (t +0.74) | +0.69 (t +0.54) |
| 10:30 | -0.14 (t -0.12) | +0.27 (t +0.22) | +0.30 (t +0.26) | -0.18 (t -0.14) |
| 11:00 | -0.42 (t -0.37) | -0.47 (t -0.40) | -1.96 (t -1.90) | +1.06 (t +0.84) |
| 11:30 | -1.07 (t -0.99) | -1.62 (t -1.51) | -1.55 (t -1.49) | -1.14 (t -1.02) |
| 12:00 | -0.48 (t -0.45) | -0.42 (t -0.38) | -1.17 (t -1.15) | +0.27 (t +0.24) |

At 10:00 the signal (+0.46), its exact opposite (+0.47), a permanent long
(+0.29) and a permanent short (+0.64) all return the same thing. Whatever
improved between 09:30 and 10:00 improved for *every* direction rule equally,
which is the definition of it not being the signal. No cell in the 32-cell grid
reaches t = +0.85.

**2. The bracket is still upside-down; the profit is end-of-day drift.**
Decomposing the +107.8 point total:

| outcome | trades | share | total pts | $ |
|---|---|---|---|---|
| target | 40 | 17.1% | +1,580.0 | +79,000 |
| stop | 168 | 71.8% | -1,764.0 | -88,200 |
| end of day | 26 | 11.1% | +291.8 | +14,588 |
| **total** | **234** | | **+107.8** | **+5,388** |

The bracket itself loses 184 points. Every point of profit — and then some —
comes from the 26 sessions (11% of trades) where neither level was touched and
price happened to drift the right way by the close. That is not the system
described; it is a coin-flip directional position held to 16:00.

**3. It is inside the noise, and one month carries it.** t = +0.37, bootstrap
95% CI **-1.95 to +2.91** points per trade (-$22,775 to +$34,075). February 2026
alone contributes +154.8 of the +107.8 point total (**144%**), and only 5 of 11
months are profitable. Monthly, in points: `Oct -60, Nov -40, Dec -42, Jan -93,
Feb +155, Mar +69, Apr +57, May -56, Jun +42, Jul +144, Aug -67`.

A 56-cell stop/target sweep at the 10:00 entry puts 53 cells negative; 10/40 is
the peak of that surface at t = +0.37. Median excursions from 10:00 are 24.0
points favourable and 23.9 adverse — still a 10-point stop inside the noise with
a 40-point target beyond the median reach.


### A 25-point stop, across take-profits

09:30 entry, 08:00 signal, stop 25:

| target | break-even TP% | actual TP% | SL% | EOD% | E[pts] | E[R] | t | net $ | maxDD $ | PF | 1st half | 2nd half |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15 | 63.8 | 59.4 | 35.5 | 5.1 | -0.56 | -0.022 | -0.45 | -6,538 | -16,050 | 0.94 | -0.32 | -0.80 |
| 20 | 56.7 | 53.4 | 38.5 | 8.1 | +0.61 | +0.024 | +0.43 | +7,088 | -15,588 | 1.06 | +1.54 | -0.33 |
| **25** | 51.0 | 47.9 | 41.0 | 11.1 | **+1.32** | +0.053 | +0.85 | **+15,488** | **-12,500** | 1.12 | +1.80 | +0.84 |
| 30 | 46.4 | 39.3 | 43.6 | 17.1 | +1.01 | +0.040 | +0.61 | +11,812 | -21,475 | 1.09 | +1.93 | +0.09 |
| 35 | 42.5 | 33.8 | 46.6 | 19.7 | +0.78 | +0.031 | +0.44 | +9,100 | -24,588 | 1.06 | +1.72 | -0.16 |
| 40 | 39.2 | 27.4 | 47.4 | 25.2 | +0.88 | +0.035 | +0.47 | +10,238 | -26,738 | 1.07 | +2.72 | -0.97 |
| 50 | 34.0 | 19.2 | 49.6 | 31.2 | +0.38 | +0.015 | +0.19 | +4,450 | -25,238 | 1.03 | +1.63 | -0.87 |
| 60 | 30.0 | 13.7 | 50.9 | 35.5 | -0.09 | -0.004 | -0.05 | -1,100 | -31,338 | 0.99 | +1.80 | -1.99 |
| 75 | 25.5 | 7.7 | 51.3 | 41.0 | +0.30 | +0.012 | +0.14 | +3,538 | -28,425 | 1.02 | +2.58 | -1.97 |
| 100 | 20.4 | 3.0 | 51.7 | 45.3 | +0.06 | +0.002 | +0.03 | +725 | -30,400 | 1.00 | +3.43 | -3.31 |

Best is 25/25 at +1.32 points (+$15,488, PF 1.12, t = +0.85), and it is one of
only two settings in the study positive in both halves of the sample. It does
not beat 20/25 (+1.38 pts, +0.069 R, t = +0.97, 7/11 green months) on any
measure, so widening from 20 to 25 adds nothing.

The optimum is a plateau rather than a spike, which is at least the right shape:

| stop \ target | 20 | 25 | 30 |
|---|---|---|---|
| 15 | +0.06 (+0.05) | +0.40 (+0.32) | -0.09 (-0.06) |
| 20 | +0.59 (+0.46) | **+1.38 (+0.97)** | +0.88 (+0.57) |
| 25 | +0.61 (+0.43) | +1.32 (+0.85) | +1.01 (+0.61) |
| 30 | -0.03 (-0.02) | +0.86 (+0.51) | +0.24 (+0.14) |

### The stop-size curve, and what it says

Holding the target at 40 and varying only the stop:

| stop | SL% | TP% | EOD% | **E[R]** |
|---|---|---|---|---|
| 5 | 90.2 | 6.4 | 3.4 | **-0.369** |
| 10 | 76.5 | 13.2 | 10.3 | -0.164 |
| 15 | 65.4 | 20.1 | 14.5 | -0.038 |
| 20 | 55.1 | 24.8 | 20.1 | **+0.033** |
| 25 | 47.4 | 27.4 | 25.2 | +0.035 |
| 30 | 42.3 | 28.6 | 29.1 | +0.004 |
| 35 | 38.0 | 30.3 | 31.6 | -0.009 |
| 40 | 33.3 | 30.8 | 35.9 | -0.015 |
| 50 | 21.8 | 33.8 | 44.4 | +0.016 |

This curve is the clearest single picture in the study. Per unit of risk the
system climbs steeply from -0.37 R at a 5-point stop, crosses zero between 15
and 20 points, and then **flattens along zero** — every stop from 20 to 50 sits
within ±0.04 R of break-even.

That shape is the signature of a coin-flip signal. A stop inside the noise
imposes a penalty proportional to how far inside it sits; widening the stop
removes that penalty and the system converges to the drift it is actually
trading, which is zero. A real directional edge would keep climbing past zero as
the stop stopped truncating winners. This one asymptotes at nothing.

So the honest answer to "does a wider stop help": it stops the bleeding, and
that is all it can do. 25 points is on the plateau; so is 20; 10 was below it.


### Are the timestamps shifted? And does moving the whole thing an hour help?

**The timestamps are not shifted.** The export's own volume profile settles it —
median 15m volume by time of day:

| time | median volume |
|---|---|
| 08:30 | 8,630 |
| 09:15 | 13,281 |
| **09:30** | **86,097** |
| 09:45 | 66,430 |
| 10:00 | 61,951 |
| **15:45** | **113,900** |
| 16:00 | 34,784 |

Volume jumps 6.5× into the bar labelled 09:30 and peaks in the bar labelled
15:45 — the cash-equity open and the closing bar into 16:00. If the file were an
hour out, that spike would sit at 10:30. TradingView stamps each row with the
exchange offset (-04:00 in EDT, -05:00 in EST, both present in this file), and
the loader strips the offset so the wall-clock is exchange time. Anyone
inheriting this repo can re-run the check as a data sanity test.

**Moving the setup an hour earlier makes it worse.** Signal at 07:00, entry at
08:30:

| bracket | n | TP% | SL% | E[pts] | net $ | PF |
|---|---|---|---|---|---|---|
| 10/40 | 235 | 15.3 | 81.3 | -2.17 | -25,462 | 0.75 |
| 20/40 | 235 | 20.4 | 67.2 | -4.92 | -57,862 | 0.65 |
| 20/25 | 235 | 34.5 | 58.7 | -3.51 | -41,275 | 0.71 |

An 08:30 entry sets its stop during quiet pre-market and then sits through the
09:30 range expansion, so the 10-point stop-out rate rises to 81.3%.

### The whole clock, tested at once

Rather than keep moving the hours one at a time, every signal time against every
entry time, expectancy in points with the t-statistic:

**stop 10 / target 40**

| signal \ entry | 08:30 | 09:30 | 09:45 | 10:00 | 10:30 | 11:00 |
|---|---|---|---|---|---|---|
| 06:00 | +0.70 (+0.53) | +1.17 (+0.89) | -0.92 (-0.76) | -0.29 (-0.24) | -0.12 (-0.10) | +0.23 (+0.19) |
| 07:00 | -2.17 (-1.83) | -1.11 (-0.92) | -0.67 (-0.55) | +1.34 (+1.03) | +0.36 (+0.30) | -0.57 (-0.50) |
| 08:00 | -0.60 (-0.48) | -1.64 (-1.41) | -1.38 (-1.20) | +0.46 (+0.37) | -0.14 (-0.12) | -0.42 (-0.37) |
| 09:00 | — | +1.49 (+1.14) | +0.75 (+0.60) | +0.99 (+0.78) | +0.84 (+0.68) | +0.47 (+0.40) |
| 09:15 | — | -1.51 (-1.28) | -1.10 (-0.95) | -0.68 (-0.58) | -1.69 (-1.58) | -2.34 (-2.20) |

**stop 20 / target 25**

| signal \ entry | 08:30 | 09:30 | 09:45 | 10:00 | 10:30 | 11:00 |
|---|---|---|---|---|---|---|
| 06:00 | +1.17 (+0.82) | +0.79 (+0.56) | -0.17 (-0.12) | -0.55 (-0.40) | -0.68 (-0.50) | -0.29 (-0.23) |
| 07:00 | -3.51 (-2.55) | -0.86 (-0.61) | -0.27 (-0.19) | +0.87 (+0.63) | -0.85 (-0.63) | -1.06 (-0.83) |
| 08:00 | +0.24 (+0.17) | +1.38 (+0.97) | -1.25 (-0.89) | -0.39 (-0.28) | -0.20 (-0.15) | -0.32 (-0.25) |
| 09:00 | — | +1.64 (+1.15) | +2.02 (+1.44) | +2.20 (+1.59) | +0.76 (+0.57) | +0.54 (+0.42) |
| 09:15 | — | -1.55 (-1.11) | -2.73 (-1.99) | -1.06 (-0.78) | -2.22 (-1.67) | -2.75 (-2.22) |

**The strongest cell in 56 is t = +1.59.** Across 56 independent-ish draws of
pure noise the largest |t| you would expect is about **2.84**, and the extremes
here are +1.59 and -2.55. The surface is not merely insignificant — it is
*flatter than chance would produce*, which is what a grid with no signal in it
looks like. There is no hour of the morning where reading a 15-minute candle's
colour predicts what follows.


### Would a 20-point stop improve it?

Yes, materially — and it confirms the diagnosis without producing an edge.
09:30 entry, 08:00 signal:

| bracket | break-even TP% | actual TP% | SL% | EOD% | E[pts] | E[R] | t | net $ | maxDD $ | PF |
|---|---|---|---|---|---|---|---|---|---|---|
| 10/40 | 21.0 | 13.2 | 76.5 | 10.3 | -1.64 | -0.164 | -1.41 | -19,150 | -22,925 | 0.80 |
| **20/40** | 34.2 | 24.8 | **55.1** | 20.1 | **+0.66** | +0.033 | +0.39 | **+7,775** | -22,600 | 1.06 |
| 20/25 | 45.6 | 44.9 | 48.3 | 6.8 | +1.38 | +0.069 | +0.97 | +16,150 | -11,212 | 1.14 |
| 20/60 | 25.6 | 12.8 | 57.7 | 29.5 | +0.24 | +0.012 | +0.12 | +2,762 | -24,125 | 1.02 |
| 20/80 | 20.5 | 6.0 | 58.1 | 35.9 | +0.76 | +0.038 | +0.37 | +8,850 | -22,512 | 1.06 |
| 30/60 | 33.9 | 13.7 | 46.2 | 40.2 | -1.46 | -0.049 | -0.68 | -17,100 | -39,650 | 0.90 |

Doubling the stop takes the stop-out rate from **76.5% to 55.1%** and the
headline from -$19,150 to +$7,775. That is exactly what the excursion data
predicted: 10 points sat inside the noise, 20 points sits at its edge. The
diagnosis was right, and the fix does what it should.

It still is not an edge, for five reasons.

**Per unit of risk it barely moves.** Expectancy goes from -0.164 R to +0.033 R.
The points improve largely because each trade now risks $1,000 instead of $500;
scaled to risk, the system is still flat.

**Target-first is still under water.** At 1:2 the break-even hit rate rises to
34.2% and the actual is 24.8%. As at every other setting, the positive total
comes from end-of-day exits (20.1% of trades), not from the target.

**It is inside the noise.** t = +0.39, bootstrap 95% CI -2.73 to +3.97 points
per trade, i.e. **-$31,900 to +$46,425** over the sample.

**The controls show mirror symmetry, not skill.** At 20/40 the signal returns
+0.66 and its inverse -0.72, while always-long (+0.04) and always-short (-0.10)
sit at zero. When the two constant rules are flat, the signal and its inverse
are forced to mirror each other, so a split of +0.66 / -0.72 is what a coin-flip
signal produces. It is not evidence that the 08:00 candle contributes anything.

**It does not survive changing the entry time.** At the 10:00 entry the same
widening reverses: 10/40 gives +0.46 and 20/40 gives -1.01. A genuine fix to a
noise-level stop should help at both entries; this helps at one and hurts at the
other.

Stability, 09:30 entry:

| bracket | 1st half | 2nd half | best month as % of total | green months |
|---|---|---|---|---|
| 10/40 | +0.01 | -3.29 | — | 3/11 |
| 20/40 | +2.09 | -0.76 | 201% (Feb 2026) | 5/11 |
| 20/25 | +1.77 | +0.99 | 55% (Jul 2026) | 7/11 |

**The one cell worth remembering is 20/25.** It is the only variant in this
entire study that is positive in both halves of the sample, green in 7 of 11
months, and not dependent on a single month, with the smallest drawdown of any
positive variant (-$11,212). It still reaches only t = +0.97, and it was picked
as the best of 56 cells, so it is not evidence — but it is the one hypothesis
here that deserves a clean test on a longer export, stated in advance rather
than selected from a sweep.


### Trading the retest of the 08:00 candle's level

`backtest_es_retest.py` — note the 08:00 candle's direction, wait for price to
leave its level, then take the same direction when price comes back and touches
it. "The level" is ambiguous, so all four readings are tested: the **breakout**
side (candle high for a bullish candle, low for a bearish one — the usual
meaning), the candle's **close**, its **mid**point, and the **far** edge.

**Entry is the open of the candle after the retest candle** (`--fill next-open`,
the default). That is how the trade is actually placed — the retest candle has
to close before you can act on it — and it also removes the intrabar problem
entirely: entry sits on a bar boundary, so **0%** of trades depend on an
assumption. The first version of this test filled a limit at the level itself,
which is optimistic and left 55% of trades assumption-dependent; those numbers
are superseded by the ones below.

A retest arrives on 85–91% of sessions. With `--require-hold`, the retest candle
must also close back on the signal's side of the level — otherwise price simply
went through it — which drops the sample to ~65% of sessions.

10/40 bracket, entry window 09:30–15:00, all resolutions identical:

| level | n | TP% | SL% | E[pts] | t | net $ | PF |
|---|---|---|---|---|---|---|---|
| breakout | 206 | 11.2 | 76.2 | -2.20 | -1.87 | -22,625 | 0.73 |
| close | 213 | 13.1 | 76.1 | -1.57 | -1.29 | -16,688 | 0.81 |
| mid | 206 | 12.6 | 77.2 | -2.04 | -1.69 | -21,012 | 0.75 |
| far | 199 | 13.6 | 73.9 | -1.00 | -0.79 | -9,950 | 0.87 |

Requiring the level to hold improves every cell without rescuing any of them:

| level | n | TP% | SL% | E[pts] | t | net $ | PF |
|---|---|---|---|---|---|---|---|
| breakout | 157 | 12.7 | 73.2 | -1.51 | -1.09 | -11,825 | 0.81 |
| close | 159 | 13.2 | 71.7 | -0.63 | -0.44 | -5,000 | 0.92 |
| mid | 161 | 11.8 | 74.5 | -1.68 | -1.24 | -13,550 | 0.79 |
| far | 154 | 12.3 | 72.7 | -1.08 | -0.76 | -8,338 | 0.86 |

Every level loses in the signal's direction, on both variants, and none of the
losses is significant. Target-first stays in the 11–13% band against the 21%
break-even — the same bracket geometry as every other test in this document.

**The controls say the same thing as everywhere else.** Held retest, entry at
the next candle's open, expectancy in points:

| level | as specified | inverted | always long | always short |
|---|---|---|---|---|
| breakout | -1.51 | **+2.28** (t +1.34) | -0.36 | +0.97 |
| close | -0.63 | +2.07 (t +1.30) | +0.88 | +0.58 |
| mid | -1.68 | +0.71 (t +0.46) | -0.04 | -0.97 |
| far | -1.08 | +0.15 (t +0.09) | -0.79 | -0.16 |

Fading the 08:00 candle on a held retest is the best-looking cell in the whole
study (+2.28 pts, PF 1.33) and it still only reaches t = +1.34 on 138 trades —
one of 16 cells tried, so nowhere near enough to act on. The consistent pattern
across every test here is that the 08:00 direction is worth slightly *less* than
nothing, and its inverse slightly more, with neither clearing noise.

**A structural stop makes it worse, and explains the family.** Sizing the stop
beyond the candle's far edge instead of a fixed 10 points — the normal way to
trade a retest — gives -0.36 R at 1:2 (t = -4.03), with all four direction rules
between -0.33 and -0.40 R. The reason is one number: **the median 08:00 candle
spans 6.8 points** (p10 3.5, p90 15.2). A stop anchored to that candle sits ~8
points from entry against a ~24-point median adverse excursion once RTH runs, so
it is inside the noise by construction.

### Fading the candle is not the answer either

`--invert` returns +0.93 pts/trade (+$10,938), which looks like the inverse
trade works. It does not survive inspection:

* t = +0.71, bootstrap 95% CI **-1.45 to +3.60** points per trade
  (-$17,012 to +$42,138 over the sample);
* target-first is 18.8%, still under the 21% break-even, so the money comes
  from end-of-day exits rather than the target;
* June 2026 alone contributes +226 points of the +219 point total — **103%**.
  Remove one month and the edge is negative.

Monthly, in points: `Oct +146, Nov +84, Dec +59, Jan +62, Feb -110, Mar -81,
Apr +31, May -69, Jun +226, Jul -179, Aug +49`.

Waiting for the 09:30 candle to close and entering at 09:45 (`--entry-mode
close`) gives -0.96 pts/trade, and widening the signal window to the whole
08:00–09:30 move gives -1.51. Neither changes the conclusion.


## Signal screen: does anything predict the session's direction?

`screen_es_signals.py` — fourteen candidates, no bracket, no stop, no target.
The signal says up or down; the session goes up or down. A signal that cannot
beat a coin flip here cannot be rescued by entry timing or trade management,
which is the trap every earlier test in this document fell into.

Outcomes: **close** (16:00 close vs the entry reference), **noon** (12:00 vs
entry), and **first20** (did price travel +20 or -20 points first — the
bracket-relevant one, decided on 221 of 235 sessions; the rest had both levels
inside one 15m bar).

**Scoring rule that matters:** a signal is never scored against a window
containing its own move. Pre-open signals are measured from the 09:30 open;
anything read off the 09:30 candle is measured from the **09:45** open — the
first price you could actually trade once that candle has closed. Scored the
sloppy way, the 09:30 candle "predicts" the day's close 64.8% of the time
(z = +4.52) and first20 78.7% (z = +8.54). Both are artifacts of the candle's
own move sitting inside the measurement window. Measured honestly they are
51.1% and 52.7%.

### Computable before 09:30

| signal | n | close hit% | z | noon hit% | z | first20 hit% | z | 1st half | 2nd half |
|---|---|---|---|---|---|---|---|---|---|
| 08:00 candle | 232 | 50.0 | +0.00 | 47.4 | -0.78 | 52.3 | +0.67 | 56.5 | 43.6 |
| 08:00 wide only | 80 | 51.2 | +0.22 | 48.8 | -0.22 | 55.7 | +1.01 | 68.8 | 39.6 |
| 08:00 + gap agree | 125 | 45.6 | -0.98 | 45.2 | -1.07 | 47.5 | -0.54 | 44.3 | 46.9 |
| 08:00–09:30 drift | 232 | 49.6 | -0.13 | 47.9 | -0.65 | 50.5 | +0.13 | 53.0 | 46.2 |
| overnight gap | 232 | 45.3 | -1.44 | 47.4 | -0.78 | 45.0 | -1.48 | 37.4 | 53.0 |
| open vs overnight mid | 233 | 52.4 | +0.72 | 53.2 | +0.98 | 51.1 | +0.34 | 53.4 | 51.3 |
| overnight momentum | 233 | 46.4 | -1.11 | 49.8 | -0.07 | 47.1 | -0.87 | 47.4 | 45.3 |
| open vs overnight mean | 233 | 51.5 | +0.46 | 53.2 | +0.98 | 49.3 | -0.20 | 51.7 | 51.3 |
| prev day direction | 232 | 51.7 | +0.53 | 48.7 | -0.39 | 51.4 | +0.40 | 52.2 | 51.3 |
| prev close in range | 232 | 54.3 | +1.31 | 53.0 | +0.92 | 50.9 | +0.27 | 49.6 | 59.0 |
| 3-day momentum | 230 | 49.1 | -0.26 | 47.0 | -0.92 | 49.5 | -0.14 | 46.9 | 51.3 |
| prior range break | 90 | 48.9 | -0.21 | 46.7 | -0.63 | 47.6 | -0.44 | 40.0 | 56.0 |

### Read off the 09:30 candle, scored from 09:45

| signal | n | close hit% | z | noon hit% | z | first20 hit% | z | 1st half | 2nd half |
|---|---|---|---|---|---|---|---|---|---|
| 09:30 candle | 235 | 51.1 | +0.33 | 54.0 | +1.24 | 52.7 | +0.81 | 53.8 | 48.3 |
| 09:30 drive | 186 | 46.2 | -1.03 | 51.1 | +0.29 | 46.9 | -0.83 | 51.1 | 41.5 |

**Nothing predicts direction.** Across 14 candidates and 3 outcomes the largest
absolute z is 1.48, and that one is *negative* (the overnight gap, contrarian).
With 42 comparisons a z of about 3 is the bar; nothing is close. Split-half
stability is poor even for the better-looking rows — the 08:00 candle runs
56.5% then 43.6%, "08:00 wide only" 68.8% then 39.6%.

### What this sample could and could not have found

235 sessions is a small screen. The smallest edge it can resolve at two standard
errors is **56.4%**:

| true hit rate | sessions needed (95%, 80% power) |
|---|---|
| 52% | ~4,900 (19 years) |
| 53% | ~2,175 (9 years) |
| 54% | ~1,223 (5 years) |
| 55% | ~782 (3 years) |
| 57% | ~398 (1.6 years) |

So this screen does **not** prove no edge exists — a true 53–54% signal would
almost certainly hide inside it. What it does prove is narrower and enough for
the decision at hand: none of these candidates shows the kind of edge that could
carry a 1:4 bracket, and a 53% directional signal would not either. The bracket
needs a 21% target-first rate against the ~14% the market gives from a
noise-level stop; that gap is not closed by a signal one or two points better
than a coin.

**If you want to keep looking**, the honest requirement is a longer export —
three to five years of ES 15m — and a candidate that is either much stronger
than 55% or conditioned on something structural (a scheduled event, a volatility
regime) rather than a candle's colour.


---

## The proxy study (run before the ES export arrived)

### The data limitation

The 08:00 ET signal candle could not be sourced in this environment:

| Source | Result |
|---|---|
| Yahoo Finance (`ES=F`) | blocked by the egress policy (403 on CONNECT) |
| Twelve Data futures | not carried — `ES` resolves to Eversource Energy |
| Twelve Data pre/post-market | Pro plan and above only |
| Twelve Data non-US listings (e.g. `CSPX` LSE, which *is* open at 08:00 ET) | Grow/Venture plan and above |
| Alpha Vantage intraday | premium endpoint on this key |
| stooq, cboe, databento, nasdaq, raw.githubusercontent | blocked by the egress policy |

So **no ES data and no pre-market data of any kind was reachable.** What was
reachable is US regular-hours equity/ETF data, which covers 09:30–16:00 only.

That splits the idea in two:

* **the entry and the bracket** (09:30 → 16:00) — fully testable, and tested below;
* **the 08:00 direction signal** — not testable here at all.

The bracket half is where the answer lives, because it fails on its own
geometry regardless of which direction the signal picks. The
`backtest_es_15m.py` engine in this repo runs the exact specified rules,
08:00 candle included, on a real ES 15m export — see *Running it on real ES data*.

## Method

**Proxy.** SPY regular-hours bars stand in for the S&P 500. SPY trades at about
1/10th of the index, so 1 SPY point ≈ 10 ES points; the 10/40 point bracket is
tested as 1.0/4.0 SPY points (`POINTS_PER_SPY` in the script). The drift in
that ratio is on the order of 1%.

**Sample.** 520 sessions, 2024-08-02 → 2026-08-28.

**Path resolution.** A bar cannot say whether the stop or the target was
touched first when both are inside it. Instead of picking an assumption,
each session is walked as an ordered list of segments and every trade is
resolved three ways — stop first (pessimistic), target first (optimistic), and
a close-based heuristic in between. Segments were refined until the assumption
stopped mattering:

| Granularity | Sessions | Trades left unresolved |
|---|---|---|
| 4h (2 segments/day) | 520 | ~9–11% |
| 1h on the days that needed it | 134 | ~3–4% |
| 15m on the one decisive hour of the days that still needed it | 38 | **0.2%** |

At 0.2% the pessimistic and optimistic columns agree to within 0.1 ES points
per trade, so the numbers below are not an artefact of the assumption.

### A data-quality finding worth keeping

Twelve Data's **daily** bars include pre/post-market prints, while its intraday
bars are regular-hours only. On 2025-03-14 the daily low is 551.49 against an
RTH low of 555.50; on 2025-04-16 the daily high is 537.89 against an RTH high of
535.11; 2024-08-21's daily low is 3.26 points below anything that traded in RTH.
The daily *open* also differs from the 09:30 open on ~15% of days.

With a 1-point (10 ES point) stop, that contamination is not cosmetic — it
manufactures stop-outs and target hits that never happened in the session. The
first run of this backtest used daily bars and reported a stop-out rate of 75.2%
against the corrected 73.3%. **`data/spy_daily_rth.csv` is kept only as the
record of that check; the analysis uses `data/spy_rth_sessions.csv`,** built
from 4h RTH bars, whose extremes were cross-checked against the 1h bars on all
134 refined days (exact match) and whose opens match the intraday 09:30 open.

## Results

520 sessions, entry at the 09:30 open, 10-point stop, 40-point target, flat at
16:00, 0.5 ES points (~$25) round-turn cost, 1 contract, ES at $50/point.
"TP%" is target-first, "SL%" is stop-first, "EOD%" exited at the close.

Heuristic resolution (pessimistic and optimistic are within 0.1 pts of these):

| direction rule | n | TP% | SL% | EOD% | E[pts] | net $ | maxDD $ | PF |
|---|---|---|---|---|---|---|---|---|
| always long | 520 | 14.2 | 73.3 | 12.5 | +0.10 | +2,543 | -16,375 | 1.01 |
| always short | 520 | 18.3 | 72.9 | 8.8 | +0.71 | +18,365 | -12,745 | 1.09 |
| overnight gap | 520 | 16.2 | 74.0 | 9.8 | +0.16 | +4,060 | -17,546 | 1.02 |
| gap inverted | 520 | 16.3 | 72.1 | 11.5 | +0.65 | +16,847 | -18,395 | 1.09 |
| previous day | 520 | 16.5 | 73.3 | 10.2 | +0.48 | +12,526 | -12,815 | 1.06 |
| **perfect foresight** | 520 | 28.7 | 52.3 | 19.0 | +9.23 | +239,865 | -5,970 | 2.68 |

"Overnight gap" (today's 09:30 open vs. yesterday's close) is the closest
observable stand-in for the 08:00 candle: the 08:00–09:30 move is a component of
the same overnight drift. "Perfect foresight" is a cheat row — it knows whether
the session closes up or down before entering — and exists to bound what *any*
direction signal could achieve.

### Is any of it distinguishable from zero?

Bootstrap 95% CI on expectancy, 4,000 resamples:

| direction rule | E[pts] | t | 95% CI (pts/trade) | 95% CI (total $, 1 contract) |
|---|---|---|---|---|
| always long | +0.10 | 0.12 | -1.47 to +1.69 | -38,121 to +44,050 |
| always short | +0.71 | 0.82 | -0.97 to +2.47 | -25,108 to +64,115 |
| overnight gap | +0.16 | 0.18 | -1.53 to +1.82 | -39,661 to +47,365 |
| previous day | +0.48 | 0.56 | -1.18 to +2.17 | -30,698 to +56,308 |
| perfect foresight | +9.23 | 9.43 | +7.35 to +11.19 | +191,123 to +290,913 |

Nothing testable clears noise. The spread between "always long" and "always
short" (0.6 points) is smaller than the standard error on either, so this sample
cannot even tell you that direction matters.

### Why the bracket is the problem

A 10-point stop from the 09:30 open is inside ordinary opening noise: it is hit
on **73%** of sessions no matter which way you face. A 40-point target is a big
directional run: it is reached first on 14–19% of sessions, against the 21%
needed to break even. Perfect foresight only lifts target-first to 28.7% — so
even a signal that is *always right about the day's direction* leaves this
bracket earning most of its money from end-of-day exits, not from the target.
A realistic signal has nowhere near that skill.

### Stop/target sensitivity

Expectancy in ES points per trade, net of cost, overnight-gap signal:

| stop \ target | 15 | 20 | 25 | 30 | 40 | 50 |
|---|---|---|---|---|---|---|
| 5 | -0.16 | 0.08 | 0.19 | 0.05 | -0.43 | -0.18 |
| 10 | -0.69 | -0.26 | 0.10 | 0.19 | **0.16** | 0.48 |
| 15 | -1.19 | -0.76 | -0.30 | -0.14 | -0.28 | -0.06 |
| 20 | -1.74 | -1.68 | -1.30 | -1.06 | -1.39 | -1.29 |
| 25 | -1.65 | -1.41 | -1.10 | -0.87 | -1.15 | -1.25 |
| 30 | -2.02 | -1.84 | -1.49 | -1.29 | -1.59 | -1.80 |

No cell is meaningfully positive; the best are a fraction of the ±1.5-point
confidence interval. Widening the stop makes it worse, because a wider stop buys
losses that the 09:30-open entry has no edge to pay for.

### By year (gap signal)

| year | n | TP% | SL% | E[pts] | net $ | PF |
|---|---|---|---|---|---|---|
| 2024 (from Aug) | 105 | 16.2 | 64.8 | +2.76 | +14,512 | 1.40 |
| 2025 | 250 | 16.8 | 75.6 | -0.25 | -3,182 | 0.97 |
| 2026 (to Aug) | 165 | 15.2 | 77.6 | -0.88 | -7,269 | 0.89 |

The one good stretch is the 105-day tail of 2024 and it does not repeat. That
shape — an early good patch followed by two flat-to-negative years — is what a
zero-edge system looks like.

## What this does and does not settle

**Settled on real ES data:** the 10/40 bracket from the 09:30 open is not
viable, the 08:00 candle is a coin flip (50.4%, z = +0.13), no stop/target pair
in a 56-cell sweep is significant, and the inverted signal's apparent profit is
one month of luck.

**Settled by the proxy study:** the bracket fails on geometry alone,
independently of the direction rule — which is why re-sizing the signal is not
a way out. The proxy also called the target-first rate (14–19% predicted,
13.2% actual) before the ES data existed.

**Still open:** whether a *different* signal, at a *different* size, on this
instrument could work. Nothing here speaks to that. What it does say is that
the 09:30 open is a poor entry reference for a tight stop: 46% of trades were
stopped inside the entry candle itself.

**Proxy caveats:** SPY is not ES. ES trades overnight, has its own opening
liquidity, and its RTH range is marginally wider in points; the ~10:1 ratio
drifts about 1%. None of that moves a 73% stop-out rate to a viable one, but the
exact figures on ES will differ by a fraction of a point.

**Costs:** 0.5 ES points ($25) round turn per contract. Cheaper fills do not
rescue the numbers; the expectancy is near zero before costs too.

## Does using cash S&P 500 data instead of futures change anything?

No — and the backtest above is already the cash-index answer. When ES turned out
to be unreachable, the whole study was run on SPY regular-hours bars, which *are*
standard S&P 500 data. Every figure above is what SPX/SPY did.

**Point sizes are interchangeable across the S&P family**, because they all track
the same index and differ only in multiplier. The futures basis (carry minus
dividends) shifts ES's *level* relative to SPX by tens of points but cancels out
of a bracket measured in points from an entry:

| instrument | 10-pt stop | 40-pt target | per point |
|---|---|---|---|
| SPX (cash index) | 10 index pts | 40 index pts | not directly tradeable |
| ES | 10 pts | 40 pts | $50 |
| MES | 10 pts | 40 pts | $5 |
| SPY | 1.0 pt | 4.0 pts | $1 per share ($100 per 100 shares) |

**Why the instrument cannot be the problem.** The bracket fails on its size
relative to how far the index travels in a session, and that ratio is identical
for SPX, SPY, ES and MES:

| | p10 | median | p90 |
|---|---|---|---|
| session range (index pts) | 31.7 | 57.8 | 115.4 |
| up excursion from the open | 4.3 | 25.0 | 63.3 |
| down excursion from the open | 4.2 | 26.3 | 76.4 |

The 10-point stop is 17% of a median session's entire range; the 40-point target
is 69% of it. On **23.7%** of sessions the index never spans 40 points at all
between its high and its low, so the target is unreachable whichever way you
face. On **50.6%** of sessions the index travels 10 points both above *and*
below the open, so the stop is hit whichever way you face. Roughly half the
sample is a loss before direction is even considered.

**What cash data cannot do is rescue the 08:00 signal — and here it is worse
than futures.** SPX does not trade before 09:30 ET, so an 08:00 candle does not
exist on the cash index; there is nothing to read. SPY has pre-market prints
from 04:00, but they are gated on this data plan, and pre-market SPY is thin
enough that a 15-minute candle's direction there is a weak reading of where the
S&P actually is. ES is the *only* instrument in the family that has a real,
liquid 08:00 candle — which is why the original specification named it.

So the choice is between:

* keeping ES for the signal (export 15m from TradingView, run `backtest_es_15m.py`);
* or, if the strategy must live on cash-hours data only, replacing the 08:00
  candle with the 09:30–09:45 opening candle and entering at 09:45 — a different
  system, not this one, and one whose bracket still has to clear the 21%
  break-even hit rate documented above.

## Running the engine yourself

`backtest_es_15m.py` implements the specification exactly — 08:00 signal candle,
09:30 entry, 10/40 bracket, flat at the close — on any 15m export. TradingView's
format works as is (timestamps may carry a UTC offset; it is stripped so the
exchange wall-clock is used):

```
python3 backtest_es_15m.py ES_15m.csv
python3 backtest_es_15m.py ES_15m.csv --stop 10 --target 40 --signal-time 08:00
python3 backtest_es_15m.py ES_15m.csv --tz-shift -1        # export stamped in CT
python3 backtest_es_15m.py ES_15m.csv --trades-csv trades.csv
```

It reports the same pessimistic/heuristic/optimistic triple, the share of bars
that contained both levels, the break-even hit rate, a per-year table and a
long-vs-short split. `--entry-mode close` waits for the 09:30 candle to close
before entering; `--invert` trades against the signal; `--dollars-per-point 5`
switches to MES.

To refresh or extend the file: TradingView → ES1! on a 15m chart with extended
hours on → ⋯ menu → Export chart data. The 234-session sample here places the
signal's agreement rate inside about ±6.5 points; a few years would halve that,
but 50.4% is close enough to a coin flip that more data is unlikely to move the
verdict.

## Files

| file | what it is |
|---|---|
| `backtest_es_15m.py` | the specified strategy, on a real ES 15m export |
| `analyse_es_signal.py` | signal-quality test and the stop/target sweep above |
| `backtest_es_retest.py` | the retest-of-the-level variant, four level definitions |
| `screen_es_signals.py` | the bracket-free signal screen above |
| `data/es1_15m_tradingview.csv` | the ES 15m export the verdict rests on |
| `data/es_trades_10_40.csv` | trade-by-trade log of the headline run |
| `backtest_open_bracket.py` | the bracket study reported above |
| `data/spy_rth_sessions.csv` | 520 RTH sessions: open, am/pm high-low, close |
| `data/spy_hourly_ambiguous.csv` | 1h bars for the 134 sessions needing finer resolution |
| `data/spy_15m_refine.csv` | 15m bars for the 38 decisive hours |
| `data/spy_daily_rth.csv` | daily bars, kept only as the record of the contamination check |
