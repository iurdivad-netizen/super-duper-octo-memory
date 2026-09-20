# Stoic Trader — SBS / Golden Pocket — Dev Notes

`stoic_sbs_golden_pocket.pine` — Pine Script **v6**, `indicator("Stoic Trader — SBS / Golden Pocket", overlay=true)`.

## Provenance — read this first

The requested source was a private NotebookLM notebook plus `stoicedge.com`. **Neither was
reachable** from the build environment (the agent egress proxy blocks both domains), so the
rules below were reconstructed from publicly indexed descriptions of the Stoic Trader system
checklist and of the Swing Breakout Sequence. Specifically:

| Rule | Confidence | Source basis |
|---|---|---|
| Bias from a 20 and a 200 moving average; above both = bull, below both = bear, 20 crossing 200 = transition | High | Stoic Trader System checklist, quoted consistently across indexed copies |
| Entry at or near the **61.8%** retracement of the impulsive move | High | Same checklist; "Golden SBS" descriptions agree |
| Targets **2R / 3R / 4R** | High | Same checklist |
| Stop **beyond the sequence low/high** | Medium | "Golden SBS" descriptions ("tight stop-losses positioned below the sequence's low") |
| SBS beat order: breakout → first pullback (FT) → new high → return to liquidate FT → double-bottom reversal → new swing high | Medium | Indexed SBS descriptions; wording varies between sources |
| Pre-marking previous daily high / low / close the night before | High | Stoic Edge blog on emotional control |
| Daily risk governors (−2R red-day stop, +3R green-day stop) | High | @StoicTA post, but **not implementable in an indicator** — noted only |

Anything marked Medium is an interpretation. If the notebook specifies different swing
definitions, a different fib anchor, or a different stop rule, those are the three places to
correct — they are isolated in the code (`f_advance`, `bullFrom`/`bearFrom`, `i_stopMode`).

## Honest framing

A 20/200 MA filter plus a 61.8% retracement entry is a generic trend-continuation template.
The Stoic material's own emphasis is that the edge is *following simple rules*, not the rules
themselves. So this script is built as a bookkeeper, not an oracle: it finds structure, draws
the level, computes R, and keeps a forward scorecard so the setup can be falsified on the
user's own instrument before any money is risked. Given this repo's history (several strategies
in `DEV_NOTES_*` were tested to death and found to have no out-of-sample edge), that scorecard
is the most important feature here.

## Structure — the state machine

One `Seq` object per direction, mutated in `f_advance()`. `stage` is the SBS beat:

```
0 idle
1 breakout        // close through the last unbroken confirmed pivot (BOS)
2 first tap       // first confirmed pullback pivot AFTER the breakout bar
3 new extreme     // price exceeds the extreme that stood when the FT formed
4 FT liquidated   // price returns through the FT level (the liquidity sweep)
5 in trade        // a setup has triggered; no re-entry until it resolves
```

Swing points come from `ta.pivothigh` / `ta.pivotlow` with `i_pivLeft` / `i_pivRight`
(default 5/5). Structure is therefore recognised `i_pivRight` bars late. That lag is the
price of not repainting, and `i_pivRight` is by far the highest-leverage input in the script.

`minStage` gates entries:
- `i_reqSBS = false` (default) → `minStage = 2`. This is the documented **four-step** system:
  break structure, then buy the 61.8% of the impulse.
- `i_reqSBS = true` → `minStage = 4`. The strict six-beat sequence. Far fewer signals.

A breakout only *starts* a sequence when `stage == 0`. Later breaks inside a live sequence are
beat 3, not a new sequence — otherwise strong trends would restart the machine on every push.

Invalidation: `close` gives back the leg origin, or the sequence exceeds `i_maxSeq` bars.

## Fib anchoring

```
f_retr(from, to, f) => to - (to - from) * f
```

Direction-agnostic: for a bear leg `to - from` is negative so the result sits *above* `to`.

`from` is the impulse origin (the confirmed swing that launched the break). With
`i_legMode = "Last leg (recent swing)"` it becomes the most recent confirmed swing instead,
but only when that swing is *deeper into the leg* than the origin — otherwise the "retracement"
would be measured off a point price has already passed.

`to` is the running impulse extreme, updated every bar.

