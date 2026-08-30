#!/usr/bin/env python3
"""
Two questions the headline backtest cannot answer on its own, on real ES 15m data:

  1. does the 08:00 ET candle predict the session's direction at all, separately
     from whatever the 10/40 bracket does with it?
  2. is there any stop/target pair that makes the signal pay?

Run after backtest_es_15m.py, on the same export.
"""

import argparse
import datetime as dt
import importlib.util
import math
import statistics
from collections import defaultdict

spec = importlib.util.spec_from_file_location("engine", "backtest_es_15m.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--cost", type=float, default=0.5)
    p.add_argument("--tz-shift", type=int, default=0)
    args = p.parse_args()

    bars = engine.load_bars(args.csv, args.tz_shift)
    days = engine.build_days(bars, dt.time(8, 0), dt.time(9, 30), dt.time(15, 45))
    print(f"{len(days)} sessions, {days[0]['date']} -> {days[-1]['date']}\n")

    # ---- 1. signal quality, independent of the bracket -------------------
    agree = 0
    signed_move = []
    mfe, mae, first_bar_stop = [], [], 0
    for d in days:
        sig = engine.signal_direction(d)
        entry = d["entry"]["open"]
        close = d["path"][-1]["close"]
        move = (close - entry) * sig
        signed_move.append(move)
        agree += move >= 0
        hi = max(b["high"] for b in d["path"])
        lo = min(b["low"] for b in d["path"])
        mfe.append((hi - entry) if sig > 0 else (entry - lo))
        mae.append((entry - lo) if sig > 0 else (hi - entry))
        b0 = d["path"][0]
        if (b0["low"] <= entry - 10) if sig > 0 else (b0["high"] >= entry + 10):
            first_bar_stop += 1

    n = len(days)
    mean = statistics.mean(signed_move)
    se = statistics.stdev(signed_move) / math.sqrt(n)
    # one-proportion z-test of the agreement rate against a coin flip
    p_hat = agree / n
    z = (p_hat - 0.5) / math.sqrt(0.25 / n)
    print("--- 1. does the 08:00 candle predict the session? ---")
    print(f"signal agrees with the 09:30-to-close direction : {100*p_hat:.1f}% "
          f"of {n} sessions (z = {z:+.2f} vs a coin flip)")
    print(f"mean move in the signal's direction             : {mean:+.2f} pts "
          f"(t = {mean/se:+.2f})")
    print(f"median favourable excursion                     : "
          f"{statistics.median(mfe):.1f} pts")
    print(f"median adverse excursion                        : "
          f"{statistics.median(mae):.1f} pts")
    print(f"trades already stopped out in the 09:30 bar     : "
          f"{100*first_bar_stop/n:.1f}%  (10-pt stop)\n")

    # ---- 2. does any bracket size pay? -----------------------------------
    stops = [5, 10, 15, 20, 25, 30, 40]
    targets = [10, 15, 20, 25, 30, 40, 50, 60]
    print("--- 2. expectancy in ES points per trade, net of cost, "
          "as specified (08:00 signal, 09:30 entry) ---")
    print(f"{'stop / target':<15}" + "".join(f"{t:>8}" for t in targets))
    best = None
    for stop in stops:
        row = f"{stop:<15}"
        for target in targets:
            trades = []
            for d in days:
                sig = engine.signal_direction(d)
                outcome, pnl, _ = engine.resolve(d, sig, stop, target,
                                                 "heuristic", "open")
                if outcome != "no-data":
                    trades.append(pnl - args.cost)
            e = statistics.mean(trades)
            row += f"{e:>8.2f}"
            if best is None or e > best[0]:
                best = (e, stop, target, trades)
        print(row)

    e, stop, target, trades = best
    se = statistics.stdev(trades) / math.sqrt(len(trades))
    print(f"\nbest cell: stop {stop} / target {target}, E = {e:+.2f} pts/trade, "
          f"t = {e/se:+.2f} -- and it is the best of "
          f"{len(stops)*len(targets)} tried, so treat it as noise unless "
          f"t clears about 3.")


if __name__ == "__main__":
    main()
