# No Wick Retest — Strategy port, implementation notes

**File:** `no_wick_retest_strategy.pine` (Pine Script **v6**, `strategy()`, `overlay=true`)
**Ported from:** `no_wick_retest.pine` — see `DEV_NOTES_no_wick_retest.md` for the
trade model itself, which is unchanged here.

This document only records what the `strategy()` port does *differently* and why.
Anything not listed below behaves exactly as the indicator does: no-wick candle
detection, the MA location filter at level creation, pull-away, retest, the four
entry models, the confirmation toggles, session/day/trend filters, the structural
stop, the target multiple and the post-breakeven profit lock.

---

## Order handling

The entry model decides the order type. There is no input for it, because the
model already says what the fill is supposed to be.

| Entry model | Order | Fill |
|---|---|---|
| `Confirmation Close` | market | the signal bar's close |
| `Rejection Close` | market | the signal bar's close |
| `Immediate Level Touch` | limit at the level, resting from the bar pull-away completes | the level, intrabar |
| `Armed Level Retest` | limit at the level, resting from the confirmation bar | the level, intrabar |

`process_orders_on_close = true` is what makes the two market models fill at the
signal bar's close instead of the next bar's open — that is the price the
indicator books, so the two scripts stay comparable.

The two limit models are actually *more* faithful than the indicator. The
indicator can only notice the retest at a bar close and therefore books the
level as though it had been filled there; a resting limit is filled by the
broker emulator at the level, intrabar, which is what "fill at the level" means.

### What the limit models cost
A resting order occupies a trade slot for as long as it waits. With
`Allow Overlapping Trades` off (the default) that means one setup can block the
next for up to `Maximum Candles to Retest` bars, where the indicator would have
been free again immediately. Two knobs bound it:

* the order is cancelled when the setup expires (`Maximum Candles to Retest`);
* `Cancel Resting Orders When Filters Turn` (on by default) pulls it as soon as
  the session, day or trend filters stop allowing the trade. The indicator
  evaluates those filters on the entry bar; a resting order has no entry bar
  yet, so re-checking them every bar is the closest equivalent.

Edge case: with `Require Close Back Through No-Wick Level` turned **off**, an
`Armed Level Retest` limit placed on the confirmation bar can be filled at that
same bar's close if the close is already through the level. The indicator
requires a strictly later bar. Leave that confirmation on (the default) and the
case cannot arise.

## Brackets

Every entry gets a `strategy.exit` bracket (stop + limit) placed at the same
time as the entry, priced off the planned entry. When the fill is registered the
bracket is re-issued against the price the fill actually happened at, so
slippage and gaps shift the stop and target rather than distorting the stop
distance the R accounting divides by.

The consequence is a one-bar window right after entry where the bracket still
sits on the planned prices, off by the slippage setting. It is not worth closing:
doing so would mean no bracket at all on the first bar after entry.

The profit lock is applied at the bar close, after the emulator has already
processed that bar's fills. That reproduces the indicator's ordering exactly —
a bar that reaches both the stop and the lock trigger is a stop-out.

## Position sizing

The indicator scores in R and never needs a quantity. Three modes here:

* `Fixed Contracts` — `Order Quantity`, always.
* `Risk $ per Trade` — `floor(budget / (stop distance x syminfo.pointvalue))`.
* `Risk % of Equity` — same, budget taken from `strategy.equity` at order time.

Both solved modes are clamped by `Minimum Contracts` / `Maximum Contracts`. A
signal whose size rounds to zero contracts is rejected and shows up as
`Position size rounds to zero` in `Last Rejection`.

## One net position

Pine strategies hold a single net position, so the indicator's ability to run a
long and a short at once cannot be reproduced. `Allow Overlapping Trades` on
stacks *same-direction* trades up to `Maximum Concurrent Trades` (resting orders
count against the cap). An opposing signal is then handled by
`Opposite Signal Handling`:

* `Skip the signal` (default) — rejected as `Opposite position open`.
* `Reverse the position` — resting orders are cancelled, the position is flattened
  and the new signal is taken. The flattened trades are booked as
  `Reversal / Manual Exits`, not as wins or losses, because neither the target
  nor the stop decided them.

With overlapping trades off, the one-trade rule blocks the case before this
input matters.

## Capital, margin and the silent funds refusal

`initial_capital = 1000000`, `margin_long = 0`, `margin_short = 0`.

This is not cosmetic. One NQ contract at 29,000 is roughly $580,000 of notional.
If the broker emulator's margin requirement cannot be met from the account
balance it **refuses the order and says nothing** — the Strategy Tester simply
reports no trades, which looks exactly like a broken signal engine. Zero margin
plus a large notional capital takes that failure mode off the table so the
backtest measures the strategy rather than the account. Set realistic values in
the Strategy Tester's **Properties** tab when you want the equity curve to model
margin; Pine will not accept `input.*` for these parameters.

