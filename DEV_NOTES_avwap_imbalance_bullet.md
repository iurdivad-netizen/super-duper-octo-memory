# AVWAP Imbalance 1:4 — "Mathematical Risk Framework"

**File:** `avwap_imbalance_bullet_strategy.pine` (Pine Script v6)
**Source:** NotebookLM notebook, "Mathematical Risk Framework: Optimizing Capital
Allocation for Prop Firm Payouts", 6 sections.
**Intended market:** NQ / MNQ futures, 1m–5m, 08:30 ET release window.

---

## Part 1 — What is codeable and what is not

The source is two documents welded together.

| Section | Content | Testable in Pine? |
|---------|---------|-------------------|
| 1 | Portfolio rotation vs. single-account survival | No — Pine has one account |
| 2 | Cost of Acquisition, 31% eval pass rate | No — no eval simulation |
| 3 | The "bullet" system, 2 × $1,000 per account | Partly — single-account survival only |
| **4** | **Anchored VWAP + FVG execution protocol** | **Yes — this is the script** |
| 5 | Payout stabilisation, idling, withdrawal schedule | No — firm-side rules |
| 6 | 1,000-trade / $498,000 backtest claim | No — but see Part 4 |

Only Section 4 is a trading strategy. Sections 1–3 and 5–6 are portfolio
accounting layered on top of it, and that accounting is where the framework
breaks (Part 3).

## Part 2 — Mapping Section 4 to code

| Source rule | Implementation |
|-------------|----------------|
| "Define the VWAP Anchor Point at Midnight (00:00) New York Time" | `sumPV/sumV/sumP2V` accumulators reset on the NY-hour transition to `i_anchorHr` (default 0). This is **not** the CME 18:00 session VWAP — the anchor is deliberately mid-session. |
| Standard deviation bands | Volume-weighted SD: `sqrt(Σp²v/Σv − vwap²)`, bands at `i_sdMult` (default 1.0). |
| "Only buy below the 1st SD band, only sell above" | Hard gate `longBias` / `shortBias` on the reclaim level, not on `close`. Rejections counted in `rejected · bias zone`. |
| 3-candle FVG, "gap between the wick of the first candle and the wick of the third" | `high[2] < low[0]` (bullish) / `low[2] > high[0]` (bearish). Wicks, as specified — not body-based. |
| "an aggressive candle creates a price displacement" | Unquantified in the source. Implemented as middle-candle range ≥ `i_dispMult × ATR(14)`, default 1.0, settable to 0. |
| "mechanical close back above the imbalance" | Requires (a) price taps the gap, then (b) a confirmed close through the reclaim level with `close[1]` on the other side. `i_reclaim` selects the far edge (strict) or the 50% midpoint. |
| Target = "reversion to the central VWAP line" | `strategy.exit(limit = VWAP)`. `i_fixTgt` freezes it at entry (default) — see Part 3f. |
| "minimum 1:4 Risk/Reward" | `i_minRR` = 4.0. Setups that cannot reach it are **rejected and counted**, never taken at worse odds. This counter is the most important output of the script. |
| 08:30 EST window | `i_sess` default `0830-0930`, timezone `America/New_York` (tracks EST/EDT; a fixed EST offset drifts an hour for eight months of the year). |
| $1,000 bullet | `qty = floor(1000 / (stopPts × pointvalue))`, capped by `i_maxQty`. Floor means realised risk ≤ $1,000. |
| 2 bullets = $2,000 drawdown | `i_bullets`, trailing off the equity peak by default. `i_simDeath` halts permanently when spent — **off by default**, so the backtest collects a full sample instead of stopping at the first dead account. |

Deliberate departures, all flagged in tooltips: the displacement threshold and
the reclaim level are invented (the source gives neither), and only the most
recent unresolved imbalance per direction is tracked rather than a stack.

## Part 3 — Where the framework's arithmetic fails

### a. Expected wins per funded account is 0.56, not 25

Two bullets, reset to two on a win (profit restores the buffer), account dead on
a second consecutive loss. With win probability `p`, `q = 1−p`:

```
H(1) = p(1 + H(2))
H(2) = p(1 + H(2)) + q·H(1)
     = p(1+q)(1 + H(2))
=>  H(2) = k/(1−k),   k = p(2−p)
```

At the source's own `p = 0.20`: `k = 0.36`, **H = 0.5625 expected wins over the
entire lifetime of a funded account.** A 64% chance the account dies before its
first payout.

### b. $498,000 requires ~443 funded accounts, not 10

$498,000 ÷ 10 slots = $49,800 per slot-year. At the source's own $2,000 withdrawn
per hit, that is **24.9 wins per slot**. At 0.5625 wins per account:

| Quantity | Source claims | Implied by source's own numbers |
|---|---|---|
| Funded accounts consumed / year | 10 | ~443 |
| Evaluations attempted / year | 33 | ~1,460 |
| Capital outlay | **$3,000** | **~$133,000** |

The capital requirement is understated by roughly **44×**. The error is treating
"20 bullets" as a one-shot portfolio when it is a consumption rate.

This also creates an internal contradiction the source cannot resolve: it
*forbids* copy-trading and mandates individual execution (§1, §6), while the
throughput its own profit figure demands is ~4 new evaluations started every
calendar day, each hand-traded through minimum-day requirements. Those two
requirements are mutually exclusive for one operator.

### c. The structure *is* EV-positive — just small

Credit where it is due. A funded account is a limited-liability call option on
your own variance: downside capped at the eval fee, upside the full payout. That
asymmetry is real, and it survives the maths. Per account, at a 90% profit split:

