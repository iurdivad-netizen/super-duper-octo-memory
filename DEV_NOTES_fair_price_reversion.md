# Fair Price Reversion — "The Prop Firm Extraction Algorithm"

**File:** `fair_price_reversion_strategy.pine` (Pine Script v6)
**Source:** `Prop_Firm_Extraction_Algorithm.pdf`, 11 slides.
**Intended market:** NQ / MNQ index futures, 1m or 5m chart, RTH.

---

## Part 1 — What the deck actually says

The PDF is a discretionary playbook, not a specification. Stripped of the
marketing, it is four rules:

| Slide | Rule |
|-------|------|
| 3 | The 9:30 NY open is the day's **fair price**. Opening flow displaces price away from it; that displacement is not a genuine repricing, so the edge is the snap-back. |
| 4 | A **90-minute** operating window. 9:30–9:35 trade the displacement *away* (continuation). 9:35–11:00 trade *only* back toward the anchor. Flat at 11:00. |
| 5 | **25pt stop / 38pt target** (1:1.52), sized against a $2,000 trailing drawdown and a $3,000 profit target. If the opening candle's range exceeds 25 points, the whole day scales to 50/76 to hold the ratio. |
| 6, 8 | Entries are **A setups** (entry body larger than the previous body) or **A+ setups** (that, plus a body *close* through prior structure — wicks explicitly do not count). Layer additional entries on further structural breaks in your favour. |

Slides 7 and 9 add a continuation bailout ("do not hold a stalling
continuation trade") and a news protocol. Slides 1, 2 and 10 are the pitch.

---

## Part 2 — Mapping to code

| Deck rule | Implementation |
|-----------|----------------|
| 9:30 fair price anchor | `fairPrice`, from the first session bar's open. Also selectable: the opening candle's midpoint or close, the 8:30 news bar, the post-news consolidation midpoint, or an anchored VWAP. See Part 3b — the 8:30 and VWAP options depart from the deck and are off by default. |
| "Opening candle" | First `i_openBars` chart bars of the session. On 5m leave at 1; on 1m set 5 to reproduce the same 09:30–09:35 candle. |
| Volatility exception protocol | `openRangePts > i_volTrig` → the **whole day** switches to 50/76. Day-level, not trade-level, exactly as slide 5 describes. |
| Phase 1 continuation | Fires once, on the bar where the opening candle completes, in that candle's direction. |
| Phase 2 bias | Hard gate: shorts only when price is ≥ `i_minDisp` above the anchor, longs only when ≥ below. Inside the dead band, nothing trades. |
| A setup | `body > prevBody` (+ optional absolute floor). |
| A+ setup | A setup **and** `close` beyond the last confirmed `ta.pivot*`. A close, not a wick. |
| Layering | Up to `i_maxLayers` independent legs, each with its own bracket; a layer must be a configurable minimum distance further toward the baseline than the previous entry, and (by default) carry a fresh break of structure. |
| 11:00 hard stop | `strategy.close_all` on the bar whose close lands at or after the cutoff, plus a block on any entry that would fill at or after it. |
| $2,000 / $3,000 evaluation | Section 6 guard: trailing high-water drawdown (optionally counting unrealised P&L, as firms actually compute it), profit target, optional daily loss limit. |

### Three deliberate proxies

The deck's language is not mechanisable as written. These are the readings, all
separately tunable so you can measure how much each one is doing:

1. **"The trade stalls"** → no `i_stallPts` of progress within `i_stallBars` bars.
2. **"Massive opposing wicks"** → opposing wick > `i_wickMult` × body **and** ≥ `i_wickMinPts`.
3. **"Unexpected news"** (slide 9) → a bar whose range exceeds `i_shockMult` × ATR voids the anchor; the midpoint of the next `i_consolBars`-bar zone under `i_consolMaxPts` tall becomes the new one. **Ships disabled**, because enabling it moves the baseline that every other rule is measured against — you cannot compare a run with it on to a run with it off and call the difference edge.

The scheduled-news branch of slide 9 needs no code: "priced in, do not change the
fair price" is the default behaviour.

### Two fidelity details worth knowing

**Brackets are re-priced off the real fill.** A signal fires on bar close and
fills at the next bar's open, so a bracket computed from the signal's `close` is
not a 25-point stop — it is 25 points from a price that was never traded. Entries
place a provisional bracket (so the leg is never unprotected), then a loop over
`strategy.opentrades` re-prices every live bracket off `entry_price()` each bar.

**`openDone[1]` is a trap.** `openDone` is a `var` that survives overnight, so on
the session's first bar `openDone[1]` reads *yesterday's* value — `true` — and
`not openDone[1]` is false forever. The continuation trigger uses a plain per-bar
flag (`openJustDone`) instead. This bug would have silently disabled phase 1
entirely while everything still compiled and backtested.

---

## Part 3 — Where the deck's maths does not hold

These are not implementation choices; they are problems with the system as
specified. Each is surfaced rather than hidden.

**1. The advertised 1:1.52 is not what most trades get.**
The deck says stop at the baseline *and* take 38 points. Those conflict. If you
short 25 points above fair price and the baseline is your cap, you are risking 25
to make 25 — 1:1, not 1:1.52. The full ratio only exists when displacement ≥ TP,
i.e. ≥ 38 points. The dashboard's **"R:R here"** row shows the ratio actually on
offer at the current displacement, and turns orange when it is below nominal.

If you want the deck's stated maths, set `i_minDisp` to 38 (or your TP) and
accept far fewer trades. If you want the deck's stated *frequency* (10+ trades a
day), accept that your real average R:R is well under 1.5. You cannot have both,
and slide 5's win-rate arithmetic assumes you can.

