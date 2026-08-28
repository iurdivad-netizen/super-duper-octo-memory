# XAUUSD — EMA 20/50 Crossover + Retest

**File:** `xau_ema_crossover_retest_strategy.pine` (Pine Script v6)
**Instrument:** XAUUSD · **Chart timeframe:** 15 minutes

---

## The setup, as specified

| Step | Rule | Where it lives in the code |
|------|------|----------------------------|
| 1 | 20 EMA crosses above the 50 EMA | `crossUp` → arms the setup (`lArmed`) |
| 2 | Wait for price to come back and touch the 20 EMA | `lTouch` |
| 3 | Enter on the retest | `longTrigger` → `strategy.entry` |
| 4 | Stop loss at the 50 EMA | `pendStop = emaSlow - iSlBuf` |
| 5 | Take profit = 2.5 × the stop distance | `actTp = actEntry + 2.5 * actR` |
| + | The opposite 20/50 cross closes the trade | `crossExitLong` / `crossExitShort` |
| + | The stop moves to break-even at 1R | `beTrigL` / `beTrigS` |
| + | 1h trend must agree | `htfLongOk` / `htfShortOk` |
| + | Trade retest number N, not necessarily the first | `lNumOk` / `sNumOk` |

Shorts are the exact mirror and can be turned off with **Trade direction → Long only**.

---

## Design decisions worth knowing about

### A cross only arms; it never buys

The cross bar is not an entry. It sets `lArmed = true` and records the bar index. The
trade is taken later, on the retest. The armed setup is dropped when any of these happen
first:

* the EMAs cross back (`crossDn` clears `lArmed`),
* a bar **closes** through the 50 EMA (`Drop the setup if a bar closes through the 50 EMA`,
  on by default) — the premise for a 50 EMA stop is gone,
* the retest has not happened within N bars (`Retest must happen within N bars`,
  default 40 = ten hours on 15m).

### The pull-away requirement is not optional decoration

Right after a cross, price is sitting on both EMAs, so the bar after the cross is
trivially "touching the 20 EMA". Without a filter, every cross fires immediately and the
retest rule does nothing.

Two guards handle it:

* **Minimum bars between the cross and the retest** (default 1) — the cross bar itself can
  never be its own retest.
* **Required pull-away (× ATR)** (default 0.30) — price must first travel 0.3 ATR away
  from the 20 EMA. `lHigh` tracks the highest high since the cross for exactly this.

Set the ATR multiplier to 0 to disable the requirement and take the first touch.

### "Touch" means a wick touch, with a confirmation close by default

`lTouch` is `low <= emaFast + tolerance` — the bar has to actually reach the 20 EMA.
The default entry mode then adds `close > emaFast`: the bar must close back **above** the
20 EMA. That is what separates a retest from a breakdown that happens to pass through the
level.

Three entry modes are available:

| Mode | Behaviour | Trade-off |
|------|-----------|-----------|
| **Close back above / below the 20 EMA** (default) | Signal on the close of the touching bar, fill at the next bar's open | Best signal quality, worst fill |
| **Touch of the 20 EMA** | Signal the moment a bar wicks into the 20 EMA | Earlier, catches more, no rejection evidence |
| **Resting limit order at the 20 EMA** | A limit order is parked at the 20 EMA while the setup is armed | Best fill, but it also fills on the retests that keep going |

In limit mode the order is re-placed or cancelled on every bar, so a parked order never
outlives the setup that justified it.

### The stop and target come from the actual fill, not the signal bar

Orders are created on a confirmed bar close and fill at the next bar's open
(`process_orders_on_close = false`). The signal bar's close is *not* the entry price, so
the risk unit is measured after the fill:

```pinescript
actEntry := strategy.position_avg_price
actR     := math.abs(actEntry - actStop)
actTp    := actEntry + iRR * actR        // 2.5R by default
```

Both levels are then live bracket orders (`strategy.exit` with `stop=` and `limit=`), not
close-only comparisons. A bar that trades through the stop and closes back inside it is a
loss here, exactly as it would be in the market.

The stop level itself is frozen at the 50 EMA reading from the signal bar. **Trail the
stop with the 50 EMA** (off by default, since it is not what was asked for) makes it
follow the 50 EMA in the trade's favour, never backwards, and never past the current price.

### Break-even at 1R

Once price has travelled one stop distance in favour, the stop jumps from the 50 EMA to the
entry price. On by default, trigger and offset both configurable.

