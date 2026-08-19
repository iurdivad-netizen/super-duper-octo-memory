# ORB Strategy — Review & Extended SL/TP Engine

**File:** `orb_strategy.pine` (Pine Script v5)
**Origin:** review + rewrite of the original "Strategy: ORB" open-range-breakout script.

---

## Part 1 — Review of the original script

### Blocking bugs

**1. Stop loss and target were wired to a display checkbox.**
```pinescript
longStop  = showSLLines ? lowestLow - (atr * 1) : na
...
sl := longStop
target := close + ((close - longStop) * rrRatio)
```
`showSLLines` defaults to `false`, so `longStop`/`shortStop` are `na` on default settings.
That makes `sl` and `target` `na`, and every exit comparison (`close >= target`,
`close <= sl`) evaluates to `na` — i.e. never true. With `mktAlwaysOn = true`
(the default) nothing ever closes a trade: positions only flip when an opposite
signal fires. The published backtest numbers on default settings are therefore
not measuring the described system at all.

**2. One shared `sl` / `target` pair for both directions.**
Both variables are overwritten by whichever entry fired last. If a long is open
and a short signal appears, the long is now managed against the short's levels.
The exit blocks also run with no position open, and the two conditions overlap:
`close <= target` (short exit) is true for any long-side target once price is
below it.

**3. Exits were close-only, evaluated one bar late.**
`strategy.close()` on a bar-close comparison cannot model a stop being hit
intrabar. A bar that trades through the stop and closes back inside it never
registers a loss; a bar that gaps past it exits at the close, not the stop.
Real bracket orders (`strategy.exit` with `stop=`/`limit=`) are needed for the
backtest to mean anything.

**4. The volume filter compares volume to a price.**
```pinescript
vwmaAvg    = ta.vwma(close, volAvg)   // a PRICE
vwma_latest = volume                   // a VOLUME
... vwma_latest > (vwmaAvg * volThreshold)
```
`ta.vwma` returns a volume-weighted *price*, not average volume. On an index
CFD at 5,000 with 1M volume the test is always true; on a low-volume symbol
priced above its volume it is always false. The intended test is
`volume > ta.sma(volume, volAvg) * volThreshold`.

**5. `annotatePlots` positions every label with `hidePDHCL`.**
```pinescript
label.set_xy(l1, bar_index, hidePDHCL ? na : val)
```
The ORB, SL and trend labels all read the *PDHCL* toggle, so hiding the previous
day levels blanks unrelated labels. The `hide` argument passed in only gates
label creation on the first bar.

### Correctness / design issues

**6. `period` ("TimeRange") is a dead input.** The range is defined solely by
`sessionInput`; changing 15 to 30 does nothing.

**7. Breakouts can fire while the range is still forming.** Nothing requires the
ORB window to be finished. `ta.crossover(close, dh)` in particular can trigger
pre-market or inside the range.

**8. End-of-day handling is inverted.** `strategy.close_all()` sits in the
`else if (not mktAlwaysOn)` branch, which is unreachable whenever `mktAlwaysOn`
is true (the default), and when reached it runs on every bar after the cutoff.
`hour(time('1'), ...)` also returns `na` outside the 1-minute session on some
symbols; the built-in `hour`/`minute` are already exchange-time.

**9. No per-day trade cap and no flat-only gate.** A choppy day can re-enter
repeatedly, and a signal against an open position silently reverses it.

**10. Fixed lot sizing.** Position size is unrelated to the stop distance, so a
wide-stop trade risks several times more than a tight-stop one and the equity
curve mostly measures volatility, not edge.

**11. No commission or slippage** in the `strategy()` header — breakout systems
on intraday data are highly sensitive to both.

**12. Minor.** `is_newbar()` is dead code; `math.floor(sl)` in the alert breaks
on sub-1.0 instruments (FX) and on `na`; the summary table is rebuilt inside a
function on every session end.

---

## Part 2 — What `orb_strategy.pine` adds

### Stop-loss modes (`Stop Loss > Stop Loss Mode`)