**2. Layering and the trailing drawdown are on a collision course.**
NQ is $20/point. A 25-point stop is **$500 per contract**. Three layers at one
contract each is **$1,500 of open risk against a $2,000 trailing allowance** —
75% of the account in a single adverse excursion, before the high-water mark has
moved. Under the scaled 50-point regime, three layers is $3,000: the account is
gone before the stops are hit. Either cap layers at 1–2 in the scaled regime,
trade MNQ ($2/point), or treat `i_maxLayers` as the primary risk dial rather
than an aggression dial. The guard will halt you, but halting is the failure
mode, not the protection.

**3. Reversion is a regime bet, not a constant.**
Fading the open works on balanced days and loses on trend days, when "reversion"
means fighting the day's direction into a 25-point stop, repeatedly, ten times.
The 11:00 cutoff bounds the damage per day; it does not create an edge. Before
trusting any equity curve, split results by opening-range bucket and check
whether the profit is concentrated in low-range days. If it is, the real signal
is the range filter, not the anchor.

**4. Slides 1, 2 and 10 are not evidence.**
"$1,600,000 realized" across nine firms, and the framing of variance being
"distributed across decentralised accounts", describe a payout structure, not an
edge. Running the same negative-expectancy system on twenty accounts does not
make it positive — it buys lottery tickets with correlated numbers, since every
account trades the same signal at the same minute. That layer is portfolio
construction and is deliberately not modelled here. What *is* modelled is the
single-account constraint it exists to survive.

**5. The win rate is the whole system.**
At a true 1:1.52 with costs, breakeven is roughly 42%. At the capped ~1:1 that
most trades actually get, it is above 50%. The deck claims 62.4%. That number is
the entire thesis and it is the one thing the PDF provides no way to verify.
Measure it before sizing anything.

---

## Part 3b — The anchor question: 8:30 and VWAP

Two departures from the deck, both implemented as options, both defaulted OFF so
the deck's own configuration remains the reference run.

### The 8:30 anchor

**The claim:** on red-folder days the 8:30 release, not the 9:30 open, sets the
day's fair price.

**This directly contradicts the deck.** Slide 9 is explicit: expected news is
"already forecasted", it is "priced in", and the action is *do NOT change the
Fair Price — target the original 9:30 baseline*. Anyone enabling the 8:30 anchor
should know they are overruling the source document, not implementing it.

**The case for overruling it is strong.** The deck justifies 9:30 as "the first
major intraday reference point for a fair auction". For a contract that trades 23
hours a day that is not quite true: 9:30 is when *cash equities* open, not when
the futures auction opens. On a CPI or NFP day the genuine repricing — the
largest volume print of the session by a wide margin — happens at 8:30. By 9:30
the market has had a full hour to find the new equilibrium. Which would mean
that on precisely the highest-volatility days, the 9:30 print is the *least*
unfair price available, not the most, and the deck's premise is weakest exactly
where its parameters get scaled up.

