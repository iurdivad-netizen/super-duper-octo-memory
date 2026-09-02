# Naked POC Levels — Dev Notes

**File:** `naked_poc_levels.pine` (Pine Script v6)
**Markets:** ES / NQ (index futures); works on any symbol with volume
**Chart:** 5m
**Session:** RTH 09:30–16:00, `America/New_York`

---

## What Was Built

A **measurement indicator**, not a trading system. It builds a session volume
profile, extracts POC / VAH / VAL at each session close, and maintains a stack of
**naked POCs** — prior-session POCs that price has not yet traded back to.

The deliberate choice to build measurement before entry logic: the whole premise
("an untested POC is a magnet") is an empirical claim. Writing entry rules before
measuring the base rate is curve fitting with extra steps. The indicator produces
the four tables needed to accept or reject the premise on this instrument.

### Core concept

1. Accumulate volume into price bins during the RTH session
2. At session close, compute POC (highest-volume bin), VAH/VAL (70% value area),
   POC strength, and a double-distribution flag
3. Push the POC onto a stack of naked levels, drawn extending right
4. Remove a level when price trades through it, recording how long it survived
5. Report the survival statistics, sliced by strength and by distance at creation

---

## Design Decisions Worth Preserving

### The line is canonical, the zone is cosmetic

All naked/tested bookkeeping uses the **POC bin centre**. The zone is used only
for drawing and as an entry tolerance downstream.

If "tested" depended on the zone edge, changing the zone width would silently
rewrite the entire dataset and no two backtests would be comparable. Keeping the
line canonical means zone width is a free parameter that cannot contaminate the
statistics.

### No distance-based pruning

Tempting for chart tidiness, but pruning far levels censors exactly the records
that answer "does distance at creation predict whether a level gets tested?".
Clutter is controlled by the stored-count cap instead, and any eviction of an
unresolved record is surfaced as **censored** in the table so the reader knows
when the stats have been truncated.

### Bin size from rolling average session range

The classic chicken-and-egg problem: bins need a price range, but the range is
unknown until the session ends, and Pine is single-pass.

Solved with **absolute bin indexing** — `binIdx = floor(price / binSize)`, anchored
at zero, stored in a `map<int, float>`. `binSize` is fixed at session open from the
rolling average of the last N session ranges divided by the target bin count
(daily ATR as the bootstrap), rounded to a whole tick. No second pass needed,
and bins stay stable for the whole session.

### Dense histogram before analysis

The map holds only bins that received volume. A bin with **zero** volume is a
genuine low-volume node — often the most significant one. Analysing the sparse
map directly would step straight over them, so the map is expanded into a dense
array from min to max key before value-area expansion and valley detection.

### Double distribution instead of full HVN/LVN

Proper HVN/LVN detection needs histogram smoothing plus a prominence threshold —
two fitted parameters, on a single session's histogram that is statistically thin.
(Standard practice puts HVN/LVN on a multi-week *composite* profile, not one day.)

Instead the script detects the one case where the POC alone actively misleads:
a session with two separated volume lobes. Prefix/suffix maxima give an O(n) test
for "a deep valley with a real peak on both sides", with no peak-finding. The
valley price *is* the session's meaningful LVN, and it is plotted. Such sessions
draw their POC line dashed.

### Strength metric

`pocShare` = the POC bin's volume ÷ total session volume. A POC holding 8% of the
day's volume is a real shelf; one holding 3% is an artifact of a trending day with
no acceptance. Level colour is a gradient on this value, and the stats table slices
survival by its quartiles — so the metric is testable rather than assumed.

---

## Zone Modes

| Mode | Definition |
|---|---|
| Line only | Zero width; POC is a bare line |
| Fixed ticks | POC ± N ticks |
| ATR fraction | POC ± k × daily ATR |
| Bin width | The POC bin's own height — states the true resolution |
| **Volume expansion** (default) | Grow out from the POC bin while neighbours hold ≥ X% of POC bin volume |

Volume expansion is the only mode that carries information: the resulting **width**
is a signal. Narrow = a sharp acceptance price worth entering against. Wide = a
broad plateau, better used as a target than a trigger.

---

## Statistics Table

| Section | Answers |
|---|---|
| All resolved | N, % tested, median / p75 / p90 sessions-to-test |
| By POC strength quartile | Does strength predict survival? If not, drop the metric |
| By distance at creation (× daily ATR) | Calibrates the distance bound for the strategy |
| Live state | Live level count, nearest above/below, double-dist %, censored count |

**Censoring rule:** a level still untested after `Stats horizon` sessions (default
60) is resolved as "not tested". Every percentage in the table is therefore
"% tested within the horizon", not "% ever tested". The level stays on the chart
and can still be tested — it just cannot be counted twice.

---

## Key Inputs

