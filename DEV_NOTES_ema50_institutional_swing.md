# Institutional 50 EMA Mechanical Swing

**File:** `ema50_institutional_swing_strategy.pine` (Pine Script v6)
**Intended chart timeframe:** 4h (manual's "sweet spot"), 1h floor
**Intended markets:** index CFDs, FX majors/minors, gold, liquid commodities

---

## Lead with the uncomfortable part

The source manual's headline statistics do not survive contact with arithmetic.

**1. Seven trades cannot yield a 65–67% win rate.** With n = 7 the only attainable
win rates are 0, 14.3, 28.6, 42.9, 57.1, 71.4, 85.7 and 100%. "65% to 67%" is not
in that set. The trade-frequency claim and the win-rate claim, as written, describe
different samples. The charitable reading — and the one worth confirming before
anything else — is ~7 trades *per market* across the 6–7 markets the manual tells
you to run, i.e. n ≈ 45–50. That would be a real sample. The document never says so.

**2. The benchmark to beat is 33.3%, and it is not obvious the system beats it.**
A +2R / −1R bracket on a driftless random walk with zero costs fills the target
1/(1+2) = 33.3% of the time. That is the null hypothesis, not a strawman. So:

| Win rate | Expectancy per trade |
|---------:|---------------------:|
| 33.3%    | 0.00R (break-even)   |
| 35%      | +0.05R               |
| 40%      | +0.20R               |
| 50%      | +0.50R               |
| 65%      | +0.95R               |

A genuine 65% at 2R is +0.95R per trade. That is not a good system; it is an
extraordinary one, and extraordinary claims need proportionate evidence.

**3. At n = 7 there is no evidence either way.**

| Observed | Rate | 95% Wilson CI | P(this good or better \| true WR = 33.3%) |
|---------:|-----:|--------------:|------------------------------------------:|
| 4 / 7    | 57.1% | 25.0% – 84.2% | 17.3% |
| 5 / 7    | 71.4% | 35.9% – 91.8% | 4.5%  |

A 4/7 result happens by pure chance one time in six. Reaching a confidence interval
narrow enough to be worth acting on takes n in the dozens, which is precisely why
the manual's own advice to run 6–7 non-correlated markets is the most useful
sentence in it — not because it "optimises capital efficiency", but because it is
the only way this setup accumulates a sample inside a human lifetime.

**This is why the script's dashboard reports the Wilson interval and the break-even
win rate side by side, and flags `CI STRADDLES IT`.** If the interval still covers
33.3%, the backtest has said nothing, however good the equity curve looks. That
warning is the most important number on the chart.

### Two further premises worth naming

* **The manual's epistemology is inconsistent.** It dismisses ~99% of indicators as
  useless because "they merely report what occurred in the past", then builds the
  entire system on a 50 EMA and an ATR-derived stop — both of which are pure
  functions of past prices. That does not make the rules bad. It does mean the
  institutional-order-flow narrative is decoration, not evidence, and should carry
  no weight in your decision to trade it.
* **"Move to break-even at 1R" is not a law.** The manual calls it non-negotiable.
  It is a trade-off, and an empirically two-sided one: it converts some full losses
  into scratches *and* some eventual 2R winners into scratches. On an idealised
  driftless walk it is roughly neutral-to-favourable; in real bars, with spread and
  noise around the entry price, a scratch costs commission and the premature
  stop-out is a real cost. It is the single highest-leverage switch in the script
  (`i_useBe`). Run your period with it off before accepting it.

---

## The setup, as specified, and where it lives in the code

| Step | Rule | Code |
|------|------|------|
| 1 | A candle **body** closes entirely across the 50 EMA | `bodyAbove` / `bodyBelow` → `rawCrossUp` / `rawCrossDn` |
| 2 | Discard spikes and huge wicks | `spikeUp` / `spikeDn` → `crossUp` / `crossDn` |
| 3 | Two consecutive opposite-colour bodies | `retraceN` |
| 4 | Pin bars do not count; wait for a visible body | `isPin` |
| 5 | Buy/sell stop one pip beyond the previous extreme | `trigPx`, `strategy.entry(stop=)` |
| 6 | A close back through the 50 EMA cancels everything | `emaKillLong` / `emaKillShort` |
| 7 | Stop = the Chandelier level at entry | `initStop` |
| 8 | Target = 2R | `tpLevel` |
| 9 | Stop to break-even at 1R | `i_useBe`, `beDone` |
| 10 | Chandelier trails thereafter | `i_useTrail` |

Shorts are the exact mirror throughout.

---

## Everything the manual leaves undefined

These are inputs, not hidden constants, and each is marked **MINE** in its tooltip.
They are the places where "mechanical" quietly becomes discretionary, and they are
where a backtest is most easily fitted to a conclusion you already hold.

| Undefined in the manual | Input | Default | Why this default |
|---|---|---|---|
| What is a "spike" | `i_spikeMult`, `i_spikeLookback` | range > 2.0 × avg of prior 8 bars | Manual says "5–10 bars"; 8 is the midpoint. 2.0× is a starting point, not a finding — sweep 1.5–3.0 |
| What is a "huge wick" | `i_wickMax`, `i_wickSide` | wick > 50% of range, breakout side only | For a long, the *upper* wick is the exhaustion tell |
| What is a "pin bar" | `i_pinMax` | body < 25% of range | Such a bar neither counts toward the two nor resets the count — the setup waits, as instructed |
| Which "previous high" | `i_trigRef` | last retracement bar | Tightest and most common reading; two alternatives provided |
| How long an order lives | `i_maxRetraceBars` | 0 = forever | Manual-faithful: only the EMA close cancels it. Non-zero stops a stale setup firing weeks later |
| Does a green bar reset the count | `i_resetOnSame` | yes | "Two **consecutive**" bars. Off is a materially looser system |
| Chandelier period/multiplier | see below | — | Unspecified in the manual |

### The Chandelier problem

The manual specifies "Chandelier Stop — Pip Charlie 1". pipCharlie's TradingView
"Chandelier Stop" is open source and is described as *a modified Chande & Kroll
stop* — which is **not** the same formula as LeBeau's Chandelier Exit, the other
indicator that goes by this name. The two produce different stop levels, therefore
different R, therefore a different 2R target, therefore a different system.

TradingView is blocked by this environment's egress proxy, so the exact source
could not be read and is **not verified here**. Both engines are implemented and
selectable via `i_chEngine`:

* **Chande & Kroll** (default, p=10 / x=1 / q=9): preliminary stops at
  `highest(high,p) − x·ATR(p)` and `lowest(low,p) + x·ATR(p)`, then smoothed by
  `lowest(·,q)` / `highest(·,q)`.
* **LeBeau Chandelier Exit** (22 / 3.0): `highest(high,22) − 3·ATR(22)`, with the
  usual one-way ratchet.

**Open the pipCharlie indicator on your own chart, read its inputs, and match them
here before trusting any number this script produces.** Until you do, the stop
distance — and so every R multiple in the report — is a guess.

---

## Implementation decisions that affect the result

### The stop is read from the bar *before* the fill

A stop-entry order fills intrabar. Reading the Chandelier from the completed fill
bar uses an extreme that the fill itself helped create and that was not knowable
when the order filled. `i_stopRefBar` defaults to **Bar before the fill** for that
reason. The "Fill bar" option exists so you can measure how much that flattery is
worth on your data; it is not a live-tradeable configuration.

### R is measured from the actual fill, not the signal

Orders are created on a confirmed close and fill later
(`process_orders_on_close = false`). `entryPx` is `strategy.position_avg_price`,
so `rValue` reflects what the trade actually risked, including trigger slippage.

### The trail runs from entry, not from 1R

This is what produces the manual's "half-percent loss" outcomes. The Chandelier can
climb above the initial stop *before* the trade ever reaches 1R, so a reversal costs
a fraction of R rather than a full R. The target stays anchored to the **initial**
R, so the printed R:R does not drift as the stop tightens.

### Three exits are live at once

Fixed 2R limit, Chandelier trail, break-even jump. They are genuinely different
systems fighting over the same trade, and they are the reason the manual's "win
rate" is ambiguous: a Chandelier scratch is not a 2R win and not a 1R loss. The
dashboard therefore reports **win / scratch / loss** separately, **how many trades
reached the full target**, and **expectancy in R** — because a 65% "win rate" made
mostly of +0.2R scratches is not the +0.95R/trade system the manual advertises.

### Guards that skip a trade rather than take a bad one

* `badFill` — a gap straight through the trigger can land the fill on the wrong side
  of its own stop. The position is flattened rather than running an inverted bracket.
* `i_minStopTicks` — a Chandelier stop sitting almost on the entry is a coin flip
  against the spread.
* `i_maxStopAtr` — a very wide stop makes 2R a price the market may never reach.

### Position sizing caveat

Risk-% sizing derives quantity from the *estimated* stop distance at order
placement. A stop entry that gaps through its trigger risks more than the intended
percentage. Check `syminfo.pointvalue` against your broker's contract before
believing the currency column.

---

## Before trusting a backtest

1. **Set commission and slippage in Properties.** They default to zero so the raw
   signal is visible first. A curve built at zero cost is not a result — and on a
   ~7-trade-per-5-months system, costs land on a very thin sample.
2. **Watch the CI, not the equity curve.** If `CI STRADDLES IT` is showing, stop.
3. **Aggregate across markets.** One instrument will not produce a decidable sample
   this decade. Run the 6–7 non-correlated markets and pool the trade lists.
4. **Check the trade count before and after each filter.** The spike filter and the
   two-bar rule each cut the sample hard. Two filters that both look sensible can
   leave nothing behind worth measuring.
5. **Turn `i_useBe` off and on over the same period.** If the answer changes the
   verdict, the verdict was never about the entry.
6. **Sweep `i_spikeMult`.** If the result is only good at 2.0 and falls apart at 1.8
   and 2.5, that is a fitted parameter, not an edge.

---

## Known limitations

* **Intrabar order of stop vs target is unknown.** When one bar spans both levels the
  broker emulator resolves it by its own assumption, not by tick data. Bar Magnifier
  (paid plans) is the fix if that matters for your sample — and on a 4h chart with a
  2R bracket, it matters more than usual.
* **Net position only.** A short signal appearing while a long is open is skipped,
  not stacked.
* **The EMA is read from the chart timeframe.** A different chart timeframe is a
  different system, not the same system at higher resolution. The dashboard warns
  below the 1h floor; `i_blockBelowTf` makes it binding.
* **A pending order with `i_maxRetraceBars = 0` can outlive its premise** for a long
  time if price drifts without closing back through the EMA.
* **The spike filter measures the breakout candle only.** The manual's "wait for the
  market to calm" is not otherwise implemented — there is no cooling-off period
  after a rejected spike.