| Mode | Long stop | Notes |
|---|---|---|
| Swing High/Low +/- ATR | `lowest(low, N) - ATR x mult` | Original behaviour, now with configurable lookback and multiplier |
| ATR from Entry | `entry - ATR x mult` | Pure volatility stop, independent of structure |
| ORB Opposite Side | `ORB low` | Classic ORB invalidation: the break is wrong if price re-enters the range |
| ORB Midpoint | `(ORB high + ORB low) / 2` | Half the range risk; the most common intraday compromise |
| Percent of Entry | `entry x (1 - %)` | Fixed fractional risk, good for crypto/FX |
| Fixed Points | `entry - N ticks` | Futures/options desks that think in points |
| Percent of ORB Range | `entry - range x %` | Risk auto-scales with how volatile the open was |
| Previous Bar Extreme | `low of the signal bar` | Tightest structural stop, highest stop-out rate |
| VWAP | session VWAP | "Long is only valid above VWAP" |

Supporting inputs: **ATR period / multiplier**, **swing lookback**, **extra SL
buffer in ticks** (survives stop hunts and spread), and **skip trade if SL wider
than X x ATR** — a filter that drops the trades where the chosen stop is
nonsense for current volatility.

Every mode is validated: if the selected level is `na` or lands on the wrong
side of the entry (e.g. VWAP above price on a long), it falls back to the ATR
stop instead of producing a zero-risk trade.

### Take-profit modes (`Take Profit > Take Profit Mode`)

| Mode | Long target | Notes |
|---|---|---|
| Risk:Reward | `entry + risk x ratio` | Original behaviour |
| ORB Range Multiple | `ORB high + range x mult` | Measured move — the classic ORB target |
| ATR Multiple | `entry + ATR x mult` | Volatility target, decoupled from stop width |
| Percent of Entry | `entry x (1 + %)` | |
| Fixed Points | `entry + N ticks` | |
| Prev Day High/Low | `PDH` | Trades into the obvious liquidity pocket |
| VWAP | session VWAP | Mean-reversion exit |
| None | — | No fixed target; exit via trailing stop / time stop / EOD |

Level-based targets (PDH/PDL, VWAP) that are already behind price fall back to
the R:R target automatically.

### Trade management

- **Partial take-profit** — scale out X% at an R multiple, with optional
  automatic move to break-even on the remainder.
- **Break-even** — trigger at any R multiple, with a tick offset so the stop can
  lock in a small profit rather than a flat scratch.
- **Trailing stops** — four modes: ATR (Chandelier, from the running extreme),
  percent of the running extreme, swing structure (last N-bar low/high), and
  "step by R" (ratchet the stop one risk unit at a time). Trails only ever
  ratchet in the trade's favour and are never pushed through the current price.
  A `Start trailing after N R` gate keeps the trail off until the trade works.
- **Time stop** — close after N bars if the move has not resolved.
- **End-of-day flat** — now actually reachable, and only fires once per position.

### Other fixes carried into the rewrite

- Real bracket orders via `strategy.exit`, armed on the signal bar and
  re-anchored to the actual fill price on the next bar.
- Volume filter uses `ta.sma(volume, N)`; symbols without volume pass the filter
  instead of silently blocking all trades.
- `Range Minutes` is now functional (opt-in): the range starts at the session
  start and lasts N minutes, so `period` no longer contradicts the session string.
- Risk-based position sizing (`Risk % of equity / stop distance`), optional.
- Per-day trade cap, direction filter, optional EMA trend filter, and entries
  only while flat.
- Labels/plots decoupled from the exit logic; summary table drawn once on the
  last bar and extended with live position, SL/TP and trade count.

---

## Part 3 — Behaviour changes to be aware of

These are deliberate and can be reverted from the inputs:

| Change | Revert with |
|---|---|
| Trades only after the opening range is complete | `Only trade after the range is complete` = off |
| No reversals — entries require a flat position | (not revertible; use max trades/day) |
| Max 2 trades per day | `Max Trades per Day` |
| SL/TP plotting no longer affects the stop calculation | — |
| Volume filter now uses average volume | — |

---

## Part 4 — Suggested starting presets

**Index futures / SPY-QQQ, 5m**
SL `ORB Midpoint`, buffer 2 ticks · TP `ORB Range Multiple` 1.0 · partial 50% at 1R,
break-even after partial · trail `ATR (Chandelier)` 2.0 starting at 1R · max 2 trades/day.

**Crypto, 15m, 24h market**
SL `ATR from Entry` 1.5 · TP `None` · trail `Percent of Extreme` 1.5% from 0.5R ·
`Market never closes` on · risk 1% of equity.

**FX, 5m**
SL `Percent of ORB Range` 60% · TP `Risk:Reward` 2.0 · break-even at 1R ·
time stop 40 bars.

Always set commission and slippage in the `strategy()` header to your broker's
real numbers before reading any backtest — they are 0 by default.
