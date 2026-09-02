# Naked POC Strategy — Dev Notes

**File:** `naked_poc_strategy.pine` (Pine Script v6)
**Companion to:** `naked_poc_levels.pine` (measurement indicator)
**Markets:** ES / NQ
**Chart:** 5m
**Session:** RTH 09:30–16:00, `America/New_York`

---

## What Was Built

A strategy that uses naked POCs as **take-profit targets only**. Entries come
from a pullback into the prior session's POC zone or value area; the target is
the nearest untested nPOC in the trade's direction.

### The thesis

A magnet is a good place to **close** a position and a poor reason to **open**
one. Entering because a level sits above you is a bet on a slow, uncertain
rotation. Exiting into a level where resting orders accumulate is using the same
information at the point where it actually pays.

This also sidesteps the survivorship problem from the indicator's notes: a POC
stays naked because price trended away from it, so the stack skews toward levels
price has abandoned. Referencing only the *nearest* one, bounded by max distance,
never touches the far tail where that bias lives.

---

## Structural Limitation — read before any backtest

**Naked POCs only exist where price has already traded.** In an uptrend making
new highs there are no naked POCs above, so a long has no nPOC target and must
use the fallback ladder.

Target availability is therefore correlated with direction and regime — it is not
random missingness. A backtest that pools nPOC-target and fallback-target trades
into one equity curve cannot tell which produced the result. The dashboard splits
N, win rate and average R by target source for exactly this reason, and
`Fallback = Skip trade` isolates the pure nPOC hypothesis.

**Read the split before reading the equity curve.**

---

## Entry Playbooks

Selectable; run them separately before running Both.

### B — Trend pullback to POC (default)

Three-phase latch, mirroring the pattern already used in `initial_balance_strategy.pine`:

1. **Side** — price trades fully above or fully below the prior POC zone; the side is remembered
2. **Touch** — price reaches into the zone; the approach side is latched
3. **Reclaim** — a close back out of the zone on the approach side → entry

Direction must agree with the regime filter (unless the filter is off).

### A — Return to value

1. Session **opens outside** the prior value area
2. First close back **inside** value → entry toward the POC
3. Fires at most once per session; optionally requires the balance regime

---

## Target Engine

| Step | Rule |
|---|---|
| Candidate | Nearest live nPOC in the trade direction, at least `Min target R` away |
| Distance cap | Rejected beyond `Max target distance × daily ATR` |
| Offset | Limit placed `Target offset` ticks **before** the level |
| Fallback | Fixed R / prior session H-L / ATR extension / **Skip trade** |
| Scale out | Optional 50% at nPOC 1, remainder at nPOC 2, breakeven after TP1 |

**The offset is not cosmetic.** Resting orders pile up on a magnet, and
TradingView fills a limit on any touch with no queue position. Without an offset
the backtest books fills that would not happen. Two ticks is a starting guess,
not a measured value.

The minimum target distance is expressed in **R**, not points, so target
selection is coupled to the stop. A target inside 1R is not a trade regardless of
how attractive the level looks.

---

## Regime Filter

Built from the profile itself rather than bolted on:

- **POC migration** — where the last N session POCs have walked, in ATR units
- **Close position in value** — where the prior session closed inside its own value area
- **VA width vs its rolling average** — wide = trend day, narrow = balance day

Bias requires POC migration *and* a corresponding close position. The EMA filter
exists only as an A/B comparison.

**`Direction filter = None` is the control group.** Direction then comes from the
setup's own approach side. Always measure against None before believing a filter
helps — a filter that only cuts trade count is not an edge.

---

## Stop & Sizing

| Stop mode | Long | Short |
|---|---|---|
| Beyond value area (default) | prior VAL − buffer | prior VAH + buffer |
| Beyond POC zone | zone low − buffer | zone high + buffer |
| ATR | entry − k × ATR | entry + k × ATR |

Both risk bounds skip the trade rather than clamping it: a stop closer than
`Min risk` makes R meaningless and will be noise-stopped, and one beyond
`Max risk` is a different trade from the one the setup described. Clamping would
silently change the system; skipping leaves it honest and shows up in the
discard counter.

**Stop-side validation.** A structural stop can land on the *wrong side* of entry
— a value area price has already crossed puts prior VAL above a long entry. The
`stopOk` guard rejects these instead of submitting an inverted bracket.

---

## Instrumentation

The dashboard is the point of the file, not decoration:

