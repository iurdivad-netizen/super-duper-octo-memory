# ES "08:00 candle decides, 09:30 entry, 10/40 bracket" — backtest notes

**Idea tested:** on ES 15m — the first 15-minute candle at 08:00 ET decides the
direction for the day; take that direction at the 09:30 open; 10-point stop,
40-point target.

**Verdict: the bracket does not work, and the signal is not the reason.**
A 10-point stop against a 40-point target from the 09:30 open needs the target
to be hit first on **21%** of trades to break even. Measured on 520 sessions of
S&P 500 RTH data, the target is hit first on **14–19%** of days under every
direction rule that can be tested, and only **28.7%** even with perfect
foresight of the day's direction. Every realistic rule lands within noise of
zero (t = 0.1–0.8; 95% CI spans roughly ±$40,000 per contract over two years).
Details, caveats and the significant data limitation are below.

---

## The data limitation — read this first

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

**Settled:** the 10/40 bracket from the 09:30 open is not viable on the S&P in
this sample. That conclusion does not depend on the direction rule, and it is
what kills the idea as specified.

**Not settled:** whether the 08:00 candle carries directional information. It
could not be measured here. But note what it would have to do: beat 21%
target-first when perfect knowledge of the day's direction only reaches 28.7%.
The 08:00 candle would have to be nearly as informative as knowing the close.

**Proxy caveats:** SPY is not ES. ES trades overnight, has its own opening
liquidity, and its RTH range is marginally wider in points; the ~10:1 ratio
drifts about 1%. None of that moves a 73% stop-out rate to a viable one, but the
exact figures on ES will differ by a fraction of a point.

**Costs:** 0.5 ES points ($25) round turn per contract. Cheaper fills do not
rescue the numbers; the expectancy is near zero before costs too.

## Running it on real ES data

`backtest_es_15m.py` implements the specification exactly — 08:00 signal candle,
09:30 entry, 10/40 bracket, flat at the close — on a 15m ES export. A
TradingView chart export works as is:

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

To get the file: TradingView → ES1! on a 15m chart with extended hours on →
⋯ menu → Export chart data. A few years of 15m bars is enough to place the
08:00 signal's hit rate inside about ±3%.

## Files

| file | what it is |
|---|---|
| `backtest_es_15m.py` | the specified strategy, on a real ES 15m export |
| `backtest_open_bracket.py` | the bracket study reported above |
| `data/spy_rth_sessions.csv` | 520 RTH sessions: open, am/pm high-low, close |
| `data/spy_hourly_ambiguous.csv` | 1h bars for the 134 sessions needing finer resolution |
| `data/spy_15m_refine.csv` | 15m bars for the 38 decisive hours |
| `data/spy_daily_rth.csv` | daily bars, kept only as the record of the contamination check |