There is also an internal-consistency argument. Slide 9's *unexpected* branch
already says to discard the old anchor, wait for a new consolidation zone, and
adopt that. The market does not know whether a shock was on the calendar. What
determines whether an anchor is still valid is whether a new equilibrium formed,
not whether the event was forecast. `ANCH_ZONE` applies that same mechanic to the
scheduled release, and reuses the existing `i_consolBars` / `i_consolMaxPts`.

**Implementation.** `ANCH_NEWS` (the 8:30 bar's open), `ANCH_ZONE` (midpoint of
the first post-8:30 consolidation zone), and `ANCH_AUTO` (8:30 on detected event
days, 9:30 otherwise). The phase clock is untouched — it still runs from the RTH
open, so only the anchor changes and runs stay comparable.

**Event detection is a proxy and will not be perfect.** There is no economic
calendar in Pine, and `request.economic()` returns data series, not release
times. The detector fires on the 8:30 bar's range relative to ATR, or its volume
relative to a rolling average — volume being the more reliable on NQ, where a CPI
minute routinely trades 20x its neighbours. It will catch CPI, NFP, PPI and
retail sales. It will also fire on an unrelated 8:30 spike, and miss a scheduled
release the market shrugs off. Check a handful of flagged days by eye.

**It needs extended-hours data.** On an RTH-only chart no 8:30 bar exists. Rather
than fail silently the anchor falls back to the 9:30 open, `anchorFellBack` goes
true, and the dashboard's Anchor row turns orange and says "8:30 n/a".

### VWAP as the fair price

**As a replacement target, this is a downgrade, and the reason is mechanical.**

A static anchor is a *fixed* level. If price runs 60 points above the 9:30 open,
the displacement reads 60 and the target sits 60 points away. **VWAP chases
price.** After thirty minutes of a rising market, VWAP has followed price up and
sits perhaps 25 points below it — so the same move now reads as 25 points of
displacement, and under `TP_NEAR` your target is capped 25 points away instead of
38. Worse, VWAP keeps rising while you hold, so the target walks toward you and
your realised reward shrinks further. This is the *same* R:R erosion documented
in Part 3, item 1, with an extra term that compounds over the holding period.

**The compensating argument is real, though.** That 60-point static reading on a
trend day is not an opportunity, it is the trap — the static anchor reports its
largest displacement precisely when reversion is least likely. VWAP refuses to
report a big number in that situation, because it has followed the repricing.
So VWAP trades away upside on balanced days to avoid catastrophic entries on
trend days. That is a genuine trade-off, not a free upgrade, which is why it is
an option to measure rather than a new default.

**The anchor point is most of the answer.** A VWAP anchored at 9:30 sits almost
exactly on price at 9:35 — it reports near-zero displacement for the first part
of the window and no reversion trade can fire at all. Anchoring at 8:30 carries
an hour of post-news volume and is the version that actually matches the "8:30
is the day's fair price" thesis. Globex-anchored VWAP is dominated by overnight
volume and sits far from post-news price on data days. `VA_AUTO` anchors at 8:30
on detected event days and 9:30 otherwise.

**The moving-target problem is handled explicitly.** `i_tpFreeze` (default on)
snapshots the fair price per leg at entry, so a leg's baseline target is fixed
even though the fair price keeps moving. The fixed-points component still comes
from the actual fill. With a static anchor this changes nothing.

### The recommendation

**Use VWAP as a filter, not as a target.** `i_vwapFilter` requires price to be on
the correct side of VWAP before a reversion entry — short only when price is
above *both* the static anchor and VWAP. This keeps the fixed target the deck's
arithmetic depends on, and spends VWAP on the thing it is genuinely good at:
telling you whether the day is oscillating or repricing. `i_vwapSlopeMax` goes
further and refuses to fade into a VWAP that is itself trending hard in the
direction of the fade. Both are off by default.

This is the direct answer to Part 3, item 3 ("reversion is a regime bet"). The
static anchor gives you the target; VWAP tells you whether the bet is on.

### The 8:30 detector's baseline

The ATR check on the 8:30 candle was there from the start, but its baseline was
wrong in a way that biased it toward false positives, so it has been rebuilt.

**The bug in the obvious approach.** A rolling `ta.atr(14)` on the chart
timeframe asks "is this bar unusual *for the last fourteen bars*". At 8:30 those
fourteen bars are 8:16-8:30 — and the minutes immediately before a scheduled
release are anomalously **quiet**, because everyone stands aside. The baseline
shrinks exactly when you are about to measure against it, so the ratio inflates,
and the test fires on ordinary mornings that merely followed a dead pre-market.

