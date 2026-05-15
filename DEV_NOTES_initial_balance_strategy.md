# Initial Balance Break & Retest Strategy — Dev Notes

**File:** `initial_balance_strategy.pine`
**Markets:** SP500 / NASDAQ (SPY, QQQ, /ES, /NQ)
**Session:** NYSE/NASDAQ exchange timezone (EST)

---

## What Was Built

A Pine Script v5 TradingView strategy based on the **Initial Balance (IB)** — the price range formed between 9:30–10:30 AM EST on the first hour of the regular trading session.

### Core Concept

1. Record the IB High and IB Low during 9:30–10:30 EST
2. After 10:30, watch for a breakout above IB High or below IB Low
3. Enter either on the breakout itself or on the retest of the broken level

---

## Entry Modes

### Breakout
- Enter on the bar where `N` consecutive closes first exceed IB High (long) or IB Low (short)
- Stop loss anchored just below IB High / above IB Low

### Break & Retest (3-phase state machine)
1. **Broke** — N consecutive closes beyond the IB level
2. **Pulled away** — at least one close goes further than `ibLevel ± tolerance` (prevents firing on the breakout candle itself)
3. **Retest armed** — wick returns to touch within tolerance of the level
4. **Entry** — next close that holds back beyond the level

### Both
- Takes whichever signal comes first that day

---

## Stop Loss Modes
| Mode | Long SL | Short SL |
|---|---|---|
| IB Mid | Midpoint of the IB range | same |
| Swing High/Low | Lower of swing low vs IB Mid | Higher of swing high vs IB Mid |
| Full IB Range | IB Low | IB High |

Breakout entries always use the IB boundary (High/Low) as the SL base regardless of the SL mode setting.

---

## Take Profit Modes
- `1:2 RR` / `1:3 RR` — fixed multiples of risk from entry
- `+1R / +1.5R / +2R / +3R Ext` — IB range projected above High (long) or below Low (short)

---

## Key Inputs
| Input | Default | Notes |
|---|---|---|
| Entry Mode | Break & Retest | Breakout / Break & Retest / Both |
| Retest Tolerance | 2% of IB Range | 2% of 100pt range = 2pts |
| Breakout Confirmation Candles | 1 | Consecutive closes needed |
| Stop Loss Mode | IB Mid | |
| TP Mode | 1:2 RR | |
| Max Trades per Day | 1 | |

---

## Visual Markers on Chart
| Shape | Meaning |
|---|---|
| Green triangle up | Long breakout entry |
| Red triangle down | Short breakout entry |
| Aqua circle | Long retest entry |
| Fuchsia circle | Short retest entry |
| Small diamond | Break confirmed (no trade yet) |
| X cross | Retest armed (watching for close) |

---

## Bugs Fixed During Development

### 1. `switch` in ternary expression
Pine Script does not allow `switch` as the false-branch of a `?:` ternary.
**Fix:** compute `modeBase` from `switch` first, then apply the ternary.

```pine
// broken
base = isBreakout ? ibHigh : switch slMode ...

// fixed
modeBase = switch slMode ...
base = isBreakout ? ibHigh : modeBase
```

### 2. Original retest fired on the breakout candle itself
The old single-condition retest (`low <= ibHigh + tolerance and close >= ibHigh - tolerance`) could trigger on the very bar that confirmed the breakout if the close was only slightly above IB High.
**Fix:** added the mandatory "pull-away" phase between breakout confirmation and retest arming.

### 3. Long/short breakout counts coupled
Both `longCount` and `shortCount` were inside `if not longBroke`, so a long breakout would stop tracking the short side.
**Fix:** split into independent `if not longBroke` / `if not shortBroke` blocks.

---

## Branch
`claude/tradingview-initial-balance-strategy-d74Sh`
