# BB Squeeze — Dev Notes

`bb_squeeze.pine` — Pine Script **v6**, `indicator("BB Squeeze", overlay=true)`.

## What it is

A combination of Bollinger Bands and the Keltner Channel. The squeeze condition is
containment: the Bollinger Bands sitting entirely *inside* the Keltner Channel.

```
inSqueeze = bbUpper < kcUpper and bbLower > kcLower
```

BB width is driven by standard deviation, KC width by ATR / average range. When the
standard-deviation envelope shrinks inside the average-range envelope, realized
dispersion has fallen below the channel's own volatility baseline — the classic
pre-expansion coil (TTM Squeeze / LazyBear lineage).

## The N-bar persistence filter

The point of this script is that a **single** bar of containment is noise. Nothing is
marked until the squeeze has held for `N` consecutive bars (`i_minBars`, default 6):

```
var int sqzBars = 0
sqzBars   := inSqueeze ? sqzBars + 1 : 0     // resets the moment containment breaks
qualified  = sqzBars >= i_minBars
```

- `qualified` — the persistent "squeeze is on" state, drives background + bar color.
- `justQualified` — fires exactly once, on the N-th consecutive bar (`SQZ` triangle).
- `released` — a *qualified* squeeze ends (`not inSqueeze and inSqueeze[1] and sqzBars[1] >= N`).
  Unqualified squeezes that break early produce no release signal at all.

## Marking the first N-1 bars

`bgcolor()` can only paint the current bar, so the bars *before* qualification can never
be colored retroactively. To show the whole coil, a `box` is anchored at the squeeze's
true start bar (`sqzStart`, captured on the containment transition) and extended each bar
while qualified, using the running high/low of the squeeze run. On release the box handle
is dropped (`sqzBox := na`) so the drawn box freezes in place.

Both markings are kept: the box shows the full squeeze, the background/dots show the
qualified portion.

## Inputs worth tuning

| Input | Default | Notes |
|---|---|---|
| BB length / mult | 20 / 2.0 | Standard. |
| KC length / mult | 20 / 1.5 | 1.5 is the TTM convention; **1.0 gives a tighter, rarer squeeze**, 2.0 a loose and frequent one. This is the single most impactful knob. |
| KC basis MA | EMA | SMA available for a symmetric BB/KC comparison. |
| KC range basis | True Range (ATR) | ATR counts gaps; High-Low ignores them. On gappy instruments ATR widens KC and produces *more* squeezes. |
| N (min bars) | 6 | Scale with timeframe — 6 bars on 5m is 30 minutes, on daily it is over a week. |
| Confirmed bars only | on | Gates every marker and alert on `barstate.isconfirmed`. |

## Repainting

Intrabar, `bbUpper`/`kcUpper` move with price, so containment can flip until the bar
closes, and `sqzBars` can tick up and then roll back. "Confirmed bars only" (default on)
gates all shapes, labels and alerts on `barstate.isconfirmed`. The bands, background and
zone box still update live by design — only the signals are gated.

## Momentum on release

`mom = ta.linreg(src - avg(avg(highest, lowest), sma), momLen, 0)` (LazyBear form). It is
used **only** to color the release marker up/down and to fill the table row. It is a
direction hint about the bar the squeeze fired on, not an entry signal — a squeeze says
*expansion is likely*, never which way.

## Alerts

`alertcondition` hooks: qualified, fired, fired-up, fired-down. Plus dynamic `alert()`
calls with ticker/timeframe/bar-count for webhook use, at `alert.freq_once_per_bar_close`.

## Pine v6 notes

- All `ta.*` calls are unconditional at global scope (both KC basis variants and both
  range variants are computed every bar, then selected) — required for consistent history.
- `plot`/`fill`/`bgcolor`/`barcolor`/`alertcondition` are global; visibility toggles are
  applied to the *value*, not to the call.
- Line continuations are indented by a non-multiple of 4 spaces so they are not parsed as
  local blocks.