A market order that has not been reported filled by the bar after it was placed
is treated as refused: it is cancelled, counted under `Cancelled`, and
`Last Rejection` reads `Market order refused — check capital / margin`. Without
that, a single refused order would hold the one-trade slot for the rest of the
backtest and every later signal would be rejected as `Trade already open`.

Four counters are also plotted to the Data Window (`Diag: setups / orders /
fills / cancelled`) so the engine can be read even if the dashboard is not
drawing. Setups but no orders means the filters are refusing the signals;
orders but no fills means the emulator is refusing the orders.

## Statistics

The registry no longer simulates fills — it reads them back. Each signal gets a
unique entry-order id (`NWR<n>`) and bracket id (`X<n>`); closed trades are
matched to their record by that id and scored from
`strategy.closedtrades.*`. Outcome classification:

| Outcome | Test |
|---|---|
| `TP` | our bracket did the exiting and the exit price reached the target |
| `LOCK` | our bracket, the profit lock had already moved the stop |
| `SL` | our bracket, neither of the above |
| `MAN` | some other exit id — a reversal or a flat |

Per trade, with `q` contracts and `rDist` the stop distance in price:

```
grossR = dir x (exit - entry) / rDist
commR  = commission / (rDist x pointvalue x q)
netR   = grossR - commR
```

Slippage is not modelled any more: it is inside the fill prices the emulator
returns, so it is already inside `grossR`. That removes the whole
fees-versus-slippage accounting problem described in the indicator's notes —
commission is the only cost left to convert, and it converts against the trade's
own cash risk rather than a planned `$ per 1R` figure.

Commission and slippage come from the `strategy()` declaration
(`cash_per_contract 0.95`, `slippage 1`) and are overridden in the Strategy
Tester's **Properties** tab, not in the script's inputs — Pine will not accept
`input.*` values for those parameters.

### Why the dashboard has a size control

TradingView **hides** a table that does not fit its pane rather than clipping
it, and the Strategy Tester panel takes roughly half the chart height — which an
indicator never has to share. At `size.small` the full 31-row table is about
465px and simply vanishes on a half-height pane. Hence `Dashboard Text Size`
(default `tiny`, ~340px) and `Dashboard Detail` (`Compact` keeps the 15 rows
worth watching live and drops the breakdowns, ~180px at tiny).

Rows are staged into parallel arrays and written in one loop, so the row set can
vary with the detail mode without every row index having to be renumbered.

### Dashboard rows that changed

| Row | Change |
|---|---|
| `Orders Placed / Filled` | replaces `Confirmed Entries`; a resting limit that never fills is placed but not filled |
| `Expired / Cancelled / Bad Stop` | `Cancelled` is new: resting orders pulled by expiry or by a filter |
| `Open / Resting` | open positions and orders still waiting at their level |
| `Reversal / Manual Exits` | new; exits that were not decided by our bracket |
| `Commission Charged` | replaces `Estimated Costs`, and is now what was actually charged |
| `Strategy Net Profit` / `Strategy Profit Factor` / `Open P&L` | new; straight from the Strategy Tester |
| `Max Closed Drawdown` | the `$` half is now realized cash, not `R x planned $ per 1R` |
| `Prop DD Used` / `DD Cushion Remaining` | driven by that realized cash drawdown |

`Max $/R @ Hist. DD` still divides `Account Max Drawdown` by the drawdown in R,
which is the one prop-risk number that is genuinely size-independent.

`TP Win Rate` and `Positive Exit Rate` are taken over bracket exits only, so a
reversal cannot flatter or depress them.

## Automation

`Enable Ghost JSON Webhook Alerts` now works two ways:

* the same `alert()` JSON as the indicator, on entry, profit lock and exit —
  create one alert with **Any alert() function call**;
* the same payload attached to every order as `alert_message`, so an alert
  created with **Order fills only** can send `{{strategy.order.alert_message}}`
  and fire on the real fill rather than on the bar close.

The payload gained the actual filled `quantity`; `action` is still one of
`entry` / `modify` / `exit`.

## Unchanged on purpose

* `Signal / Execution Timeframe` is still a guard, not a `request.security()`
  call, for the same reason: a stateful setup machine inside `request.security`
  repaints.
* ATR stays fixed at 14.
* The whole engine still runs under `barstate.isconfirmed`, and
  `calc_on_every_tick` is off, so signals do not repaint.
* Every drawing, filter, tooltip and default is carried over verbatim so the two
  scripts can be run on the same chart and compared row by row.
