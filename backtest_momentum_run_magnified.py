#!/usr/bin/env python3
"""Bar-magnifier probe: 15m signals, 3m intrabar path resolution.

`backtest_momentum_run.py` has to guess when a single bar's range contains both
the stop and the target. That guess is harmless at 1.5R (~1% of trades) and
decisive at 0.5R (~4.3%), where it moves the measured hit rate by 4.3 points and
the z-score against the null from -5.67 to -0.77. Any conclusion about tight
targets drawn from 15m OHLC alone is an artifact of the assumption.

This script removes the assumption. It rebuilds 15m bars from `es1_3m` so the
OHLC is exact, then resolves every fill, stop and target on the 3m sub-bars.
Residual ambiguity is 0.0% of trades.

The cost is coverage: es1_3m spans two months, so this is ~270 trades against
~3,000 for the 15m probe. Use it to check the shape of a result, not to
establish one.

Usage:
    python3 backtest_momentum_run_magnified.py
    python3 backtest_momentum_run_magnified.py --runs 2 --min-risk 30
"""
import argparse
import csv
import math
from datetime import datetime

TICK = 0.25
COST_TICKS = 3.0
SUB_PER_BAR = 5  # 3m bars per 15m bar


def build_bars(path):
    """Rebuild exact 15m bars from 3m data, keeping the sub-bars for each."""
    raw = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            raw.append((datetime.fromisoformat(r["time"]), float(r["open"]),
                        float(r["high"]), float(r["low"]), float(r["close"])))
    raw.sort(key=lambda x: x[0])

    groups, order = {}, []
    for dt, o, h, l, c in raw:
        key = (dt.date(), dt.hour, dt.minute // 15)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((o, h, l, c))

    bars, subs = [], []
    for key in order:
        g = groups[key]
        if len(g) != SUB_PER_BAR:
            continue  # incomplete bucket: the 15m OHLC would be wrong
        bars.append((g[0][0], max(x[1] for x in g), min(x[2] for x in g), g[-1][3]))
        subs.append(g)
    return bars, subs


def colour(o, c):
    return 1 if c > o else (-1 if c < o else 0)


def probe(bars, subs, n, rr, min_risk_ticks=0.0, max_hold=200):
    total = len(bars)
    runs, prev = [0] * total, 0
    for i, (o, h, l, c) in enumerate(bars):
        d = colour(o, c)
        if d == 0:
            runs[i], prev = 0, 0
        elif d == prev:
            runs[i] = runs[i - 1] + 1
        else:
            runs[i], prev = 1, d

    filled = wins = ambiguous = 0
    gross = net = 0.0
    for i in range(total - max_hold - 2):
        o, h, l, c = bars[i]
        d = colour(o, c)
        if d == 0 or runs[i] != n:
            continue
        entry = h + TICK if d > 0 else l - TICK
        stop = l - TICK if d > 0 else h + TICK
        r = abs(entry - stop)
        if r <= 0 or (min_risk_ticks and r < min_risk_ticks * TICK):
            continue
        target = entry + d * rr * r

        fill = None
        for si, (so, sh, sl, sc) in enumerate(subs[i + 1]):
            if (d > 0 and sh >= entry) or (d < 0 and sl <= entry):
                fill = (i + 1, si)
                break
        if fill is None:
            continue
        filled += 1
        bar_i, sub_i = fill

        result = None
        for j in range(bar_i, min(bar_i + max_hold, total)):
            for si, (so, sh, sl, sc) in enumerate(subs[j]):
                if j == bar_i and si < sub_i:
                    continue
                hit_stop = sl <= stop if d > 0 else sh >= stop
                hit_tgt = sh >= target if d > 0 else sl <= target
                if hit_stop and hit_tgt:
                    ambiguous += 1
                    result = -1.0
                    break
                if hit_stop:
                    result = -1.0
                    break
                if hit_tgt:
                    result = rr
                    break
            if result is not None:
                break
        if result is None:
            last = bars[min(bar_i + max_hold, total - 1)][3]
            result = d * (last - entry) / r

        if result > 0:
            wins += 1
        gross += result
        net += result - (COST_TICKS * TICK) / r

    return filled, wins, gross, net, ambiguous


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/es1_3m_tradingview.csv")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--min-risk", type=float, default=0.0)
    ap.add_argument("--rr", type=float, nargs="+",
                    default=[0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0])
    args = ap.parse_args()

    bars, subs = build_bars(args.data)
    print(f"{len(bars)} complete 15m bars rebuilt from {args.data}")
    print(f"N={args.runs}, min risk {args.min_risk:g} ticks, "
          f"{COST_TICKS:g} ticks round-trip friction\n")
    print(f"{'RR':>5s} {'n':>5s} {'BE%':>6s} {'win%':>6s} {'±1se':>5s} "
          f"{'z':>6s} {'gross':>7s} {'net':>7s} {'amb%':>5s}")

    for rr in args.rr:
        f, w, g, nt, a = probe(bars, subs, args.runs, rr, args.min_risk)
        if f < 30:
            print(f"{rr:5.2f} {f:5d}   (n<30, skipped)")
            continue
        p, be = w / f, 1.0 / (1.0 + rr)
        se = math.sqrt(p * (1 - p) / f)
        print(f"{rr:5.2f} {f:5d} {100*be:5.1f}% {100*p:5.1f}% {100*se:4.1f} "
              f"{(p-be)/se:+6.2f} {g/f:+7.3f} {nt/f:+7.3f} {100*a/f:4.1f}%")


if __name__ == "__main__":
    main()
