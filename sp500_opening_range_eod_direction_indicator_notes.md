# S&P500 Opening Range vs EOD Direction — Indicator Dev Notes

**Script file:** `sp500_15min_eod_direction.pine`  
**Platform:** TradingView Pine Script v5  
**Instrument:** S&P500 — SPX, ES1! (E-mini futures), or CFD  
**Required timeframe:** 15-minute chart  

---

## What This Indicator Does

Captures the direction of the **first N minutes** of each trading session and
compares it against the **end-of-day close direction** (relative to the session
open). It tracks two windows simultaneously:

| Window | Description |
|---|---|
| **Fixed 15-min** | Always the first 15-min candle — close vs open |
| **Custom N-min** | User-defined (default 30 min) — accumulated close vs session open |

Both windows share the same **session open price** as the reference for EOD
direction, so all comparisons are self-consistent.

---

## Metrics — Direction Table (Table 1, Top Right)

Per window:

| Metric | Formula | Meaning |
|---|---|---|
| Direction Agreed | `(BullBull + BearBear) / totalDays` | Signal matched EOD regardless of direction |
| Direction Disagreed | `(BullBear + BearBull) / totalDays` | Signal did not match EOD |
| Bull → Bull | `BullBull / totalDays` | % of all days that were bull→bull |
| Bear → Bear | `BearBear / totalDays` | % of all days that were bear→bear |
| Bull → Bear | `BullBear / totalDays` | % of all days: bullish open, bearish close |
| Bear → Bull | `BearBull / totalDays` | % of all days: bearish open, bullish close |
| Of Bull days: EOD Bull | `BullBull / (BullBull + BullBear)` | **Conditional hit rate** — when the signal was bullish, how often was it right |
| Of Bear days: EOD Bear | `BearBear / (BearBear + BearBull)` | **Conditional hit rate** — when the signal was bearish, how often was it right |

> **Key insight:** "Direction Agreed" is biased by the market's own directional
> drift. The conditional hit rates (last two rows) are the more meaningful
> signal quality metric — they tell you the edge on each side independently.

---

## Metrics — Range & Structure Table (Table 2, Top Left)

Per window:

### Opening Range / Daily Range

`(window_high − window_low) / (session_high − session_low) × 100`

Tracked as an average, split three ways:
- All days
- Agree days (signal matched EOD)
- Disagree days (signal did not match)

A higher average on agree days suggests the opening move carries more momentum
on days it follows through to the close.

### HOD / LOD Made First

Tracks which session extreme — high of day (HOD) or low of day (LOD) — was
**established first**, segmented by signal direction:

| Row | Interpretation |
|---|---|
| ↑ Bull day: HOD first | Opening bullish, HOD set before LOD — opening drive held |
| ↑ Bull day: LOD first | Opening bullish, LOD set first — dipped then rallied |
| ↓ Bear day: LOD first | Opening bearish, LOD set before HOD — opening drive held |
| ↓ Bear day: HOD first | Opening bearish, HOD set first — popped then sold off |

HOD/LOD order is determined by tracking `bar_index` each time a new session
high or low is set. At EOD, `hodIdx < lodIdx` means HOD was established first.
Days where `hodIdx == lodIdx` (same bar, degenerate session) are excluded.

---

## Design Decisions & Gotchas

### Custom window snapping
On a 15-min chart, non-multiples of 15 round up to the next bar boundary.
Example: 20-min setting → the 9:45 bar starts within 20 min of open, so its
close at 10:00 is used → effective window is 30 min. Use a 5-min or 1-min
chart for exact minute precision.

### Update ordering (critical)
Three update blocks run each bar in this order:
1. `if custWinEnd` → marks the window closed (`custWinSet = true`)
2. `if inSess and not sessStart` → updates session high/low and HOD/LOD indices
3. `if inSess and not sessStart and not custWinSet` → updates custom window H/L

This ordering ensures the bar that *triggers* `custWinEnd` is excluded from the
opening range calculation (its high/low belong to the post-window session, not
the opening range).

### Direction definition
- Opening window direction: `window_close > session_open`
- EOD direction: `last_session_bar_close > session_open`
- Doji (equal): treated as bearish (not a separate bucket)

### Cyrillic character bug (fixed)
During development a Cyrillic `А` (U+0410) was introduced in the identifier
`sumRangeCА`. It is visually identical to Latin `A` but rejected by the Pine
Script compiler with "no viable alternative at character 'A'". Fixed by
renaming to `sumRangeCAg`.

---

## Input Groups

| Group | Key Inputs |
|---|---|
| General | Session string, trading days, label/highlight toggles, Table 1 position |
| Custom Window | Minutes (1–480), show/hide custom section in both tables |
| Range & HOD/LOD | Show/hide Table 2, Table 2 position |
| Table Appearance | Font size, 9× colour pickers (background, border, header, labels, values, agree, bear-bear, disagree) |

---

## Table Layout Summary

**Table 1 — Direction** (13 rows without custom, 27 with):
- Rows 0-12: Fixed 15-min section
- Rows 13-26: Custom N-min section (thick `═══` separator at row 13)

**Table 2 — Range & Structure** (11 rows without custom, 23 with):
- Rows 0-10: Fixed 15-min section
- Rows 11-22: Custom N-min section (thick separator at row 11)

---

## Session Logic

```
SESSION = "0930-1600:23456"   // configurable

sessStart = first bar of session (bar closes = 15-min candle close)
sessEnd   = first bar AFTER session (close[1] = EOD close)

f15Open  = open  at sessStart
f15Close = close at sessStart   ← full first 15-min candle captured at bar close
dayOpen  = f15Open              ← shared reference for both direction comparisons
```

For the custom window:
```
custWinEnd fires when: (bar_open_time − sessStartMs) >= customMins * 60 * 1000
custWinClose = close[1] at custWinEnd  ← last bar that started within the window
```

---

## Possible Future Extensions

- **Streak counter** — consecutive agree/disagree days
- **Day-of-week breakdown** — does Monday behave differently from Friday?
- **Gap filter** — separate metrics for gap-up vs gap-down open days
- **Volume confirmation** — correlate opening range size with volume
- **Alert** — fire when today's 15-min signal is bullish/bearish
