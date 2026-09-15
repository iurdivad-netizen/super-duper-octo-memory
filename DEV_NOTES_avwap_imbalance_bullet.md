# AVWAP Imbalance 1:4 — "The Prop Firm Loophole"

**File:** `avwap_imbalance_bullet_strategy.pine` (Pine Script v6)
**Source:** `Prop_Firm_Extraction_Blueprint.pdf` — "The Prop Firm Loophole: A
Mathematical Framework for Extraction", a 14-slide deck by "Garland Trader",
generated in Gemini Notebook. Image-only PDF, no text layer.
**Intended market:** NQ futures, **1-minute** chart (slide 10), 08:30 ET.

> Previously drafted from a NotebookLM text summary of this deck. The PDF
> changed two substantive things: the imbalance polarity (Part 2a) and the
> document's purpose (Part 3a). Both are corrected below.

---

## Part 1 — What is codeable

| Slide | Content | Testable in Pine? |
|-------|---------|-------------------|
| 1–4 | Pitch; "variance exhaustion"; old-vs-new comparison table | No |
| 5 | Zero-edge anchor: 100k-trade MC, 1:1.5 R/R → ~40% WR | No |
| 6 | Funnel: $3,000 → 30 evals → 30% pass → 10 funded, CoA $300 | No |
| 7 | Bullets: 1 account = $2,000 DD = 2 × $1,000 risks → "20 independent attempts" | Partly |
| 8 | The output math: $3K → $9K–$12K in 2–3 weeks | No — and it is wrong (Part 3b) |
| 9 | Payout ladder: strike day 1, micro-risk days 2–5, withdraw 50% | No |
| **10–11** | **1-min AVWAP scalp + imbalance entry trigger** | **Yes — the script** |
| 12 | $498,000 / 1,000 trades / 365 days, "AI Verification: Claude + TradingView" | No |
| 13 | "A $20,000 Week" across Topstep / Tradeify / Blue Guardian | No |
| 14 | 12-week coaching programme, "Apply Now" | No |

## Part 2 — Mapping slides 10–11 to code

| Source rule | Implementation |
|-------------|----------------|
| "VWAP (Anchored at Midnight EST)" | Accumulators reset on the NY-hour transition to `i_anchorHr` (default 0). Not the CME 18:00 session VWAP. |
| Upper / Lower 1st SD | Volume-weighted SD: `sqrt(Σp²v/Σv − vwap²)`, `i_sdMult` default 1.0. |
| "Buy Zone: bias is strictly LONG back to VWAP" (below lower 1st SD); mirror above upper | Hard gate `longBias` / `shortBias` on the reclaim level. Rejections counted. |
| **"gap between Candle 1's low and Candle 3's high"** | See Part 2a — this is a **downward** displacement. `dnGap = low[2] > high[0]`. |
| "Aggressive move creates a gap" | Unquantified. `midRange ≥ i_dispMult × ATR(14)`, default 1.0, settable to 0. |
| "Wait for a candle to visually CLOSE above the imbalance" | `close > lRecLvl and close[1] <= lRecLvl`, confirmed bars only. |
| "Ride momentum back to the central VWAP" | `strategy.exit(limit = VWAP)`, frozen at entry by default. |
| "1:4 R/R (Risk $1K to make $4K)" | `i_minRR = 4.0`. Setups that cannot reach it are **rejected and counted**. |
| "Step to the market at 8:30 AM EST" | `i_sess` default `0830-0930`, `America/New_York` (tracks EST/EDT; a fixed EST offset drifts an hour for eight months). |
| 1-minute chart | Dashboard header flags any TF outside 1/3/5m. |
| $2,000 DD → 2 × $1,000 bullets | `i_bulletUSD`, `i_bullets`, trailing off the equity peak. `i_simDeath` off by default. |

### 2a. The imbalance polarity was wrong in the first draft

Slide 11 draws candle 1 high, candle 2 a large **down** candle, candle 3 low,
and brackets the imbalance between **candle 1's low and candle 3's high** —
then labels the setup "Buy Bias" and the trigger "close **above** the
imbalance".

