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

## Part 3d — The window is Chicago time, and that changes the answer

Slide 10 reads *"Step to the market at 8:30 AM EST **(Open)**"*. Two things
say that "8:30" is **Chicago** time, i.e. the 09:30 ET cash open:

1. The deck calls it **"(Open)"**. The NASDAQ open is 09:30 ET = 08:30 CT.
   (Earlier notes framed 08:30 as the US data-release window — that was an
   inference added here, not something the deck says.)
2. `data/mnq1_1m_tradingview.csv` carries the creator's own `New York VWAP`
   column, and it **resets at 01:00 ET** = midnight CT. The charting
   environment is on Chicago time, so both the deck's "Midnight EST" anchor
   and its "8:30 AM EST" window are CT labelled as EST — and they are
   mutually consistent under that reading.

So the deck's intended window is **09:30–10:30 ET**. Re-running there:

| Window (ET) | n | tgt | hit | 95% CI (hit) | avg R | 95% CI (avg R) | net |
|---|---|---|---|---|---|---|---|
| 0830–0930 premarket | 13 | 3 | 23.1% | [8.2, 50.3] | +0.578 | [−0.38, +1.63] | +$7,510 |
| **0930–1030 the open** | **1** | **0** | — | — | −0.239 | — | −$239 |
| 0930–1100 open +90m | 2 | 0 | 0.0% | [0.0, 65.8] | −0.818 | [−0.99, −0.65] | −$1,636 |
| **0930–1600 full RTH** | **29** | **10** | **34.5%** | [19.9, 52.7] | **+0.691** | [−0.03, +1.43] | +$20,030 |
| 1800–1700 all session | 72 | 22 | 30.6% | [21.1, 42.0] | +0.302 | [−0.14, +0.77] | +$21,723 |

**Under the deck's own window, correctly interpreted, the setup fires once in
17 days.** Twenty bullets would take ~340 trading days.

### Why: the 1:4 filter and the opening bell are incompatible

This is structural, and the per-hour geometry stats rest on 60–90 triggers an
hour, so they are far more robust than the trade counts:

| Hour ET | triggers | median stop | median R:R | share ≥ 1:4 |
|---|---|---|---|---|
| 08:00 (premarket) | 88 | 18.2 pt | 4.38 | **55.2%** |
| 09:00 | 84 | 24.5 pt | 3.74 | 46.4% |
| **10:00 (post-bell)** | **69** | **30.2 pt** | **2.14** | **7.7%** |
| 13:00 | 74 | 20.2 pt | 6.84 | 81.8% |
| 15:00 | 76 | 23.0 pt | 5.94 | 100.0% |

1:4 requires the stop to sit within 25% of the distance to VWAP. The stop
spans the displacement candle, and opening displacement is the largest of the
day — 30–41 pt against a target only ~1 SD away. So **the geometry objection
retracted in Part 3b for 08:30 ET turns out to be valid at the open.** The
1:4 filter wants a small displacement far from value, which is a quiet-hours
characteristic, not an opening-bell one.

### Three readings, three different answers

| Reading | Support | Result |
|---|---|---|
| A — 08:30 ET premarket | none textually; contradicts "(Open)" | n=13, hit 23.1%, avg R +0.578 |
| B — 08:30 CT = 09:30–10:30 ET | **strongest**: "(Open)" + the 01:00 ET VWAP reset | **n=1 — cannot run** |
| C — arrive at the open, trade the session (09:30–16:00) | consistent with B's timezone, looser on duration | n=29, hit 34.5%, **avg R +0.691** |

Reading C performs best and is the only one that is both timezone-consistent
and operable. Its avg R CI still has a lower bound of −0.03, so no edge is
established — but it is the version worth testing on a longer series.

The deck is therefore ambiguous on its single most consequential parameter,
and the interpretation that matches its own wording most literally (B) is the
one that cannot produce the 20 bullets its payoff model requires.

## Part 3e — Sample doubled to 32 days: the edge does not replicate

`data/mnq1_1m_tradingview.csv` now merges two contiguous MNQ1! 1-minute
exports, **2026-08-02 → 2026-09-15, 43,920 bars, 32 trading days**. Parts
3b–3d were formed on the later block only (Aug 23 – Sep 15), so **Aug 2–21 is
a genuine out-of-sample period.**

### Out-of-sample result (fixed 4R target, 1 pt/side slippage)

