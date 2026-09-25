# super-duper-octo-memory

A research workbench of **TradingView Pine Script indicators and strategies** and the
**Python backtests** used to check them against real market data. Most scripts start
from a published idea: a TradingView script, a course PDF, a "prop firm" deck, or a
strategy description. Each one is implemented faithfully and then measured against a
null hypothesis.

> **The main finding so far:** none of the directional strategies tested here shows a
> repeatable edge out of sample. The one result that keeps holding up is that next-candle
> **size** (volatility) can be forecast, while next-candle **direction** cannot. Read the
> scripts as measurement tools, not as trading systems ready to run.

---

## Repository layout

```
.
├── *.pine                 # TradingView scripts (Pine v5/v6): indicators and strategy()s
├── DEV_NOTES_*.md         # One design + findings note per script (read these first)
├── *.py                   # Python backtests / probes, mostly stdlib, run from the repo root
├── tools_pinelint.py      # Static checker for common Pine v6 compile errors
└── data/                  # OHLC(V) CSV exports used by the Python scripts
```

Every major script has a matching `DEV_NOTES_<name>.md`. That note records where the
idea came from, how each rule maps to code, known bugs in the source, and the backtest
results with their caveats.

---

## Pine Script: strategies

| Script | What it trades | Notes | Status of evidence |
|---|---|---|---|
| `avwap_imbalance_bullet_strategy.pine` | NQ 1m, midnight-anchored VWAP ±1 SD, imbalance entry, 1:4 R/R ("bullet" risk model from a prop-firm deck) | `DEV_NOTES_avwap_imbalance_bullet.md` | 47 days / 220 trades, 3 sequential blocks: **no edge**. The deck's own arithmetic is shown to be wrong |
| `fair_price_reversion_strategy.pine` | NQ 1m, fades the opening displacement back to a fair-price baseline ("Prop Firm Extraction Algorithm") | `DEV_NOTES_fair_price_reversion.md` | Built with an evaluation-pass-rate harness; test plan documented |
| `es_open_direction_strategy.pine` | ES: the 08:00 ET candle sets direction, entry at the 09:30 open, 10-pt stop / 40-pt target | `DEV_NOTES_es_opening_direction.md` | 520 sessions: no direction rule is distinguishable from zero. The 10-pt stop is hit on about 73% of sessions whichever way you face |
| `momentum_run_strategy.pine` | N consecutive same-colour candles, stop-entry continuation | `DEV_NOTES_momentum_run_strategy.md` | Six tests across instruments, exits, sessions and OOS: **"end of the line"**. The entry effect is real (+0.109R) but only cancels the breakout penalty, so expectancy nets to about zero |
| `ema50_institutional_swing_strategy.pine` | 50 EMA body cross, two-bar pullback, Chandelier trail, 2R target (4h) | `DEV_NOTES_ema50_institutional_swing.md` | The source manual's win-rate claims don't hold up arithmetically. Benchmark to beat: 33.3% |
| `initial_balance_strategy.pine` | SPX/NQ Initial Balance (09:30–10:30) breakout or retest | `DEV_NOTES_initial_balance_strategy.md` | Implementation notes |
| `orb_strategy.pine` | Opening-range breakout with a rewritten SL/TP engine | `DEV_NOTES_orb_strategy.md` | Review of the original: its SL/TP was wired to a display checkbox, so exits never fired |
| `naked_poc_strategy.pine` | ES/NQ 5m, naked POCs used as **targets**, with entries on a pullback into the prior value area | `DEV_NOTES_naked_poc_strategy.md` | Companion to `naked_poc_levels.pine` |
| `value_area_reversion_strategy.pine` | Value Area Reversion Signals (VARS) converted to a strategy, 18:00 ET anchor | `DEV_NOTES_value_area_reversion_strategy.md` | All of the P&L sits in the exit engine that was added, not in the original signal |
| `no_wick_retest_strategy.pine` | Retest of levels set by no-wick candles | `DEV_NOTES_no_wick_retest_strategy.md` | `strategy()` port of the indicator |
| `xau_ema_crossover_retest_strategy.pine` | XAUUSD 15m, EMA 20/50 cross then retest of the 20 EMA, 2.5R target, 1h trend filter | `DEV_NOTES_xau_ema_crossover_retest.md` | Rule-to-code mapping |
| `nq_2080_levels_strategy.pine` | NQ breakout and retest of round-number bands (X80–X20) | none | none |
| `spx_expected_move_vix_strategy.pine` | VIX-implied SPX expected move converted to a backtestable put-credit-spread strategy | none | SPX chart only |

## Pine Script: indicators