```pinescript
beReady = iUseBe and inTrade and not beDone and not justIn and nz(actR, 0) > 0
beTrigL = beReady and strategy.position_size > 0 and high >= actEntry + iBeAt * actR
...
actStop := math.max(nz(actStop, actEntry), actEntry + iBeOffset)
```

Four details behind those three lines:

* **The bar's extreme, not its close.** `high >= entry + 1R` fires on the bar that actually
  traded 1R. Waiting for a close above 1R would move the stop later than the trade earned it.
* **Never on the fill bar.** In the resting-limit entry mode the bar's high can predate the
  fill, which would trigger break-even on a move the trade never captured. `not justIn`
  costs one bar of protection and removes a class of fake results from the backtest.
* **`math.max`, so it only ever moves in the trade's favour.** Break-even and the optional
  50 EMA trail both write to `actStop` and neither can pull it back.
* **`beDone` latches per trade** and is reset on every fill, so a trade that comes back
  through the entry does not re-trigger anything.

**Break-even offset** shifts the level off the exact entry. Positive locks in a little and
covers costs — 0.3-0.5 on XAUUSD roughly covers a typical spread, and a stop sitting exactly
at the entry is a scratch *minus* commission. Negative leaves a cushion short of the entry
so that a wick back through it does not scratch the trade.

The trade-off is the point of testing it: at a 1R trigger with a 2.5R target, a real share
of the trades that would have reached the target get scratched at break-even instead. It
reliably improves the loss column and just as reliably costs some of the win column — which
side wins is an empirical question on your data, not a general truth. Raising the trigger to
1.5R or 2R is the usual middle ground.

### The opposite 20/50 cross as an exit

For an open long, the 20 EMA crossing back under the 50 EMA is the signal that got you in
going away. **Take profit / exit** decides what that is worth:

| Mode | Behaviour |
|------|-----------|
| **R multiple or the opposite cross, whichever comes first** (default) | The 2.5R limit is live *and* a cross closes the trade early |
| **Fixed R multiple only** | The original behaviour — 2.5R or the stop, the cross is ignored |
| **Opposite 20/50 cross only** | No limit order at all; the trade runs until the cross or the stop |

Cross-only lets a trend run well past 2.5R, at the cost of giving open profit back when it
turns — the cross is a lagging signal by construction. Whichever-comes-first caps the
upside at 2.5R but stops a stalled trade from riding all the way back to the 50 EMA stop.
They are genuinely different systems; backtest both before picking.

Two implementation points that matter:

* **The bracket stays live while the close is in flight.** `strategy.close()` is a market
  order that fills at the *next* bar's open, so the stop has to cover the bar in between.
  The `strategy.exit` call is made first and unconditionally; only then is the close sent.
* **In cross-only mode the limit is `na`, not a far-away price.** `limit = tpLevel` with
  `tpLevel = na` places no limit order at all, rather than a target that silently caps the
  trade.

**Only close on the cross when the trade is in profit** (off by default) turns the cross
into a strict take-profit: a cross while the trade is underwater is ignored and the 50 EMA
stop is left to do its job. Off, the cross closes the trade either way — which is the more
defensible reading, since the premise for the trade is gone regardless of the P&L.

Note this exit fires on the same bar that arms the setup in the opposite direction, which
is intended: the long is closed at the next open, and the short then waits for its own
retest before it can enter.

### Guards that skip a trade rather than take a bad one

* **Minimum stop distance** (default 0.5 points) — when price is sitting on the 50 EMA the
  stop is a coin flip against the spread.
* **Maximum stop distance** (default 0 = off) — when the EMAs are stretched apart, a 50 EMA
  stop on gold can be 15+ dollars wide; 2.5R of that is a target price may never see.
* **Invalid fill** — if the fill lands on the wrong side of its own stop (a gap through the
  50 EMA), the position is flattened instead of running an inverted bracket.

### Higher-timeframe (1h) confluence

The 15m retest is only taken when the 1h agrees with it. One `request.security` call
fetches the 1h fast EMA, slow EMA and close — plus their previous values — with
`barmerge.gaps_off, barmerge.lookahead_off`, so no future data reaches the backtest.

Four rules, longs shown (shorts are the mirror):

| Rule | Passes when |
|------|-------------|
| **1h 20 EMA above the 1h 50 EMA** (default) | `eFast > eSlow` |
| **1h price above the 1h 50 EMA** | `eClose > eSlow` |
| **Both of the above** | both |
| **Both, and the 1h 50 EMA sloping the right way** | both, plus `eSlow > eSlow[1]` |