That is a **downward** displacement gap, entered **long** on an upward reclaim:
an exhaustion reversal. It is *not* the conventional bullish FVG (candle 1's
high below candle 3's low) held as support, which is what the earlier draft
implemented and what nearly every published FVG script means. The two are close
to opposite signals — continuation vs. reversal — and the reversal reading is
the one that actually fits "ride momentum *back* to the central VWAP" from
below the −1 SD band.

`i_fvgMode` now selects:

- **`Reclaim (slide 11)`** — default. Long on `low[2] > high[0]`, trigger
  `close > low[2]`. Price starts *below* the gap, so there is no prior tap to
  wait for; `needTap = false`. The displacement candle is bearish, i.e. against
  the trade.
- **`Continuation (classic FVG)`** — the old behaviour, retained for comparison.
  Long on `high[2] < low[0]`, tapped then reclaimed; `needTap = true`.

Consequence for the stop, and it is a large one: in reclaim mode the gap's far
edge (`high[0]`) sits *inside* the displacement candle, above the actual swing
low, so a stop there would be run first. `i_stopBasis` defaults to the 3-candle
**sequence extreme** (`min(low[0..2])`) in reclaim mode. That stop spans the
whole displacement candle, so it is **wide** — which makes the 1:4 requirement
against a target only ~1 SD away considerably harder to satisfy than it looked
under the continuation reading. `rejected · no 1:4 geometry` measures it.

## Part 3 — What the deck gets wrong

### a. It is a lead magnet, not analysis

Slide 14: a 12-week paid coaching programme, "Guarantee: Get funded within 2
months", "Apply Now — click the link in the description". The NotebookLM text
summary stripped this entirely. Every performance figure in the deck is
marketing collateral produced by the party selling the course, which sets the
prior for slides 8, 12 and 13.

And slide 14 undercuts them directly: the **entire student body's** track record
is "over **$90,000** in personal payouts." Slide 13 claims one operator
extracted **$20,000 in a single week**; slide 12 claims **$498,000** a year. At
the advertised rate, one student would exceed the whole cohort's lifetime record
in about five weeks. Those three numbers cannot all be true.

### b. Slide 8 books the wins and never books the losses

This is the deck's central arithmetic, and the error is plain:

```
Slide 8:  20 bullets × 20% = 4 wins
          4 wins × $3,000 ("after $1K risk is covered") = $12,000 gross
          − $3,000 funnel cost                          =  $9,000 net
```

20 bullets at a 20% hit rate is 4 wins **and 16 losses**. The 16 losses are
never subtracted. Account-balance change:

```
4 × (+$4,000)  +  16 × (−$1,000)  =  $16,000 − $16,000  =  $0
```

**Exactly zero** — which is precisely what slide 5 promises when it says the
baseline strategy "works with NO expected value". Slide 8 then reports $12,000
of gross profit from it. The two slides contradict each other, and the gap is
the $16,000 of unbooked losing bullets (net of the $4,000 the slide wrongly
deducts from the winners — a win does not also cost you its risk).

The fair version is a **cash** account, since losing bullets burn the firm's
simulated capital, not yours:

| | Slide 8 | Corrected |
|---|---|---|
| Cash out (30 evals) | $3,000 | $3,000 |
| Wins | 4 | 4 |
| Withdrawn (slide 9: 50% of $4,000) | — | $8,000 |
| After a 90% profit split | — | $7,200 |
| **Net cash** | **$9,000** | **≈ $4,200** |
| Accounts left alive | (not stated) | **2 of 10** — 16 lost bullets kill 8 |

So the structure does make money, and the mechanism is real: limited liability
caps your downside at the eval fee while the upside is the full payout. A
funded account is a call option on your own variance. But the deck's own
tagline on slide 13 — *"all you need is one trade to hit to completely mitigate
your acquisition cost"* — is the tell. This is option-premium arbitrage, not a
trading edge, and it is worth roughly half what slide 8 claims per cycle.

### c. The 20 bullets are not independent

Slide 7 states "we have 20 **independent** attempts to hit this target." They
are not. Bullet 2 exists only conditional on bullet 1 having lost, and losing
both destroys the account. Modelling the buffer as resetting on a win:

```
H(2) = k/(1−k),   k = p(2−p)
p = 0.20  →  k = 0.36  →  H = 0.5625 expected wins per account, ever
```

A 64% chance an account dies before its first payout. Carried to slide 12's
$498,000 (10 slots × $49,800 ÷ $2,000 per withdrawal = 24.9 wins per slot):

| | Slide 12 | Implied |
|---|---|---|
| Funded accounts consumed/year | 10 | ~443 |
| Evaluations/year | 30 | ~1,460 (≈4/day) |
| Capital outlay | **$3,000** | **~$133,000** |

Slides 1 and 4 also *forbid* copy-trading and mandate individual execution — so
those ~4 evaluations a day are all hand-traded. Not achievable by one operator.

### d. Consistency rules block the deck's core instruction — verified

Slide 4's primary goal is "**Speed to payout; clear the buffer fast**." That is
the exact behaviour best-day consistency rules exist to prevent, and the deck
names firms that enforce them:

| Firm | Best-day cap |
|---|---|
| Topstep — Trading Combine | **50%** of profit target |
| Topstep — Express Funded | **40%** |
| Apex | 30% |
| MFFU | 40% |

A $4,000 single-trade hit is **100% of account profit**. Under Topstep's Express
Funded 40% target you need ~$10,000 total profit before that day is compliant;
under Apex's 30%, ~$13,300. Topstep does not fail you — it *raises the target*,
so you keep trading with the drawdown re-exposed. That destroys both the
"speed to payout" thesis and the CoA model, because every account now occupies
a slot far longer than slide 8's 2–3 weeks.

Worse, the **Combine itself** carries the 50% rule, so slide 6's 30% pass rate
from random 1:1.5 entries is overstated for Topstep: a random-entry run that
clears the target in a few large trades fails the consistency target on the way.

Sources: [TradeDupe](https://tradedupe.com/blog/prop-firm-consistency-rule-guide),
[PropTradingVibes](https://proptradingvibes.com/blog/topstep-consistency-rule),
[Funded Futures Family](https://www.fundedfuturesfamily.com/topstep-consistency-rule/),
[Phidias](https://phidiaspropfirm.com/education/topstep-consistency-rule).

Separately, slide 9's micro-risk "lock-in" — $150 to make $150 purely to
satisfy minimum trading days — is at many firms an explicit T&C breach
(no-purpose / gaming trades) and grounds for payout denial.

### e. Slide 13 counts unrealised balance as extracted

| Firm | Deck's wording | Amount |
|---|---|---|
| Topstep | "locked in" ×2 | $9,186 — **still in the account** |
| Tradeify | "extracted" ×4 | $16,100 |
| Blue Guardian | "payout" | $2,000 |

Headline: "Over **$20,000 extracted** in a single week." $9,186 of it was not
extracted; "locked in" means unrealised account balance, still exposed to the
drawdown and to the consistency rules above.

### f. Two more internal contradictions

- Slide 8 says **2–3 weeks** for the whole $3K→$9K cycle. Slide 3 puts the eval
  at weeks 1–4 with funding in week 5, and slide 14 guarantees funding "within
  2 months". The cycle cannot fit in 2–3 weeks by the deck's own timeline.
- Slide 9 claims the 1:1 micro-risk phase "averages to break-even over 4 days"
  and "the buffer is completely protected". A zero-edge 1:1 sequence is a
  driftless random walk with non-zero variance — not protection — and after
  commissions the drift is negative. Tight-stop micro-trades make the
  commission drag proportionally worse, not better.

### g. Where the edge actually is, and its sensitivity

Setting EV = 0 per account against acquisition cost:

| Real Cost of Acquisition | Break-even 1:4 hit rate |
|---|---|
| $300 (slide 6) | **7.4%** |
| $600 | 13.4% |
| $1,000 | **19.8%** |

At $300 there is real cushion under the asserted 20%. At $1,000 the break-even
*is* 20% and the margin is gone. The load-bearing number is therefore slide 6's
**30% pass rate**, not the trading setup — and Part 3d shows that pass rate is
optimistic at the one firm the deck names most.

The 30% is at least plausible in isolation: for a driftless walk,
`P(target before drawdown) ≈ DD/(DD+Target)` = 2000/5000 = 40%, and costs push
a zero-gross-expectancy system below that.

### h. Slide 12 is not a validation

1,000 trades over 365 days is ~4/day from one setup inside a 60-minute window,
gated by gap formation + band location + reclaim + 1:4 geometry. Not achievable
under slides 10–11 as written, so the run measured something looser. "AI
Verification: Claude + TradingView" is not verification — summarising exported
trade data cannot detect look-ahead bias, unachievable fills, or survivorship
in the account sample.

## Part 3b — Backtest result (real MNQ 1m, corrects an earlier error)

`backtest_avwap_imbalance.py` ports the Pine logic. Data:
`data/mnq1_1m_tradingview.csv`, MNQ1! 1-minute, 2026-08-23 → 2026-09-15,
23,220 bars, **17 trading days**. The export carries TradingView's own
`New York VWAP` and ±1 SD columns, so the VWAP is validated rather than
assumed (it resets at **01:00 ET** = midnight Chicago, not midnight NY; the
geometry result is identical under either anchor).

**An earlier run used ES 3m/15m as a proxy and found the 1:4 geometry
literally unavailable (0 of 23 eligible triggers, max R:R 2.61). That was
wrong.** ES is not NQ, and 3m/15m is not 1m: both changes widen the
FVG-spanning stop relative to the SD band width. On the correct instrument
and timeframe the geometry is readily available:

| | ES 3m (wrong proxy) | **MNQ 1m (correct)** |
|---|---|---|
| eligible triggers | 23 | 37 |
| median available R:R | 1.15 | **4.64** |
| max available R:R | 2.61 | **16.46** |
| share offering ≥ 1:4 | **0.0%** | **54.1%** |
| median stop width | 5.5 pt | 20.5 pt |

So Part 3f's geometry objection does **not** hold on NQ 1m. Setups exist.

### What the 17-day sample does and does not show

| Variant | n | target | stop | hit | avg R |
|---|---|---|---|---|---|
| target = VWAP, flat at 09:30 | 13 | 2 | 7 | 15.4% | +0.77 |
| **fixed 4R target, flat at 09:30** | 13 | 3 | 7 | **23.1%** | +0.58 |
| fixed 4R target, no EOD flatten | 13 | 6 | 7 | 46.2% | +0.95 |

Three reasons this cannot be used to accept the framework:

1. **The sample is too small to decide anything.** Wilson 95% CI on the
   23.1% hit rate is **[8.2%, 50.3%]**. The decision range is 7.4%–19.8%
   (Part 3g). The confidence interval *contains the entire decision range*,
   so the test cannot separate "profitable" from "break-even" from "losing".
   Bootstrap on avg R: 95% CI **[−0.38, +1.61]**, with P(avg R ≤ 0) = 12.9%.
2. **The result hinges on a rule the deck never states.** Flatten at the
   window close → 23.1% hit. Hold to stop-or-target → 46.2%. That single
   unspecified choice swings the answer by more than the margin being
   tested. In the target=VWAP variant, **82% of total R came from forced
   window-close exits**, not from targets.
3. **Slippage flips it.** Fixed 4R target: avg R +0.65 at 0 slip, +0.58 at 1
   pt/side, +0.31 at 5 pt/side, **−0.03 at 10 pt/side**. Ten points a side on
   an 08:30 CPI print is ordinary.

### The finding that does survive the small sample: throughput

Signal frequency is far less sensitive to a short window than win rate is.

- 13 qualifying trades in 17 trading days = **0.76 per day**.
- Only **8 of 17 days (47%)** produced any qualifying trade at all.
- Firing **20 bullets** sequentially therefore takes **~26 trading days
  (~5 weeks)**, not the 2–3 weeks slide 8 claims. The deck needs ~1.4
  qualifying signals a day; the setup delivers 0.76.
- Firing one signal into all 10 accounts would fix the throughput — but that
  *is* copy-trading, which slides 1, 3 and 4 explicitly forbid as the thing
  that destroys the edge.

This is a structural contradiction in the deck, not a statistical one, and it
compounds Part 3d: a 5-week cycle keeps each account exposed to the trailing
drawdown for twice as long as budgeted, and raises the real Cost of
Acquisition — which is exactly the variable that moves break-even from 7.4%
to 19.8% and erases the margin.

## Part 3c — Could not extend the sample; what the 17 days do say

**More NQ 1m data is not obtainable from this environment.** Twelve Data does
not carry futures and gates pre/post-market behind a paid plan; Alpha
Vantage's historical-month intraday endpoint is premium-only; Yahoo and every
other host probed (stooq, Databento, Polygon) are refused by the egress
policy. QQQ without premarket is useless here because RTH starts at 09:30,
*after* the deck's window.

So the sample stays at 17 trading days. To get more out of it, the same setup
mechanics were run across wider windows — which separates two questions the
deck conflates.

### Widening the window (fixed 4R target, 1 pt/side slippage)

| Window (ET) | n | tgt | hit | 95% CI (hit) | avg R | 95% CI (avg R) |
|---|---|---|---|---|---|---|
| 0830–0930 (the deck) | 13 | 3 | 23.1% | [8.2, 50.3] | +0.578 | [−0.39, +1.60] |
| 0930–1600 RTH | 29 | 10 | 34.5% | [19.9, 52.7] | +0.691 | [−0.03, +1.44] |
| **1800–1700 all session** | **72** | **22** | **30.6%** | **[21.1, 42.0]** | +0.302 | [−0.13, +0.77] |

At n=72 the hit-rate CI lower bound (21.1%) finally clears the worst-case
break-even (19.8%, Part 3g). That is the first result in this whole exercise
to clear a statistical bar — but note the two metrics disagree: **avg R's CI
still spans zero**, because realised payoffs are not a clean 4:1 once
slippage and forced exits are counted. Avg R is the decision-relevant figure,
and it remains indistinguishable from no edge.

### The 08:30 window is the worst hour in the sample

The deck's entire execution premise is that 08:30 ET is the window
("Step to the market at 8:30 AM EST"). Ranked by total R:

| Hour ET | n | hit | avg R | sum R |
|---|---|---|---|---|
| 11:00 | 5 | 20.0% | +0.901 | +4.51 |
| 09:00 | 8 | 12.5% | +0.207 | +1.66 |
| 14:00 | 10 | 10.0% | +0.154 | +1.54 |
| … | | | | |
| **08:00 (the deck)** | **10** | **10.0%** | **−0.205** | **−2.05** |
| 04:00 | 5 | 0.0% | −0.586 | −2.93 |
| 06:00 | 8 | 0.0% | −0.496 | −3.97 |

10th of 12 hours. Per-hour n is far too small to be conclusive, but it points
the **opposite way** to the deck's claim, and the deck offers no evidence for
08:30 beyond assertion. If the release window carried the edge the deck
attributes to it, this is not what it would look like.

Split-half stability (all session, n=36 each): avg R +0.474 → **+0.129**, hit
33.3% → 27.8%. Weakening, though within noise at that size.

### How much data would actually settle it

| n | 95% CI on a true 20% hit rate | width |
|---|---|---|
| 13 | [8.2%, 50.3%] | 42.1 pp |
| 72 | [11.7%, 30.4%] | 18.7 pp |
| **200** | **[15.0%, 26.1%]** | **11.0 pp** |
| 400 | [16.4%, 24.2%] | 7.8 pp |

The decision range is 12.4 pp wide (7.4%–19.8%), so **n ≈ 200 is the minimum**
for the test to distinguish profitable from break-even. At the 08:30 window's
measured 0.76 qualifying trades/day that is ~263 trading days; n=400 is
**~2.1 years** of NQ 1m.

That is the concrete ask. Anything less cannot separate this setup from noise,
and the deck presents no evidence approaching it.

## Part 4 — How to use the script

1. NQ1!/MNQ1!, **1-minute** (slide 10), `i_fvgMode` = `Reclaim (slide 11)`,
   `i_simDeath` off. Collect ≥ 100 closed trades; the dashboard greys the hit
   rate below 30.
2. Check `rejected · no 1:4 geometry`. On NQ 1m roughly 46% of eligible
   triggers are rejected for this and 54% pass (Part 3b) — so expect setups,
   not a famine. On any other instrument or timeframe re-measure: on ES 3m
   the pass rate is 0%.
3. Compare the measured rate to **7.4%** and **19.8%** (Part 3g), not to the
   asserted 20%. You need on the order of 300-400 trades before the
   confidence interval is narrower than that range; 13 trades is nowhere
   close (Part 3b).
4. Flip `i_fvgMode` to `Continuation` and compare. If continuation tests better,
   that is evidence the deck's own slide-11 geometry is not the edge.
5. Re-run at `slippage` 20 and 40 ticks. $1,000 on NQ ($20/pt) is a 50-point
   stop; 20 points of slip on an 08:30 CPI print costs ~1.4 bullets, and two
   bullets is the whole account. Shipped at 4 ticks, which is optimistic.
6. Vary `i_dispMult` (0 / 0.5 / 1.5), `i_maxWait` (10 / 20 / 40),
   `i_stopBasis`, `i_reclaim`. An edge that clears break-even at one parameter
   set is curve-fit.
7. Then `i_simDeath` on, to see single-account survival — the cost side slide 8
   omits.

## Part 5 — Known limitations

- One unresolved imbalance per direction; a newer gap overwrites an older
  untriggered one.
- RR is filtered on the signal-bar close but fills occur at the next bar's open
  (`process_orders_on_close = false`). On a news bar that gap is large, so
  realised R is worse than filtered R. `Avg R per trade` is the realised
  figure — compare the two.
- `i_fixTgt = false` follows "reversion to the central VWAP" more literally but
  breaks the fixed $4,000 payoff the portfolio maths assumes.
- Requires volume; dashboard shows `NO VOLUME DATA` when `Σv = 0`.
- No eval, payout, profit-split, consistency-rule or multi-account modelling.
  Those belong in a portfolio simulator, not Pine.