| Window | period | n | hit | avg R | 95% CI (avg R) | net |
|---|---|---|---|---|---|---|
| 0830–0930 premkt | **NEW Aug 2–21** | 10 | 20.0% | **+0.103** | [−1.03, +1.29] | +$1,033 |
| | prior Aug 23+ | 13 | 23.1% | +0.578 | [−0.37, +1.61] | +$7,510 |
| | combined | 23 | 21.7% | +0.371 | [−0.36, +1.14] | +$8,543 |
| 0930–1600 RTH | **NEW Aug 2–21** | 34 | 11.8% | **−0.029** | [−0.52, +0.54] | −$987 |
| | prior Aug 23+ | 29 | 34.5% | +0.691 | [−0.02, +1.43] | +$20,030 |
| | combined | 63 | 22.2% | +0.302 | [−0.13, +0.77] | +$19,043 |
| all session | **NEW Aug 2–21** | 64 | 23.4% | **−0.050** | [−0.45, +0.40] | −$3,180 |
| | prior Aug 23+ | 72 | 30.6% | +0.302 | [−0.14, +0.75] | +$21,723 |
| | combined | **136** | 27.2% | **+0.136** | **[−0.17, +0.46]** | +$18,543 |

**On data not used to form the earlier conclusions, avg R is +0.10, −0.03 and
−0.05.** The apparent edge was confined to Aug 23 – Sep 15 and did not carry.

Every estimate fell as the sample grew: premarket +0.578 → +0.371, RTH +0.691
→ +0.302, all-session +0.302 → +0.136. That monotone decay across three
independent windows is the signature of small-sample luck, not of an edge
being measured more precisely.

At n=136 the all-session result is **avg R +0.136, CI [−0.17, +0.46],
P(avg R ≤ 0) = 19.9%** — no edge established. Quartiles by date:

| quartile | dates | n | avg R | sum R |
|---|---|---|---|---|
| 1 | Aug 3 – Aug 12 | 34 | −0.231 | −7.86 |
| 2 | Aug 12 – Aug 25 | 34 | +0.277 | +9.43 |
| **3** | **Aug 26 – Sep 7** | 34 | **+0.561** | **+19.06** |
| 4 | Sep 8 – Sep 15 | 34 | −0.061 | −2.08 |

All of the profit is one fortnight. Q1 and Q4 are negative.

Note the two metrics still disagree and the money one wins: the combined hit
rate is 27.2%, CI [20.4%, 35.2%], nominally above the 19.8% worst-case
break-even — but avg R is ~0 because realised payoffs are not a clean 4:1
once slippage and forced exits are counted. Hit rate flatters it; P&L does not.

### The geometry finding is now solid, and it indicts the deck's window

Per-hour geometry rests on 116–159 triggers an hour, so this is structural:

| Hour ET | triggers | median stop | share ≥ 1:4 | n | avg R |
|---|---|---|---|---|---|
| 08:00 premarket | 159 | 20.2 pt | 50.9% | 20 | +0.034 |
| **09:00 (open)** | 156 | 27.2 pt | 32.7% | 11 | −0.149 |
| **10:00 (post-bell)** | 116 | **32.5 pt** | **21.1%** | 3 | −0.280 |
| 13:00 | 149 | 19.2 pt | **86.4%** | 20 | −0.145 |
| 14:00 | 148 | 16.0 pt | **85.0%** | 21 | +0.038 |
| 15:00 | 159 | 18.5 pt | **86.2%** | 14 | +0.197 |

A strict 09:30–10:30 gives **n=2 in 32 days**, median stop 48.2 pt, 7.1% of
triggers clearing 1:4 — 20 bullets would take ~320 trading days. The deck's
own window, read correctly as Chicago time (Part 3d), cannot produce its own
payoff model.

And the 1:4 filter points where the deck never looks: the quiet 13:00–15:00
ET hours offer 1:4 on 85–86% of triggers versus 21% after the bell. Even
there, avg R is ≈ 0.

### Verdict on the execution layer

Across 32 trading days, 136 trades and every window tested, **no edge is
demonstrated.** The setup is mechanically well-defined and the 1:4 geometry
exists in the quiet hours, but realised expectancy is indistinguishable from
zero out of sample. Combined with Parts 3a–3d — the slide-8 double count, the
non-independent bullets, the best-day consistency caps, and a stated window
that cannot fire — nothing in the deck survives contact with its own data.

Getting to a defensible answer needs n ≈ 200–400 *per window* (Part 3c), i.e.
roughly 1–2 years of 1-minute data, not 32 days.

## Part 3f — 47 days, n=220, three sequential blocks: no edge

`data/mnq1_1m_tradingview.csv` now merges three contiguous MNQ1! 1-minute
exports: **2026-07-12 → 2026-09-15, 64,620 bars, 47 trading days.** The three
blocks were supplied in reverse chronological order, so each earlier block is
a clean out-of-sample test of conclusions already drawn from the later ones.