## The `tapped` latch (and the bug it caused)

`Seq.tapped` records that price has traded through the 61.8% level, which is what the
"Confirmation close" trigger needs — tap first, then close back through.

First implementation never cleared it. Consequence: tap the level, then rally to a new high.
The leg is now longer, so the 61.8% is *lower*, and `close > bullEntryLvl` becomes trivially
true — a long would fire near the highs on a stale tap. Fixed by clearing `tapped` in
`f_advance()` at the same point `pullExt` resets, i.e. whenever a new impulse extreme is made.

## Realtime consistency

Fields of a `var` object are **not** rolled back between realtime ticks. Most updates here are
safe because they are monotone within a bar (`high`/`low` only extend, `stage` only advances).
Two are not, because they test `close`, which fluctuates intrabar:

- break of structure (`bosUp` / `bosDn`)
- sequence invalidation through the origin

Both are gated on `barstate.isconfirmed`, which also matches the documented rule ("close
through structure") and makes historical and realtime behaviour identical.

Entries are additionally gated on `barstate.isconfirmed`, so no marker or alert appears before
the bar is final.

## Risk

```
stopRef  = i_stopMode == "Impulse origin" ? seq.origin : seq.pullExt
stopRaw  = min(stopRef, low) - i_stopBuf * atr        // long; mirrored for short
R        = close - stopRaw
targets  = close + {i_t1, i_t2, i_t3} * R             // 2R / 3R / 4R by default
```

`pullExt` is the counter-extreme since the last new impulse extreme — i.e. the low of the
*current* pullback, which is the "sequence low" the Golden SBS material describes. A setup is
rejected if `R <= max(mintick, 0.05 * ATR)` to avoid degenerate risk at the level.

Entry is the trigger bar's close. No slippage or commission is modelled — this is an indicator.

## Scorecard

One open `Trade` per direction, resolved bar-by-bar in `f_track()`:

- **Stop is checked before targets.** A bar whose range contains both scores as a stop. That
  is the conservative reading and it *understates* the hit rate; tick data would score higher.
- Tracking starts on the bar *after* entry.
- A trade resolves on a stop or on T3. `hit` records the deepest target reached beforehand, so
  "reached 2R then stopped" still counts as a 2R touch.
- `E[R] flat 2R` = `p(T1) * i_t1 - (1 - p(T1))` — the expectancy of a single-exit plan taking
  everything off at target 1. It is the one number worth looking at before trusting the setup.

This is a smoke test, not a backtest. It rejects obviously broken parameter sets. For a real
evaluation, port the trigger logic into a Python harness in the style of the other
`backtest_*.py` scripts in this repo and run out-of-sample blocks.

## Not implemented, deliberately

- **Daily risk governors** (−2R stop on a red day, stop after +3R or the first A+ trade on a
  green day). These are account-level rules about *the trader*, not the chart. An indicator
  cannot know your fills or your P&L. They belong in a journal or in a `strategy()` port.
- **"A+ trade" classification.** Undefined in any public source; inventing a definition would
  be dressing a guess as a rule.
- **Double-bottom pattern matching at beat 5.** The FT sweep (beat 4) plus the golden-pocket
  confirmation close is a cleaner, less parameter-hungry proxy for the same idea.

## Known lint output

`tools_pinelint.py` reports 17 errors, all in its known false-positive classes (bare hex colour
literals, UDT type names and their field declarations, and `var <UDT> x = T.new()` declarations
which its assignment regex does not match). Compare with `naked_poc_levels.pine`, which reports
the same classes. There are no real findings.

## Tuning notes

| Input | Effect |
|---|---|
| `i_pivRight` | The dominant setting. Low = more, noisier sequences recognised sooner. High = fewer, cleaner, later. Change this before anything else. |
| `i_reqSBS` | Off = documented 4-step system. On = strict 6-beat SBS, a small fraction of the signals. |
| `i_entryMode` | "Confirmation close" waits for a close back through the level. "Golden touch" fires on the tap — earlier fills, worse hit rate. |
| `i_stopMode` | "Sequence extreme" gives tight stops and big R multiples with more stop-outs. "Impulse origin" is the opposite trade-off. |
| `i_legMode` | "Last leg" produces shallower levels and more signals in extended trends. |
