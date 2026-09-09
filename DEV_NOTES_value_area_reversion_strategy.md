# Value Area Reversion Strategy — Dev Notes

**File:** `value_area_reversion_strategy.pine` (Pine Script v6)
**Converted from:** the "Value Area Reversion Signals" (VARS) indicator
**Anchor:** 18:00 `America/New_York` (CME futures day boundary)
**Intended chart:** 5m ES / NQ

---

## What the conversion actually involved

The indicator supplied a *signal* and nothing else. Sections 3–8 of the strategy
are a faithful port of its profile engine and reclaim state machine — with the
signal-detection block stripped of the two added lines, it is character-identical
to the source. Everything else (stop, target, invalidation, sizing, session
handling, filters) is new, because the indicator never specified any of it.

That distinction matters more than it sounds: **all of the P&L lives in the part
the original author did not write.** A backtest of this file is not a test of the
VARS signal. It is a test of the signal *plus* six exit-engine choices I made.
Change the stop mode and you are testing a different system.

### Added to the ported state machine

Two lines per direction, tracking the furthest excursion outside the value area
(`bearishBreakoutLow` / `bullishBreakoutHigh`). The indicator had no need for
them; the strategy uses them as the default stop, because the breakout extreme is
the price that falsifies the reclaim thesis.

---

## Why the signal is the binding constraint

A bullish reclaim requires **six conjunctive conditions**:

1. a close below VAL (breakout begins),
2. at least two breakout bars (deceleration cannot be measured on one),
3. a down-volume bar lower than the previous down-volume bar,
4. a close back inside the value area,
5. a bullish engulfing bar,
6. up-volume above both the bar's down-volume and the last breakout bar's.

Condition 3 has a quirk worth knowing: `currentDownVolume` is zero on any bar that
closes up, so **a bullish bar during a bearish breakout does not update the
deceleration state at all** — it is skipped, not counted as slowing. Preserved for
fidelity, not endorsed.

Expect single-digit signals per month on 5m. Two consequences:

- **Do not tune parameters on this sample.** Ten to thirty trades cannot
  distinguish an edge from noise at any useful confidence. Every input in this
  file that you optimise is a degree of freedom spent on a sample that cannot
  support it.
- **The min-R filter is not free.** It removes signals from an already-thin set.
  The dashboard reports signals seen vs. filtered out, split by source, precisely
  so you can see whether you have filtered the strategy into non-existence.

---

## Volume siding is a proxy, not delta

`currentUpVolume` / `currentDownVolume` assign the **entire** bar's volume to one
side based on `close >= open`. This is not order flow. "Breakout volume was
slowing" therefore means "the bar's total volume fell, and that bar happened to
close in the breakout direction". The signal's central claim — that sellers are
exhausting — rests on a measurement that cannot see buyers and sellers separately.

If the strategy shows an edge, the first robustness test should be replacing this
with real up/down volume from a lower timeframe (`request.security_lower_tf`), and
checking whether the edge survives. If it does not, the edge was an artifact of
the proxy.

---

## The developing value area

When any session bar makes a new high or low, the profile range and bin size are
rebuilt and **every level moves**. Early in a session the current-day VA is built
from a handful of bars and is close to meaningless. This is why current-day
signals default OFF, matching the indicator's own default.

This is *not* repainting — each bar's levels are computed only from bars up to
that bar, so history is causal and the backtest is honest. But it does mean the
current-day VA is a moving target within a session, and a "breakout" of it early
in the session is often just the range not yet being established.

The previous-session VA is fixed for the whole session and is the more defensible
reference. Signal-source priority reflects this: when both fire, previous wins.

---

## Exit engine — the choices and why

| Component | Default | Reasoning |
|---|---|---|
| Stop | Breakout extreme + 0.1 ATR | The excursion low is the level that says the reclaim failed. A signal-bar stop is tighter but gets swept by the retest. |
| First target | Reference POC, 50% off | The POC is a far higher-probability touch than the far VA edge. Scaling there is what makes the geometry survivable. |
| Final target | Opposite VA edge | Full rotation through value — the actual thesis of "value area reversion". |
| Invalidation | Close back outside the reference VA | **The most consequential setting in the file.** The trade says the breakout failed; a close back outside says it did not. This usually exits before the stop and materially changes the return distribution. |
| Breakeven | After the first target | Standard; reduces the tail of full-stop losses at the cost of more scratches. |
| Anchor flat | ON | At 18:00 the reference value area is *replaced*. Holding through it is holding a position whose thesis has been deleted. |

**The geometry problem is real.** A stop at the breakout extreme with a POC target
frequently yields sub-1R trades. That is why the partial exists and why the
min-R filter defaults to 1.0 measured against the *final* target. If you find
yourself lowering min-R to get more trades, you are buying sample size with
expectancy.

### Target fallback ladder

A POC or opposite-edge target can sit on the *wrong side* of the entry when the
reclaim bar closes deep into the value area. Rather than trade an inverted
target, the final target falls back to the R-multiple, and the first target is
disabled (no partial) if it is not strictly between entry and final target.

---

## Fills and realism

- Entries are issued at signal-bar close and fill at the **next bar's open**
  (`process_orders_on_close = false`). A gap through the stop exits immediately at
  a worse price. That is realistic.
- Bracket orders are issued on the signal bar *and* re-issued each bar the
  position is open. Without the signal-bar issue the position would sit
  unprotected for one full bar after the fill.
- `commission_value = 2.50` and `slippage = 2` are **ES-shaped placeholders**. Set
  them for your instrument before reading any equity curve. On a strategy whose
  targets are often ~1R, transaction costs are not a rounding error — they are a
  large fraction of the edge.

---

## Dashboard

Splits signals, filtered signals, trades, win rate, average R and total R by
**previous-VA vs current-VA source**. R is computed per entry with partial exits
folded back together (keyed by entry bar index), so a scaled-out trade counts once,
not twice.

If one source carries the entire result, the other is not an edge — it is padding
on the trade count. Pooling them into a single equity curve hides exactly that.

---

## What would change the conclusion

- **More signals from a shorter timeframe.** Running 1m multiplies the sample but
  also multiplies the noise in the volume proxy. Worth testing; not obviously
  better.
- **Replacing the volume proxy with true delta.** The single highest-value test.
- **Dropping the engulfing requirement.** It is the most restrictive condition and
  has the least theoretical justification of the six. Testing the signal with and
  without it tells you whether the candle pattern contributes anything or is
  simply cutting the sample.
- **Testing the exit engine against a fixed-R baseline.** If a plain 1R stop /
  2R target on the same signals performs comparably, the profile-based targets
  are decoration and the edge (if any) is in the entry alone.

## Known limitations

- The profile is rebuilt from all stored session bars whenever a new extreme
  prints. On very long sessions at 1m this is the heaviest loop in the script;
  it has headroom at 5m but is worth watching if you shorten the timeframe.
- Reference VA levels are frozen at entry for the re-break exit. For previous-VA
  trades this is exact (those levels are static within a session); for current-VA
  trades the live VA may drift away from the frozen one.
- Only one position at a time (`pyramiding = 0`), max two entries per anchored
  session by default.