### avg R by block (fixed 4R target, 1 pt/side slippage)

| Window | Jul 12–31 | Aug 2–21 | Aug 23–Sep 15 | ALL |
|---|---|---|---|---|
| 0830–0930 premkt | **−0.377** | +0.103 | +0.578 | +0.178 (n=31) |
| 0930–1600 RTH | +0.105 | **−0.029** | +0.691 | +0.226 (n=103) |
| 1300–1600 afternoon | **−0.120** | +0.041 | +0.644 | +0.153 (n=68) |
| 1800–1700 all session | **−0.060** | **−0.050** | +0.302 | +0.061 (n=220) |

**Only the Aug 23 – Sep 15 block is positive, in every window.** That block is
exactly the data Parts 3b–3d were built on. The two earlier blocks are zero to
negative throughout. One favourable three-week stretch produced the entire
apparent edge.

### Full-sample verdict

| Window | n | hit | 95% CI (hit) | avg R | 95% CI (avg R) | P(avg R ≤ 0) |
|---|---|---|---|---|---|---|
| 0830–0930 premkt | 31 | 16.1% | [7.1, 32.6] | +0.178 | [−0.38, +0.79] | 28.6% |
| 0930–1030 the open | **4** | — | — | +0.710 | [−0.59, +2.57] | 25.5% |
| 0930–1600 RTH | 103 | 21.4% | [14.5, 30.2] | +0.226 | [−0.11, +0.58] | 9.7% |
| 1300–1600 afternoon | 68 | 17.6% | [10.4, 28.4] | +0.153 | [−0.24, +0.56] | 23.3% |
| **1800–1700 all session** | **220** | **24.1%** | **[18.9, 30.2]** | **+0.061** | **[−0.17, +0.30]** | **31.0%** |

Note the hit-rate metric has now stopped flattering it too: at n=136 the
all-session CI was [20.4%, 35.2%], clearing the 19.8% worst-case break-even.
At n=220 it is **[18.9%, 30.2%]** — the lower bound has fallen *below*
break-even as data accumulated.

### Abundant 1:4 geometry does not mean edge — a prior suggestion was wrong

Part 3e observed that 13:00–15:00 ET clears 1:4 on 85–86% of triggers and
suggested that window was "the thing worth testing". **With 47 days it is
refuted.** Geometry availability and expectancy are unrelated:

| Hour ET | triggers | median stop | share ≥ 1:4 | n | avg R | sum R |
|---|---|---|---|---|---|---|
| 06:00 | 222 | 14.0 pt | 59.3% | 21 | −0.455 | **−9.56** |
| 07:00 | 206 | 20.8 pt | 38.7% | 18 | −0.662 | **−11.91** |
| 08:00 premarket | 229 | 22.0 pt | 51.4% | 28 | +0.035 | +0.98 |
| 09:00 (open) | 228 | 34.8 pt | 31.1% | 17 | +0.153 | +2.60 |
| 10:00 (post-bell) | 198 | **39.8 pt** | **19.5%** | 5 | −0.185 | −0.92 |
| 13:00 | 225 | 20.2 pt | **83.3%** | 31 | −0.147 | −4.54 |
| 14:00 | 234 | 18.0 pt | **78.4%** | 26 | −0.035 | −0.91 |
| 15:00 | 227 | 22.5 pt | **82.6%** | 26 | −0.156 | −4.05 |

The three hours with the *best* 1:4 availability (13:00–15:00, 78–83%) are all
**negative**. The 06:00–07:00 hours combine decent availability with the worst
expectancy in the day (−21.5 R combined). Whether a 1:4 target is reachable
says nothing about whether it is reached.

The strict open window remains structurally unusable: **n=4 in 47 days**,
median stop 39.8 pt post-bell, 19.5% of triggers clearing 1:4.

### Conclusion on the execution layer

47 trading days, 220 trades, three sequential out-of-sample blocks, every
window tested: **avg R +0.061, P(avg R ≤ 0) = 31%. No edge.** The setup is
well-specified and the geometry is real; the expectancy is not. Nothing
remains of the deck's $498,000, its "$20,000 week", or the 20% hit rate its
bullet arithmetic depends on — and that arithmetic was already broken on its
own terms (Parts 3a–3d).

## Part 3g — Anchor sweep, entry mechanics, and a correction

### Correction: the n=220 headline was a biased subsample

Parts 3b–3f used TradingView's supplied `New York VWAP` column. That column is
**empty on 30.5% of bars (19,740 of 64,620) — the entire 18:00–00:00 ET globex
evening.** Those bars were silently skipped, so the n=220 / avg R +0.061
result covered only the part of the session TradingView had populated.