**Use the last CLOSED 1h bar** (on by default) is the setting that decides whether the
filter is honest. With it ON the script reads the previous, completed 1h bar in history and
in real time alike, so a 15m signal means the same thing live as it does in the backtest.
With it OFF, live trading uses the forming 1h bar while history can only ever show closed
ones — the two diverge, and the backtest stops describing what you will actually get.

The filter gates entries, not arming. A cross can arm the setup while the 1h is still
undecided and become tradeable by the time the retest arrives — which is often exactly how
a good pullback develops.

The confluence timeframe is an input, so "1h" is only the default; the dashboard warns if
it is set below the chart timeframe.

### Enter on retest number N

`Enter on retest number N` skips the first N-1 touches of the 20 EMA after a cross. The
first pullback into a fresh cross is the one most likely to just keep going; N = 2 or 3
trades a trend that has already held the 20 EMA at least once.

Counting distinct retests is the part that needs care. A cluster of bars sitting on the
20 EMA is **one** retest, not six, so a touch is only counted once price has pulled away
again:

```pinescript
if lTouch
    lCount := lCount + 1
    lRef   := high      // the pull-away measurement restarts here
```

`lRef` is the highest high since the cross *or since the last counted retest*, and the
same `Required pull-away (× ATR)` threshold that gates the first touch also gates every
subsequent one. Setting the pull-away multiplier to 0 removes that separation, and then
every touching bar counts as its own retest — worth knowing before combining `0` with a
high N.

`That retest only` restricts entries to exactly retest N; with it off, retest N and every
retest after it qualify. In the resting-limit entry mode the fill *is* the touch, so the
order is only parked when a fill would be retest number N.

Turn on **Number the retests on the chart** while tuning N — it prints 1, 2, 3 … on each
touch so you can see what the count is actually doing on your data.

### One trade per cross

By default a filled retest spends the setup: the script then waits for the next 20/50
cross. **Allow a new trade on every later retest of the same cross** re-arms it, so each
subsequent touch of the 20 EMA while the EMAs stay crossed is tradeable again.

---

## Position sizing

* **Fixed quantity** (default 1) — raw signal quality, no compounding.
* **Risk % of equity** — quantity is derived from the real stop distance
  (`equity × risk% ÷ (stopDistance × pointvalue)`), so a wide 50 EMA stop and a tight one
  risk the same amount. Check that `syminfo.pointvalue` matches your broker's XAUUSD
  contract before trusting the currency figures.

---

## Before trusting a backtest

1. **Set commission and slippage in Properties.** They default to zero so the raw signal is
   visible first. On 15m gold the spread is a real share of a 50 EMA stop; a curve built at
   zero cost is not a result.
2. **Stay on 15m.** The EMAs are read from the chart timeframe, so a different chart
   timeframe is a different system. The dashboard shows a warning when the chart is not 15m.
3. **Watch the trade count.** Tight pull-away and long retest windows produce very few
   trades on some periods; a 60 %-win-rate sample of 11 trades is noise.

---

## Alerts

* Entry fires an `alert()` with a JSON payload (`action`, `symbol`, `entry`, `stop`,
  `target`, `rr`) suitable for a webhook.
* The crosses fire a plain "watching for the retest" alert, so the setup can be watched
  without sitting on the chart.

Create the alert on the strategy with **"Any alert() function call"**.

---

## Dashboard

Top-right by default: timeframe check, current state (flat / armed and waiting / in trade),
both EMA values, bars since the cross, the live entry/stop/target with the stop distance in
points, and closed-trade stats (count, win rate, profit factor, net P&L).

---

## Known limitations

* **Net position only.** Pine strategies hold one position, so a short signal appearing
  while a long is open is skipped, not stacked. `flat` is part of every entry permission.
* **A cross exit is one bar late by design.** It is detected at the close of the crossing
  bar and filled at the next open. On a fast reversal the stop can be hit first — that is
  the honest result, not a modelling error.
* **Intrabar order of stop vs target is unknown.** When a single bar spans both levels, the
  broker emulator resolves it by its own assumption, not by tick data. Bar Magnifier (paid
  plans) is the fix if that matters for your sample.
* **The retest window is measured in bars, not in structure.** A setup that pulls back over
  a weekend gap will age out on bar count.
* **A high N and a short retest window fight each other.** Waiting for retest 3 inside a
  40-bar window leaves very little room; raise `Retest must happen within N bars` (or set it
  to 0) when raising N, and watch the trade count on the dashboard.
* **The 1h filter costs trades.** Stacking it with a high N can cut the sample to a handful
  over a year of 15m data. Two filters that each look sensible can leave nothing behind
  worth measuring.
