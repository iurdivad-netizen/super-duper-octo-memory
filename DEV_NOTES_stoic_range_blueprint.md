# Stoic Range Blueprint — Dev Notes

`stoic_range_blueprint.pine` — Pine Script **v6**, `indicator("Stoic Range Blueprint", overlay=true)`.

## Provenance

Built from the primary source this time: `Stoic_Market_Mechanics.pdf` ("The Stoic Range
Blueprint — A Mechanical Playbook for Simplifying Market Structure", StoicEdge.com), 17
slides, plus a 4-slide carousel of the same model. The PDF has no text layer — it is 17 page
images — so it was rendered with `pdftoppm` and read page by page.

**This supersedes `stoic_sbs_golden_pocket.pine` as "the Stoic model".** That file implements
the older publicly documented Stoic system (20/200 MA bias, break of structure, 61.8%
retracement, 2R/3R/4R). None of that appears in this deck. Both files are kept: they are two
different systems that happen to share an author.

Every rule below is quoted or directly derived from a slide. Nothing here is reconstruction.

## The model

| Slide | Rule |
|---|---|
| The Universal Truth | Markets only do Consolidation → Expansion. |
| The Translation Matrix | Order blocks, FVG, liquidity sweeps, manipulation sequences all reduce to *a range sweep* or *a range breakout*. |
| Defining the Environment | "Where price stops making progress. Wait for the pause. Look for multiple visual reactions to draw the box." |
| Anatomy of the Range | Top 20% and bottom 20% = high-probability edges. Middle 60% = "The Chopping Block / No Edge Zone". **"The edges are for execution. The middle is for targets. Never initiate a trade from the 50% line."** |
| The Only Two Setups | "If the chart does not look exactly like one of these two, there is no trade today." |
| Setup 1 Mechanics | The Trap → The Reversal → The Retest. Trigger: false break & rapid return. Internal to the box. **High probability (common).** |
| Setup 1 Targets | TP1 = 50% midpoint. TP2 = opposing boundary. "Once price reaches the midpoint, expect chop." |
| Setup 2 Mechanics | The Break → The Retest → The Extension. "Most breakouts fail. But when a retest holds outside the range, expect rapid, volatile extension." **Lower probability (rare, but explosive).** |
| Setup 2 Targets | TP1 = 1× the height of the originating range. TP2 = 2× the height. |
| Timeframe Alignment | Fractal. A 5-minute sweep can be the exact trigger for a daily range reversal. Ranges within ranges. |
| Adapting to the Churn | No forced bias. Price stuck at the 50% line is not ready. **1 to 2 trades a day max.** |
| The Rule of 'R' | 1R = entry to invalidation, predefined. If the structural stop is too wide, reduce size. "The model finds the location; only you decide the risk." |
| The Pre-Trade Contract | Range defined? Price at a boundary, not the 50%? 1R predefined? Can you pinpoint the exact invalidation price? |

## The one hard problem: drawing the box

Everything else in the model is arithmetic on `rHi` and `rLo`. The only discretionary
instruction is *"look for multiple visual reactions to draw the box"*, and mechanising it is
what determines whether this indicator is useful.

**Default: `Pivot clusters`.** A literal reading. Confirmed `ta.pivothigh` / `ta.pivotlow`
values are kept in rolling arrays. `f_cluster()` tries each of the last `i_scanPiv` pivots as
a reference level and counts how many pivots on that side sit within `i_tolAtr × ATR` of it;
the reference attracting the most touches wins, most recent breaking ties. The box is drawn
through the *extreme* of the winning cluster (highest high, lowest low) so it encompasses the
wicks, the way a human draws it.

Trying several references rather than just the newest is what stops a single sweep spike —
which by definition becomes the most recent pivot high — from redefining the boundary it just
swept. That is not a refinement; without it the detector eats its own signals.

Validity gates: `i_minTouch` per side (default 2, the literal minimum for "multiple"), height
≥ `i_minHgt × ATR`, and age ≥ `i_minSpan` bars ("wait for the pause").

**Alternative: `Channel contraction`.** `highest/lowest` over `i_ctrLen` whenever that span is
narrow relative to ATR. Simpler, always produces a box, less faithful to the slide. Offered
because some people read consolidation as volatility compression rather than as touch counts.

Expect disagreement with your own eye. Tune `Touch tolerance` first; it moves the box more
than everything else combined.

**Freezing.** The box stops updating while a break is being classified or a trade is live
(`busy`), so the levels a signal was measured from cannot shift underneath it. It expires once
price has travelled `i_expire` range heights beyond a boundary — the consolidation is spent,
and by default that is exactly Setup 2's TP2.

## The tension the model does not resolve

At the instant price breaks Range High, Setup 1 says fade and Setup 2 says follow. The deck
distinguishes them only retrospectively: a sweep is a "rapid return", a breakout is a "retest
that holds outside". So classification cannot happen at the break. One `Edge` state machine
per boundary watches and commits:

```
phase 0  inside
phase 1  wick beyond the boundary — PENDING, unclassified
phase 2  closed back inside within i_sweepMax bars      -> SWEEP     (Setup 1 arms)
phase 3  i_holdBars consecutive closes outside          -> BREAKOUT  (Setup 2 arms)
```

`i_holdBars` is the dial that splits the two. Raise it and more breaks are classified as
sweeps. A phase-1 break that does neither (returns inside, but late) resets.

**The cost is that entries are always late relative to the extreme.** That is a property of
the model, not of this implementation, and no setting removes it. Anyone expecting to be
filled at the sweep wick has misread the deck.

Wick vs close is deliberate and asymmetric: a break is *detected* on a wick (`high > rHi`),
because the trap is made by spikes — "the market manipulates highs and lows". A break is
*confirmed* on closes, because the deck requires a "sustained hold".

## Triggers

**Setup 1 (fade, internal).** Sweep of the high → short; sweep of the low → long.
- `Retest of the boundary` (default, the deck's third beat): while phase 2, a later bar
  returns to the boundary within tolerance and is rejected again — closes back inside *and*
  against the boundary.
- `Reclaim close`: fires on the reclaim bar itself. Earlier and noisier, but it catches the
  sweeps that never retest.
- Invalidation: beyond the sweep extreme (`Edge.sweepExt`), the furthest excursion outside.
- TP1 = `rMid`. TP2 = the opposing boundary.

**Setup 2 (follow, external).** Break above → long; below → short.
- Trigger: while phase 3, a bar whose low returns to the boundary (within tolerance) but which
  still **closes outside** — literally "a retest that holds outside the range".
- Invalidation: `Retest extreme` (beyond that bar's low/high, default) or `Range boundary`
  (a close back inside means the breakout failed).
- TP1 = boundary ± 1× height. TP2 = boundary ± 2× height.

Setup 1 wins if both somehow coincide, since the deck calls it the high-probability case.

## Realtime consistency

Fields of a `var` object are **not** rolled back between realtime ticks. Every phase transition
in `f_edge()` tests `close`, which fluctuates intrabar, so all transitions are gated on
`barstate.isconfirmed`. The excursion extreme (`sweepExt`) updates live, because `high`/`low`
only ever extend within a bar and a live invalidation level is more useful than a stale one.
Box adoption and signal generation are likewise confirmed-bar only. Nothing repaints.

## Discipline, implemented

Unlike the R-governors in the other Stoic system, the churn rules here *are* chart-level facts
and are implemented:

- `i_maxDay` (default 2) caps signals per day — "1 to 2 trades a day max". `timeframe.change("D")`
  resets the counter.
- `i_blockMid` rejects any entry priced inside the no-edge zone. Both setups trigger at a
  boundary by construction, so this is a guard rail against pathological boxes, not a filter.
- The Pre-Trade Contract renders live in the dashboard. The "1R sized by you" row deliberately
  shows the *distance* rather than a tick — per the deck, the model finds the location and only
  the trader decides the risk. Claiming to check that box would be dishonest.

## Scorecard

Tracked separately for Setup 1 and Setup 2, because that is the deck's central testable claim:
S1 common and high-probability, S2 rare but explosive. If your instrument does not reproduce
that asymmetry, the model is not describing your instrument.

Caveats, same as the other script: bar-resolution, **stop checked before targets** so an
ambiguous bar scores as a loss, entry at the trigger bar's close, no slippage or commission,
one open trade at a time. It is a smoke test that rejects broken settings — not a backtest.
For a real evaluation, port the trigger logic to a `backtest_*.py` harness like the others in
this repo and run out-of-sample blocks.

## Fractal context

The deck's "ranges within ranges" slide is served by an optional box for the previous completed
`i_htfTf` bar's high/low, plus a dashboard row giving price's position inside it as a
percentage. Running the full cluster detector on a higher timeframe was rejected: the detector
carries `var` state, which does not survive `request.security` correctly.

## Bugs caught in review

- **Setup 1 retest collapsed into reclaim.** The reclaim bar wicked beyond the boundary and
  closed back inside, so it satisfies the retest test by construction. Without a
  `bar_index > phaseBar` guard, `Retest of the boundary` silently behaved as `Reclaim close`
  and the two entry modes were identical.
- **Sweep spike redefining its own boundary** — addressed by design via multi-reference
  clustering (above) rather than by a patch.

## Known lint output

`tools_pinelint.py` reports 14 errors, all in its known false-positive classes: bare hex colour
literals, UDT type names and their field declarations, and `var <UDT> x = T.new()` which its
assignment regex does not match (it then misreports the later `:=` as the declaration site).
`naked_poc_levels.pine` produces the same classes. No real findings.

## Tuning order

| Input | Why it matters |
|---|---|
| `Touch tolerance (ATR)` | Dominant. Decides which reactions count as the same level, so it decides the box. |
| `Min touches per side` | 2 is the literal minimum; 3 gives far fewer, far cleaner boxes. |
| `'Sustained hold'` | Splits sweep from breakout. Higher = more sweeps, fewer breakouts. |
| `'Rapid return' window` | How quickly a false break must be reclaimed to count as a trap. |
| `Pivot left/right` | Structure recognition lag. Ranges want tighter pivots than trends. |
| `Entry trigger` (S1) | Retest = later and cleaner. Reclaim = earlier and catches non-retesting sweeps. |
