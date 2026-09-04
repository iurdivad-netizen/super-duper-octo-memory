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
| 9:30 fair price anchor | `fairPrice`, set from the first session bar's open. Configurable to the opening candle's midpoint or close for testing. |
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