**The fix: a same-bar-of-day baseline.** The question you actually want answered
is "is this unusual *for an 8:30 window*". The detector now keeps a rolling
history of the last `i_newsBaseDays` (default 20) 8:30 windows and compares
today against their **median**. Median rather than mean so that one CPI print
cannot drag the baseline up and hide the next one. Today's reading is pushed to
the history *after* the test, so a release is never part of its own baseline.
Until five days are banked it falls back to the ATR test and the dashboard says
`[ATR (warmup)]` so you can see which test produced a flag.

**Measured over a clock window, not one bar.** Detection now runs over a fixed
`i_newsWinMin` (default 5 minutes) from 8:30, so a 1m and a 5m chart classify the
same day the same way. A CPI reaction is not finished after sixty seconds.

**Scaling is not linear.** Under the ATR fallback the range baseline is scaled by
`sqrt(windowBars)`, because volatility scales with the square root of time.
Volume is scaled linearly, because it does. Scaling both the same way would make
one of the two tests wrong by construction.

**One consequence worth knowing.** Because the verdict now arrives at 8:35 rather
than 8:30, the `VA_AUTO` VWAP anchors at the window close instead of at 8:30 —
you cannot anchor on a fact you do not have yet. That is arguably the better
anchor anyway: it measures the post-release auction and leaves the spike bar out
of the average. `VA_NEWS` still anchors at 8:30 exactly if you want the spike in.

### The opening range / trend-day filter

This is the most direct answer available to Part 3 item 3, and probably the
single most valuable addition to the system. The static anchor reports its
**largest** displacement on trend days — the days where reversion is least likely
— so the deck's own signal is loudest precisely where it is most wrong. Something
has to say "not today", and a day that breaks its opening range and holds outside
it is the textbook definition of the day you must not fade.

**Scope: reversion entries only.** The phase-1 continuation trades *with* the
opening flow; a trend-day filter has no business blocking it. It also fires at
9:35, before any sane opening range has formed.

**The range.** First `i_orMin` minutes from the RTH open, default 15. The classic
30-minute initial balance ends at 10:00 and costs a third of a 90-minute session
before the filter can say anything. Measured on bar closes, on the same clock as
the rest of the strategy, so 1m and 5m charts bracket the same minutes.

**The rule: block counter-trend, not everything.** `OR_CT` is the default and the
one to start with. After a confirmed upside break it blocks reversion **shorts**
but still allows longs — a long back up toward the anchor from below runs *with*
the day, not against it. The filter is naturally directional, which is why it
costs far fewer trades than a blanket day-kill. `OR_ALL` kills the day outright;
`OR_WIDTH` skips the break logic entirely and applies only the width cap.

**A break needs `i_orHoldBars` consecutive closes outside** (default 2). One close
outside is a probe; consecutive closes are what separate a break from a wick
through the edge.

**The classification clears by default.** If price closes back inside the range,
`orDir` resets — unless `i_orSticky` is on. This is deliberate: a failed breakout
is the *best* reversion setup on the board, and a sticky flag would throw away
the highest-quality trade of the day in the name of avoiding trend days.

**`i_orMaxPts` is a separate, blunter test** and ships disabled. Measure your
instrument's opening-range distribution before picking a number; an arbitrary cap
here is curve fitting with extra steps.

**Everything is off by default**, including this. The deck's own configuration
stays the reference run.

### What to measure

1. Baseline: deck default (9:30 open, static, no filter).
2. `ANCH_AUTO` alone. Split results by the `eventDay` flag — if the 8:30 anchor
   helps, the improvement must be concentrated in flagged days. If it is spread
   evenly, the detector is firing on noise and you are just anchoring differently.
3. **`i_orUse` alone**, mode `OR_CT`. This is the one I would test first of the
   four — it targets the failure mode the deck is most exposed to, and it is the
   cheapest in trades given the counter-trend-only rule. Then vary `i_orMin`
   (15 vs 30) and `i_orHoldBars` (1 vs 2 vs 3) one at a time.
4. `i_vwapFilter` alone, static anchor. Expect fewer trades; the question is
   whether win rate rises by more than trade count falls. Note this overlaps
   with the OR filter — both are trend-day detectors — so gains will not add up.