```
EV = 0.5625 × ($4,000 × 0.90 × 50% withdrawn) − $300 CoA
   = 0.5625 × $1,800 − $300
   = +$712
```

A genuine 10-account portfolio is therefore worth about **$7,100**, not $498,000
— a 70× overstatement, but not zero. The framework's conclusion is directionally
defensible; its magnitude is fiction.

### d. The edge is a bet on evaluation pricing, not on the strategy

Setting EV = 0 and solving for `p`:

| Real Cost of Acquisition | Break-even 1:4 hit rate |
|---|---|
| $300 (source's figure) | **7.4%** |
| $600 | 13.4% |
| $1,000 | **19.8%** |

At $300 CoA there is wide cushion below the claimed 20%. At $1,000 CoA the
break-even is 19.8% and **the entire margin of safety is gone.** So the
load-bearing number is not the 1:4 hit rate — it is the 31% pass rate, the least
verified figure in the document. The framework is not a trading edge; it is a
wager that prop-firm evaluations are underpriced.

The 31% itself is at least plausible: for a driftless walk, `P(target before
drawdown) ≈ DD/(DD+Target)` = 2000/5000 = 40%, and commissions plus slippage
push a zero-gross-expectancy system below that. But it assumes no eval time
limit, no minimum-day requirement, and no consistency rule during evaluation.

### e. Consistency rules can zero the whole thing, and are never mentioned

A $4,000 hit on a $50k account makes one day equal **100% of total account
profit**. Firms that run a consistency rule typically cap the best day at 20–50%
of total profit for payout eligibility. Under a 30% cap, that $4,000 day is not
payable until total profit reaches ~$13,300 — meaning you must keep trading, with
the drawdown re-exposed, exactly when the model says to stop and withdraw. A
single-trade-to-target design is the worst possible shape for a consistency rule.

Separately: the §5 "idling protocol" — risking $150 to make $150 purely to
satisfy minimum trading days — is at many firms an explicit T&C breach
(no-purpose / gaming trades) and grounds for payout denial. This is an execution
risk, not a moral one: it determines whether the money arrives.

**Verify both rules in the specific firm's T&Cs before spending anything.** They
are cheaper to check than to discover.

### f. The 1:4 geometry may not exist at 08:30

This is what the script is built to measure. A long enters *below* the −1 SD band
and targets the VWAP centreline, so reward ≈ one SD band width. For 1:4, the stop
— placed beyond the far edge of the FVG — must be within **25% of the distance to
VWAP**:

```
FVG height + buffer  ≤  0.25 × (entry → VWAP distance)
```

At 08:30 the midnight-anchored VWAP has accumulated only ~8.5 hours of thin
overnight volume, so the bands are narrow, while news displacement makes FVGs
large. Narrow target, wide stop — the inequality frequently fails.

**Read `rejected · no 1:4 geometry` against `trades taken` first.** If rejections
dominate, the setup does not produce a testable sample, and the 20% claim is not
false so much as unmeasurable.

### g. Slippage lands precisely where the model is most fragile

$1,000 on NQ ($20/point) is a 50-point stop. On a CPI or NFP print, 5–20 points
of stop slippage is routine. A slipped stop does not cost one bullet, it costs
~1.4 — and with only two bullets, an account can die on a single bad fill. The
bullet model assumes losses are exactly $1,000; in the one window it trades,
they are not. The script ships `slippage = 4` (1 point), which is optimistic —
**re-run at 20 and 40 ticks.** If the result inverts, that is the answer.

### h. §6 is not a validation

1,000 trades over 365 days is ~4 per day from one setup inside a 60-minute
window, gated by FVG formation + band location + tap + reclaim + 1:4 geometry.
That frequency is not achievable under the rules as written, so the backtest
measured something looser than the document describes. And a summary of exported
trade data — by any tool — cannot detect look-ahead bias, unachievable fills, or
survivorship in the account sample. It is a restatement of the input, not
evidence.

## Part 4 — How to use the script

1. NQ1! or MNQ1!, 1m or 5m, `i_simDeath` **off**. Collect ≥ 100 closed trades
   before reading the hit rate at all; the dashboard greys it below 30.
2. Check `rejected · no 1:4 geometry`. If it is a large multiple of
   `trades taken`, stop — Part 3f applies and there is nothing to measure.
3. Compare the measured hit rate to 7.4% (break-even at $300 CoA) and to 19.8%
   (break-even at $1,000 CoA), not to the asserted 20%.
4. Re-run at `slippage` 20 and 40 ticks, and with `i_dispMult` at 0 / 0.5 / 1.5
   and `i_maxWait` at 10 / 20 / 40. A hit rate that only clears break-even at one
   parameter set is curve-fit, not an edge.
5. Then turn `i_simDeath` on to see single-account survival — the cost side §3
   omits.

## Part 5 — Known limitations

- One unresolved imbalance tracked per direction; a newer FVG overwrites an older
  untriggered one.
- RR is filtered using the signal-bar close as a proxy entry, but fills occur at
  the next bar's open (`process_orders_on_close = false`). On a news bar that gap
  can be large, so *realised* R is worse than *filtered* R. `Avg R per trade`
  reports the realised figure — compare the two.
- `i_fixTgt = false` follows the source's wording more literally but breaks the
  fixed $4,000 payoff the portfolio maths depends on.
- Requires volume. The dashboard shows `NO VOLUME DATA` when `Σv = 0`.
- No eval, payout, profit-split, consistency-rule or multi-account modelling.
  Those belong in a portfolio simulator, not Pine.