With the VWAP recomputed over **all** bars, every anchor is **negative**:

| VWAP anchor | n | hit | avg R | 95% CI | P(≤0) | Jul | Aug1 | Aug2 |
|---|---|---|---|---|---|---|---|---|
| **18:00 ET globex open** | 424 | 18.6% | **−0.180** | **[−0.34, −0.02]** | 99% | −0.18 | −0.26 | −0.11 |
| 00:00 ET midnight NY | 384 | 20.3% | −0.103 | [−0.27, +0.07] | 89% | −0.08 | −0.15 | −0.09 |
| 01:00 ET midnight CT (deck) | 378 | 20.6% | **−0.082** | [−0.25, +0.09] | 84% | −0.11 | −0.18 | +0.02 |
| 09:30 ET cash open | 514 | 18.3% | **−0.187** | **[−0.34, −0.04]** | 99% | −0.19 | −0.14 | −0.22 |
| TV column (30% of bars missing) | 220 | 24.1% | +0.061 | [−0.17, +0.31] | 31% | −0.06 | −0.05 | +0.30 |

**Answer to "is 18:00 an improvement": no — it is the worst anchor tested**,
with a CI that excludes zero on the negative side and all three
out-of-sample blocks negative. The deck's own 01:00 ET (midnight CT) anchor is
the least bad. None is positive. The earlier "expectancy ≈ zero" verdict was
optimistic; corrected, it is negative.

### The entry timing observation was right, and it is the key diagnosis

In reclaim mode price starts *below* the gap and the trigger is
`close > gap top`. To close above the top, price must rally through the
**entire** gap — so **at the moment of entry the imbalance is fully filled and
no longer exists.** The entry is at the far edge of the displacement with the
stop back at the swing low, which is why median stops were 18–40 pt.

Waiting for a **retest** of the reclaimed level instead (limit at the gap edge,
stop just beyond the gap) fixes exactly that. Measured, all-session, 18:00
anchor, fixed 4R:

| Entry mechanic | n | hit | median stop | **GROSS avg R** | NET avg R |
|---|---|---|---|---|---|
| close > gap top (as implemented) | 424 | 18.6% | 18.2 pt | **−0.074** | −0.180 |
| **RETEST gap top, stop beyond gap** | 866 | **23.8%** | **3.0 pt** | **+0.178** | **−0.199** |

**Before costs the retest entry turns a no-edge signal into a positive one**
(−0.074 → +0.178 avg R). The observation identified a real defect and the fix
genuinely improves signal quality.

It still loses, for a different reason: the retest stop sits 3.0 points away,
and transaction costs are then **73.5% of the risk unit.**

### Costs, not signal quality, are what kill it

Cost per R depends only on stop width — it is invariant to position size:

```
cost/R = 2·slip_pts/stop_pts + 2·commission/(stop_pts · point_value)
```

| Stop (pts) | cost/R at 1 pt/side + $2.04/side |
|---|---|
| 3.0 | **73.5%** |
| 8 | 28.3% |
| 11.5 | 19.2% |
| 15.8 | 14.0% |
| 20.8 | 10.6% |

On NQ the stop must be ≥ ~12–15 points before costs fall under 15% of R. The
deck's tight-FVG entries do not produce stops that wide, and its
"$1,000 risk per bullet" sizing forces 6–12 contracts on a small stop, so
slippage and commission scale straight into the risk unit.

Forcing a ≥12 pt stop does produce the only positive cell found:
n=54, hit 27.8%, gross +0.286, **net +0.237**, P(≤0) = 18%, blocks
+0.28 / −0.03 / +0.32. **It is not evidence.** Several hundred cells were
tested this session (≈5 anchors × 9 entry mechanics × 5 windows × 8 stop
filters × target and slippage modes); dozens of cells at P(≤0)≈0.2 are
expected from noise alone. Its neighbours are non-monotonic (min-stop 6 gives
gross −0.232 against min-stop 0's +0.178) and the min-stop 15 cell has two of
three blocks at −0.92 and −0.55. That is a fitted cell, not a stable effect.

### Where the execution layer actually stands

- The signal has **no edge as the deck specifies the entry** (−0.074 gross).
- Fixing the entry to a retest gives a **real gross edge (+0.178)** that is
  entirely consumed by costs at the stop widths the pattern produces.
- No VWAP anchor rescues it; 18:00 is the worst of the four.
- The only viable direction would be a variant whose natural stop is 12–20 pt
  *and* retains the retest's gross edge. Nothing tested does both, and
  establishing one would need a fresh out-of-sample period, not more cells
  from these 47 days.

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