| Row | Answers |
|---|---|
| Naked POC / Fallback: N, win %, avg R | Do nPOC targets outperform the fallback? |
| A / B entry counts | Which playbook is actually trading? |
| Skipped: no target / risk out of range | *Why* setups were discarded |
| Bias, POC migration, VA regime | What the filter currently sees |

Per-trade R is reconciled through a FIFO queue: one record per closed trade an
entry will produce (two when scaling out), drained as `strategy.closedtrades`
advances, and cleared whenever the position goes flat to self-heal any desync
from an EOD flatten.

---

## Execution Realism

Following the failure list in `DEV_NOTES_orb_strategy.md`:

- Real bracket orders via `strategy.exit(stop =, limit =)` — never close-based
  comparisons, so intrabar stop hits are modelled
- Per-direction state; no shared `sl` / `target` pair
- Stops and targets never wired to display toggles
- Entries on confirmed bar close, filling at the next open
  (`process_orders_on_close = false`, `calc_on_every_tick = false`)
- `commission_type = cash_per_contract` at 2.50, slippage 2 ticks

Entry is deliberately **close-confirmation, not a limit at the level**. A limit
entry at a magnet has the same optimistic-fill problem as a limit exit, and there
is no offset trick that fixes it on the entry side.

---

## Bugs Fixed During Development

### 1. Scale-out re-issued TP1 on every bar

`strategy.exit(..., qty_percent = 50)` takes a share of the **current** position.
Re-asserting the bracket each bar (the correct pattern for stop/limit) meant that
after TP1 filled, the next bar exited 50% of the *remainder*, and the next 50% of
that — the runner was bled away in halves instead of carried to TP2.

**Fix:** an `sTp1Done` flag, set when position size drops. Once set, only the
TP2 exit is re-issued.

```pine
// broken -- TP1 re-halves the runner every bar after it fills
if i_scaleOut and not na(sT2)
    strategy.exit("TP1", eid, stop = sStop, limit = sT1, qty_percent = 50)
    strategy.exit("TP2", eid, stop = sStop, limit = sT2)

// fixed
if i_scaleOut and not na(sT2) and not sTp1Done
    strategy.exit("TP1", eid, stop = sStop, limit = sT1, qty_percent = 50)
    strategy.exit("TP2", eid, stop = sStop, limit = sT2)
else if i_scaleOut and not na(sT2)
    strategy.exit("TP2", eid, stop = sStop, limit = sT2)
```

### 2. Playbook B latch never cleared on entry

`bTouched` / `bApproach` stayed armed after a trade was placed. The B signal is a
level comparison (`close > lastZoneTop`), so it remains true for as long as price
holds outside the zone — the first bar after the trade closed re-entered off the
same stale touch, with no fresh pullback. With `Max trades = 2` this reliably
produced a duplicate entry.

**Fix:** clear `bTouched`, `bApproach` and `bLastSide` in the entry block, so the
next trade requires a genuine new interaction with the zone.

### 3. Discard counters counted bars, not setups

For the same latching reason, `cntSkipTgt` / `cntSkipRisk` incremented on every
bar the signal stayed true, inflating the discard tally by roughly an order of
magnitude and making the dashboard's diagnostic row meaningless.

**Fix:** count on the rising edge of `candDir` only.

### 4. `aFired := aFired`

A no-op self-assignment left over from an attempt to stop playbook B consuming
playbook A's once-per-session budget. Replaced with `aFired := true` inside the
A branch only.

### 5. Dead code

Unused `stopMode` variable, three `nz(x, na)` calls (a no-op that reads as a
mistake), and the `i_showStats` input carried over from the indicator whose table
does not exist in this file.

---

## Calibration Warning

`Max target distance`, `Max risk`, `Min target R` and the migration threshold are
**placeholders**. They were chosen to be plausible, not because anything measured
them.

Set them from the tables in `naked_poc_levels.pine` — specifically the
distance-at-creation table, which is the whole reason that indicator refuses to
prune by distance. Fitting them here, against this equity curve, is how a
measurement tool gets turned back into a curve fit.

---

## Suggested Test Sequence

1. `Playbook = B`, `Direction filter = None`, `Fallback = Skip trade`
   → the pure nPOC-target hypothesis with no filter and no fallback
2. Turn the filter to `Profile regime` → did it improve avg R, or only cut N?
3. Enable the fallback → does the split table show nPOC targets beating it?
4. Only then try Playbook A, Both, and scale-out

Step 1 is the honest baseline. Everything after it should have to justify itself
against that number.

---

## Branch

`claude/poc-tradingview-strategy-8wuyn9`