5. `FP_VWAP` alone. Expect the displacement distribution to compress and average
   R:R to drop. If net profit still improves, the trend-day protection is worth
   more than the reward given up — that is the whole test, and the dashboard's
   "R:R here" row is where you watch the cost.
6. Only then combine, and expect less than the sum: items 3, 4 and 5 are three
   different instruments pointed at the same problem. Five options tested
   together produce a result you cannot attribute to any of them.

---

## Part 3c — Attribution and backtest integrity

### The attribution panel

The strategy tester reports one blended equity curve. That cannot answer a
single question in Part 4 — which is why every test there previously needed its
own backtest run and manual bookkeeping.

Each entry is now tagged with six attributes and every closed trade is counted
into all six buckets, so **one run** reports trades, win rate and net P&L split by:

| Split | Answers |
|-------|---------|
| Continuation / A / A+ | Is the edge in phase 1 or phase 2, and does slide 6's "stronger win rate" for A+ actually exist? |
| Layer 1 / 2 / 3+ | Do the second and third layers earn the risk they add, or are they just leverage? |
| Standard / scaled volatility | Does the 50/76 exception protocol work, or does it just lose more per trade? |
| Normal / 8:30 event day | If the 8:30 anchor helps, the gain **must** concentrate here. Spread evenly means the detector is firing on noise. |
| Balanced / trend-day entry | The regime bet, measured directly. |
| Displacement < TP / ≥ TP | The R:R degradation from Part 3 item 1, in realised money rather than in theory. |

Read the panel before reading the equity curve. If a bucket has fewer than about
thirty trades its win rate is noise, and the deck's 62.4% claim is not
distinguishable from 50% at that sample size.

### The ambiguity counter — read this row first

A bar whose range covers **both** the stop and the target has an outcome decided
by TradingView's intrabar assumption, not by the data. With a 25-point stop and a
38-point target — 63 points of span — on 1m NQ, that is not a rare event, and it
is the single largest source of backtest optimism in a system shaped like this
one. The panel now counts those trades and shows them as a percentage.

If that number is a large fraction of the total, **nothing else on the panel
means much** until you re-run with the bar magnifier enabled or on a finer
timeframe. A strategy whose results rest on a coin-flip resolution of 30% of its
trades has not been backtested, it has been simulated.

### Two corrections made at the same time

**Risk-percent sizing was incompatible with the evaluation guard.** Sizing off
`strategy.equity` compounds: over a profitable multi-year backtest the account
grows, position size grows with it, and the fixed $2,000 trailing drawdown
becomes breachable in a single trade — so the guard's pass rate stops meaning
anything. A real evaluation account does not compound; you are paid out and it
resets. `i_sizeBase` now defaults to sizing off initial capital.

**The layer counter desynchronised on partial exits.** `layersOpen` was tracked
manually and only reset when the position went flat, so the moment one leg of a
three-leg position hit its target, the freed slot could never be reused —
`position_size` was still non-zero, nothing reset the counter, and the day was
silently capped below `i_maxLayers`. Both `layersOpen` and `posDir` are now read
from `strategy.opentrades` and `strategy.position_size` directly. They cannot
drift, and it makes `i_maxLayers` a cap on *concurrent open risk*, which is the
useful reading — `i_maxTrades` already caps total entries per day.

---

## Part 3d — Point size, and why auto-detecting it does not make this portable

### It is not the tick size

`i_psMode` auto-resolves the point/pip size from the symbol. The thing worth
being precise about is what it resolves, because the obvious answer is wrong.

`syminfo.mintick` is the smallest price increment — **0.25 on NQ**. A *point*,
the unit the deck's 25 and 38 are quoted in, is **1.0 on NQ**, four ticks.
Setting the point size to the tick size makes every stop four times tighter than
intended, and nothing errors: the script runs, the backtest produces a curve, and
the curve is of a different strategy than the one you meant to test. That is why
the input carries the warning and the dashboard always shows the resolved value
alongside the symbol's actual tick.

The mapping is a market convention, not a fact any built-in reports:

| Instrument | Point / pip | Detected by |
|---|---|---|
| NQ, ES, YM, RTY, stocks, crypto | 1.0 | default branch |
| EURUSD, GBPUSD, and most FX | 0.0001 | `syminfo.type == "forex"` |
| USDJPY and JPY pairs | 0.01 | quote currency is JPY |
| 6E and other FX futures | 0.0001 | `mintick <= 0.0001` |

