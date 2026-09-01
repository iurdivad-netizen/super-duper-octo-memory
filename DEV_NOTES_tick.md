# Tick — Dev Notes

`tick.pine` — Pine Script **v6**, `indicator("Tick", overlay=false)`.

## What it is

The lower pane from the SMB / tradingworkshop screenshot: ThinkOrSwim's
`Comparison($TICK)` study, rebuilt for TradingView. For every bar on the chart it
requests the OHLC of a market-breadth TICK index and draws it as bars in its own pane,
with a zero line and extreme bands.

TICK = (issues trading on an uptick) − (issues trading on a downtick), sampled
continuously across an exchange. It is breadth, not price. Near zero the tape is mixed;
±1000 means nearly everything is being lifted or hit at once — a one-sided burst that
usually marks exhaustion rather than the start of a move.

## Why OHLC bars and not a line

A line of TICK closes throws away most of the information. A bar that spiked to +900 and
closed at +50 is a completely different tape from one that ground sideways at +50, and
only the bar's range shows that. This is why the ToS study plots OHLC and why `OHLC bars`
is the default here — `Candles`, `Line (close)` and `Histogram (close)` are available but
secondary.

## The data

```
[tO, tH, tL, tC] = request.security(tickSym, timeframe.period,
     [open, high, low, close],
     i_hideNa ? barmerge.gaps_on : barmerge.gaps_off,
     barmerge.lookahead_off)
```

One call, one tuple — the four values must come from the same request so they describe
the same bar of the index. `lookahead_off` throughout: historical bars never see future
data.

Symbols (verified on TradingView):

| Preset | Symbol |
|--------|--------|
| NYSE | `USI:TICK` |
| Nasdaq | `USI:TICKQ` |
| Dow | `USI:TICKI` |
| All US stocks | `USI:TICK.US` |
| Custom | whatever you type |

**This is the one real limitation.** TICK is an index feed. If a plan does not carry it,
`request.security` returns `na` on every bar and the pane is simply empty — which looks
like a broken script. So the script tracks `firstValidBar` and, if nothing ever came
back, draws a label on the last bar naming the symbol and the likely cause. Nothing else
in the script can fix a missing data subscription.

### gaps_on vs gaps_off

Default is `gaps_on` ("Hide bars with no new TICK data"): the index only prints during the
regular cash session, so pre/post-market bars come back `na` and are left blank. With
`gaps_off` the last known value is carried forward, which draws a flat line of repeated
bars overnight — and, because the cumulative sum accumulates on any bar where data is
present, inflates the cumulative reading outside the session. Leave it on unless you have
a reason not to.

## Session state

Everything session-scoped resets on `timeframe.change("D")`:

```
var float sesHigh, sesLow, cumTick
var int   nExtUp, nExtDn
```

- `sesHigh` / `sesLow` — the day's TICK range, tracked on the index's own high/low.
- `cumTick` — running sum of TICK closes since the open. Net breadth for the day: it
  trends up on a day of persistent buying even when individual readings look ordinary.
  It is its own plot style (`Cumulative (session)`) rather than an overlay, because its
  scale is thousands and it would flatten the bars into a stripe.
- `nExtUp` / `nExtDn` — how many bars have tagged the outer band today, counted on the
  bar's **range**, not its close: a bar that traded to +1000 tagged the extreme even if it
  closed back at +200.

On a daily-or-higher chart every bar is a new day, so the stats collapse to that one bar's
values. Coherent, just not very interesting — this is an intraday tool.

## v6 traps this script had to route around

1. **Lazy `and`/`or`.** `hasTick and ta.crossover(tC, 0)` would skip the `ta.crossover`
   call on every bar where `hasTick` is false, corrupting its internal state. The crosses
   are computed unconditionally at global scope and gated afterwards:
   ```
   xUp = ta.crossover(maSrc, 0)      // always runs
   zeroUp = hasTick and xUp          // gated here
   ```
2. **`ta.*` needs a continuous series.** With `gaps_on` the TICK close is `na` outside the
   session, which would poison a moving average. The MA is fed `fixnan(tC)` (forward-fill)
   and then hidden on bars without data at plot time.
3. **`plot`/`plotbar`/`hline` cannot live in an `if`.** All five plot styles are wired to
   the same data and the unselected ones resolve to `na`, so the style choice happens in
   the values, not the control flow.
4. **`hline()` takes input-qualified prices and colours only.** Band visibility can't
   branch on a series, so hiding a band swaps in a fully transparent colour instead. This
   works because `i_showLvl and i_mode != M_CUM` is built from inputs and stays
   input-qualified.

## Colouring

`Colour by` is independent of plot style:

- `Single colour` — the flat indigo of the original ToS study (default).
- `Close sign (+/-)` — green above zero, red below.
- `Bar direction` — close vs open of the TICK bar itself.
- `Extremes only` — everything grey except bars reaching the inner band. The most useful
  mode once you stop reading every bar.

`Highlight bars that reach the outer band` layers on top of all four, so extremes stay
visible in every mode.

## Alerts

`TICK extreme high` / `TICK extreme low` (outer band tagged), `TICK crossed above zero` /
`TICK crossed below zero`. All `alertcondition`, so they show up in the alert dialog.

## What it deliberately does not do

No signals, no divergence detection against price, no bar colouring on the price pane.
TICK is context — it tells you what the rest of the tape is doing while your setup plays
out. Wiring it to entries would be a different script.
