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
| `data/es1_15m_tradingview.csv` | the ES 15m export the verdict rests on |
| `data/es_trades_10_40.csv` | trade-by-trade log of the headline run |
| `backtest_open_bracket.py` | the bracket study reported above |
| `data/spy_rth_sessions.csv` | 520 RTH sessions: open, am/pm high-low, close |
| `data/spy_hourly_ambiguous.csv` | 1h bars for the 134 sessions needing finer resolution |
| `data/spy_15m_refine.csv` | 15m bars for the 38 decisive hours |
| `data/spy_daily_rth.csv` | daily bars, kept only as the record of the contamination check |