The FX branch keys off the **quote currency**, not off `mintick * 10`. That
arithmetic happens to work on a 5-decimal feed and is silently wrong on a
4-decimal one. A `runtime.error` fires if the resolved point size ends up smaller
than the symbol's tick, which is incoherent by definition.

### The trap this does not fix

Auto-detecting the point size makes the *arithmetic* correct on any instrument.
It does **not** make the strategy portable, and it would be easy to assume
otherwise.

25 and 38 are NQ numbers. NQ's daily range runs a few hundred points; ES runs
roughly a quarter of that. A 25-point stop is a routine intraday wiggle on NQ and
close to half a session's range on ES — on ES the strategy would sit in its dead
band most days and take almost nothing, and what it did take would be sized
completely differently in risk terms.

So the dashboard now carries **SL / daily ATR**, and it turns orange outside a
sane band. On NQ, 25 points against a ~300-point daily ATR reads about 0.08. Run
the same settings on ES and it reads roughly 0.4. That single number tells you
immediately that the parameters did not travel, which no amount of correct point
arithmetic would have revealed.

If you want the strategy to actually run on other instruments, the fix is
ATR-relative stops and targets — `SL = k x ATR` with `k` calibrated so it
reproduces ~25 points on NQ — not a different point size. That is a change to the
risk model rather than to a unit conversion, and it is not built.

---

## Part 4 — How to test it

1. **1m NQ1! continuous, RTH only**, at least two years, `i_openBars = 5` so the
   opening candle is the deck's literal 09:30–09:35 candle.
2. Run the phases in isolation. `i_useRev = false` measures the continuation
   alone; `i_useCont = false` measures the reversion alone. The deck bundles
   them; there is no reason to assume both carry edge.
3. **A vs A+.** Run `SET_A`, then `SET_APLUS`. Slide 6 claims A+ has the
   "stronger win rate". If the A+ subset is not measurably better, the structure
   filter is costing you trades for nothing.
4. **Target modes.** `TP_FIXED` (trade through the baseline) vs `TP_BASE` (full
   reversion) vs `TP_NEAR` (the deck's combination). This is slide 10's central
   claim — that segmentation beats holding — and it is directly testable.
5. **Evaluation guard.** `HALT_DAY` re-arms the account each session and gives
   you a distribution of independent evaluation days: what fraction reach $3,000
   before losing $2,000. That pass rate is the only number that matters for the
   stated use case. `HALT_PERM` shows a single account run and stops dead at the
   first breach.
6. **Layers.** 1 vs 2 vs 3. Watch max drawdown, not net profit.

Commission defaults to $2.50/contract round turn and slippage to 2 ticks. Both
are optimistic for a 10-trade-a-day system; raise them and see what survives.

---

## Part 5 — Known limitations

- **`i_maxLayers` is capped by `pyramiding = 10`** in the `strategy()` call,
  which must be a compile-time constant. The input enforces the real limit.
- **Structure is lagged by `i_pivLen` bars** by construction — a pivot is only
  confirmed that many bars after it prints. This is deliberate: a pivot that
  confirms instantly is a repainting pivot.
- **Intrabar sequencing is not modelled.** When a bar's range covers both a
  stop and a target, TradingView's bar-magnifier assumption decides the outcome.
  With layered entries this matters more than usual.
- **One direction at a time.** All open legs share a direction; an opposite
  signal is ignored unless `i_allowRev` is on.
- **The multi-account layer is out of scope**, as above.
- **Sixty-odd inputs is a large overfitting surface.** Every one is a chance to
  fit noise. The honest procedure is to freeze everything at the deck's values,
  change exactly one thing, and require the improvement to show up in the
  attribution bucket it was supposed to affect — not merely in net profit.
- **The 8:30 features need extended-hours data.** On an RTH-only chart they fall
  back to the 9:30 anchor and say so on the dashboard, but they do not work.
- **Event detection finds volatility, not a calendar.** See Part 3b.
- **VWAP needs volume.** On a symbol with no volume series, `vwapNow` is `na`,
  the VWAP filters pass everything, and `FP_VWAP` leaves the anchor undefined so
  no trade fires. Check the dashboard's VWAP row before assuming a config ran.