| Input | Default | Notes |
|---|---|---|
| Session | 0930-1600 | RTH; ETH profiles on index futures are thin and distorted |
| Target bins per session | 50 | Bin size derived from avg session range ÷ this |
| Volume distribution | Uniform over range | Or HLC3 point — cheaper, TPO-like, noisier POC |
| Value area % | 70 | Standard |
| POC zone mode | Volume expansion | See table above |
| Max stored naked POCs | 40 | Eviction of unresolved records is reported as censored |
| Test tolerance | 0 ticks | High/low must actually reach the POC |
| Testing starts next session | true | See bug 1 below |
| Stats horizon | 60 sessions | The censoring rule |

---

## Bugs Fixed During Development

### 1. `Testing starts next session` blocked two sessions, not one

`sessCount` increments at session **end**. A level created at the close of session
N is stored with `npSess = N`, and `sessCount` remains `N` for the whole of session
N+1. The gate `npSess.get(i) < sessCount` was therefore false throughout the very
session in which the level should first have become testable — every level was
frozen for an extra full session, inflating sessions-to-test by one across the
entire dataset.

**Fix:** a separate `sessStartCnt`, incremented at session **start**, is stored on
the stack and used for both eligibility and age. A level born at the close of
session N becomes eligible at the *open* of N+1, which is what the input claims.

```pine
// broken — sessCount has not incremented yet during session N+1
bool eligible = not i_testNext or npSess.get(i) < sessCount

// fixed — the session-start clock has
bool eligible = not i_testNext or npSess.get(i) < sessStartCnt
```

### 2. Malformed eligibility expression

The same line wrapped an already-complete boolean in a redundant ternary
(`A or B or C ? B or A : false`), which is not equivalent to the intent and made
the `not inSess` term change the result depending on time of day.
Replaced with the single clause above.

### 3. `table.merge_cells` re-run on every realtime tick

The table block runs inside `if barstate.islast`, which on a live bar executes on
**every tick**. Re-merging an already-merged cell is undefined behaviour in Pine.
**Fix:** no merges anywhere — header bands are faked by giving every cell in the
row the same `bgcolor`, which renders identically and is idempotent.

### 4. Forward iteration while removing from the stack

Removing element `i` shifts every later element down one, so forward iteration
skips the level immediately after each removal — on a bar that trades through two
levels, the second was silently missed. The test loop iterates **backwards**
(`for i = size - 1 to 0`) so removals only affect indices already visited.

### 5. Descending `for` ranges

Pine iterates *downward* when the start value exceeds the end value, so
`for i = 1 to m - 2` silently runs backwards when `m == 2`, and
`for i = 0 to size - 1` runs backwards when the array is empty. Every parametric
loop is now guarded (`m >= 1`, `m > 1`, `m >= 3`, `size() > 0`) and the two
intentionally descending loops are commented as such.

### 6. Sparse map hid zero-volume bins

Value-area expansion and valley detection originally walked the sorted map keys,
which contain only bins that received volume — stepping straight over empty bins,
i.e. the strongest low-volume nodes. Fixed by densifying to a contiguous array
(capped at `MAX_DENSE_BINS = 1000`) before any analysis.

---

## Performance Notes

- Per-bar in-session cost is a handful of map operations (bar span is typically
  5–20 bins); the spread loop falls back to point-mode above `MAX_SPAN_BINS = 500`.
- Session finalisation is O(n log n) on ~50–120 bins, once per session.
- The per-bar test scan is O(stack size), capped at 40 by default. Raising the cap
  much above ~100 risks the script execution limit on deep history.
- Drawing objects stay well under the 500 limit because tested levels are deleted
  by default. Enabling **Keep tested levels** will hit the limit within about two
  years of sessions, after which Pine FIFO-deletes the oldest.

---

## Known Limitations

- **Chart-timeframe profile.** Resolution is capped by the chart timeframe (~78
  bars per RTH session on 5m). A `request.security_lower_tf` version would be
  truer but collapses backtest depth to TradingView's intrabar cap — the honest
  control group is prior-session VWAP, which should be A/B'd against this before
  the profile machinery is assumed to earn its complexity.
- **Continuous contracts.** `ES1!` volume across a roll date produces a distorted
  profile. Roll sessions are not currently detected or excluded.
- **Survivorship.** A POC stays naked *because* price trended away from it. A stack
  of untested POCs below price is partly a record of how far the market has
  trended, not a set of magnets. The distance-at-creation table exists specifically
  to quantify this before any strategy treats these levels as targets.

---

## Next Steps

1. Run on ES 5m and read the four tables before writing any entry logic.
2. If strength quartiles show no separation, delete `pocShare` and simplify.
3. Use the distance table to pick the bound for a strategy — do not guess it.
4. Likely strategy shape: nPOCs as **take-profit targets**, not entry triggers,
   with entries from a prior-POC/value-area pullback. A magnet is a good place to
   close a position and a poor reason to open one.

---

## Branch

`claude/poc-tradingview-strategy-8wuyn9`