| Script | Purpose |
|---|---|
| `candle_forecast_v2.pine` | Online-learned next-bar direction and size, with a 75/20/5 train/test/calibrate split shown on the chart (`DEV_NOTES_candle_forecast_v2.md`) |
| `next_candle_predictor.pine` | Markov-chain colour probability plus a size forecast, with a live scorecard (`DEV_NOTES_next_candle_predictor.md`) |
| `next_candle_strength_lite.pine` | Rewrite of a "candle strength" script that now forecasts bar size (`DEV_NOTES_candle_strength_lite.md`) |
| `naked_poc_levels.pine` | Session volume profile, POC/VAH/VAL, and a stack of untested POCs. Built to measure first, trade later (`DEV_NOTES_naked_poc_levels.md`) |
| `no_wick_retest.pine` | Open re-implementation of the closed-source "No Wick Retest" workflow (`DEV_NOTES_no_wick_retest.md`) |
| `stoic_range_blueprint.pine` | Consolidation-then-expansion model, taken rule by rule from the Stoic Range Blueprint PDF (`DEV_NOTES_stoic_range_blueprint.md`) |
| `stoic_sbs_golden_pocket.pine` | Older Stoic Trader system: 20/200 MA bias, swing breakout sequence, 61.8% entry, 2/3/4R targets (`DEV_NOTES_stoic_sbs_golden_pocket.md`) |
| `bb_squeeze.pine` | Bollinger Bands inside the Keltner Channel, marked only after the squeeze holds for N bars (`DEV_NOTES_bb_squeeze.md`) |
| `tick.pine` | NYSE/Nasdaq TICK breadth drawn as OHLC bars in its own pane (`DEV_NOTES_tick.md`) |
| `sp500_15min_eod_direction.pine` | Direction of the first 15/N minutes vs the end-of-day direction (`sp500_opening_range_eod_direction_indicator_notes.md`) |
| `expected_move_tastytrade.pine` | tastytrade-style expected-move bands |
| `spx_expected_move_vix.pine` | SPX expected move by timeframe from VIX, with a put-credit-spread win/loss counter |
| `spx_0dte_expected_move_bands.pine` | Historical expected-move bands for SPX 0DTE |
| `stochastic_pivot_points.pine` | Stochastic-based pivot points (NexusSignals) |
| `prev_hl_ny_lon_zone_v5.pine` | Previous high/low by period, plus NY and London session shading (v5 conversion) |
| `xau_no_trade_zone_levels.pine` | Shades the no-trade band around every round-number level |

---

## Python backtests and probes

All scripts run from the repository root with `python3 <script>.py [args]` and read from
`data/`. Most use only the standard library. The Pine replicas follow the Pine execution
model bar by bar, rather than a vectorised shortcut, so that their results can validate
the on-chart numbers.

| Script | What it measures |
|---|---|
| `backtest_es_15m.py` | ES 08:00-candle / 09:30-entry / 10-40 bracket. Bars that touch both stop and target are resolved three ways: pessimistic, heuristic, optimistic |
| `analyse_es_signal.py` | Whether the 08:00 candle predicts session direction at all, plus a stop/target sweep |
| `screen_es_signals.py` | Bracket-free screen: does any pre-open signal beat a coin flip on session direction? |
| `backtest_es_retest.py` | The retest-of-the-08:00-level variant, under four definitions of "the level" |
| `backtest_es_range_breakout.py` | The 08:00 range traded as a breakout from 09:30 (15m or 3m data) |
| `backtest_open_bracket.py` | The 10/40 bracket from the 09:30 open on SPY RTH data, under every direction rule |
| `backtest_momentum_run.py` | Momentum-run hit rate vs the random-walk null of 1/(1+RR) |
| `backtest_momentum_run_magnified.py` | The same trade, with fills resolved on 3m sub-bars so no bar is ambiguous |
| `backtest_avwap_imbalance.py` | How often the AVWAP setup offers a 1:4 geometry, and its hit rate when it does |
| `backtest_next_candle_predictor.py` | Walk-forward, strictly causal validator for `next_candle_predictor.pine` |
| `backtest_candle_forecast_v2.py` | Bar-by-bar reference implementation of `candle_forecast_v2.pine` (`--all`, `--ablate`) |
| `probe_candle_strength.py` | Scores the "candle strength" formula's direction call against the base rate |
| `tools_pinelint.py` | `python3 tools_pinelint.py file.pine`: static checks for mechanical Pine v6 errors |

## Data (`data/`)

Most files are TradingView exports. The ones the main verdicts rest on:

| File | Contents |
|---|---|
| `es1_15m_tradingview.csv` | ES1! 15m, Oct 2024 → Aug 2026 (~43k bars) |
| `es1_3m_tradingview.csv` | ES1! 3m, Jun → Aug 2026 (~20k bars), used for intrabar resolution |
| `mnq1_1m_tradingview.csv` | MNQ1! 1m with NY VWAP and SD bands, Jul → Sep 2026 (~65k bars, 47 days) |
| `es_trades_10_40.csv` | Trade log of the headline ES 10/40 run |
| `spy_rth_sessions.csv`, `spy_hourly_ambiguous.csv`, `spy_15m_refine.csv`, `spy_daily_rth.csv` | SPY RTH sessions and finer bars for the open-bracket study |
| `spy_1day.csv`, `qqq_15m.csv`, `aapl_1h.csv`, `eurusd_1h.csv`, `btcusd_1h.csv`, `xauusd_{5m,15m,1h}.csv` | Cross-instrument samples for the momentum and candle-forecast tests |

---

## Methodology used throughout

- **Benchmark against a null, not zero.** A +RR / −1R bracket on a driftless random walk
  wins 1/(1+RR) of the time (40% at 1.5R, 33.3% at 2R). A strategy has to beat that
  number after costs.
- **Show intrabar ambiguity instead of hiding it.** When a bar contains both the stop and
  the target, results are reported both pessimistically and optimistically, or resolved
  on lower-timeframe bars.
- **Keep the sample honest.** Bootstrap confidence intervals, out-of-sample blocks, and
  explicit warnings about multiple testing once a parameter grid gets large.
- **Separate the signal from the exit engine.** When a converted indicator never
  specified exits, the notes say so, because the backtest is then testing the added
  exit logic.

## Using the scripts

1. **TradingView:** open the Pine Editor, paste a `.pine` file, and add it to a chart on
   the instrument and timeframe given in its header and dev note.
2. **Python:** `python3 backtest_es_15m.py` (or any script above) from the repo root.
   Most scripts print usage in their module docstring.
3. **Lint Pine before pasting:** `python3 tools_pinelint.py some_script.pine`.

*Nothing here is financial advice. Several source claims examined in the dev notes were
shown not to hold up.*
