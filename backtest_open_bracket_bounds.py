#!/usr/bin/env python3
"""
Bounds analysis for "enter at the 09:30 ET open, 10-point stop / 40-point target".

Why bounds:  a daily bar tells us whether the target and/or the stop were touched,
but not in which order.  Instead of guessing, every ambiguous day (both levels
touched) is resolved three ways:

    pessimistic  -- stop first  (worst case for the trader)
    heuristic    -- the move opposite to the day's close is assumed to have come
                    first (an up-closing day dipped before it rallied)
    optimistic   -- target first (best case for the trader)

The true result of any real intraday backtest must lie between the pessimistic
and the optimistic column.  If a setup is unprofitable in the optimistic column
it cannot be rescued by finer data.

Instrument: SPY RTH daily bars used as the S&P 500 proxy.  SPY trades at ~1/10th
of the index, so 1 SPY point ~= 10 ES points (see POINTS_PER_SPY).
"""

import argparse
import csv
import datetime as dt
from collections import defaultdict

POINTS_PER_SPY = 10.0     # ES index points per SPY point
ES_DOLLARS_PER_POINT = 50.0

RESOLUTIONS = ("pessimistic", "heuristic", "optimistic")


def load(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            rows.append({
                "date": dt.date.fromisoformat(r["datetime"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
            })
    rows.sort(key=lambda r: r["date"])
    for prev, cur in zip(rows, rows[1:]):
        cur["prev_close"] = prev["close"]
        cur["prev_dir"] = 1 if prev["close"] >= prev["open"] else -1
    return [r for r in rows if "prev_close" in r]


def resolve(bar, direction, stop_pts, target_pts, resolution):
    """Return (outcome, pnl_in_es_points) for one day, gross of costs."""
    entry = bar["open"]
    stop_spy = stop_pts / POINTS_PER_SPY
    target_spy = target_pts / POINTS_PER_SPY

    if direction > 0:
        hit_target = bar["high"] >= entry + target_spy
        hit_stop = bar["low"] <= entry - stop_spy
    else:
        hit_target = bar["low"] <= entry - target_spy
        hit_stop = bar["high"] >= entry + stop_spy

    if hit_target and hit_stop:
        if resolution == "pessimistic":
            first = "stop"
        elif resolution == "optimistic":
            first = "target"
        else:
            # The day's close tells us where price ended, so the opposite
            # excursion is the more likely one to have happened first.
            closed_up = bar["close"] >= bar["open"]
            if direction > 0:
                first = "stop" if closed_up else "target"
            else:
                first = "stop" if not closed_up else "target"
        return ("target" if first == "target" else "stop",
                target_pts if first == "target" else -stop_pts)

    if hit_target:
        return ("target", target_pts)
    if hit_stop:
        return ("stop", -stop_pts)

    close_pnl = (bar["close"] - entry) * direction * POINTS_PER_SPY
    return ("eod", close_pnl)


SIGNALS = {
    "always_long":  lambda b: 1,
    "always_short": lambda b: -1,
    "gap":          lambda b: 1 if b["open"] >= b["prev_close"] else -1,
    "gap_inverse":  lambda b: -1 if b["open"] >= b["prev_close"] else 1,
    "prev_day":     lambda b: b["prev_dir"],
    "perfect":      lambda b: 1 if b["close"] >= b["open"] else -1,
}


def run(bars, signal, stop_pts, target_pts, cost_pts, resolution):
    trades = []
    for b in bars:
        d = signal(b)
        outcome, pnl = resolve(b, d, stop_pts, target_pts, resolution)
        trades.append({
            "date": b["date"], "dir": d, "outcome": outcome,
            "pnl": pnl - cost_pts,
            "ambiguous": ambiguous(b, d, stop_pts, target_pts),
        })
    return trades


def ambiguous(bar, direction, stop_pts, target_pts):
    entry = bar["open"]
    s, t = stop_pts / POINTS_PER_SPY, target_pts / POINTS_PER_SPY
    if direction > 0:
        return bar["high"] >= entry + t and bar["low"] <= entry - s
    return bar["low"] <= entry - t and bar["high"] >= entry + s


def stats(trades):
    n = len(trades)
    if not n:
        return {}
    wins = [t for t in trades if t["pnl"] > 0]
    total = sum(t["pnl"] for t in trades)
    eq, peak, mdd = 0.0, 0.0, 0.0
    for t in trades:
        eq += t["pnl"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    counts = defaultdict(int)
    for t in trades:
        counts[t["outcome"]] += 1
    gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    return {
        "n": n,
        "target_pct": 100 * counts["target"] / n,
        "stop_pct": 100 * counts["stop"] / n,
        "eod_pct": 100 * counts["eod"] / n,
        "win_pct": 100 * len(wins) / n,
        "expectancy": total / n,
        "total": total,
        "dollars": total * ES_DOLLARS_PER_POINT,
        "max_dd": mdd * ES_DOLLARS_PER_POINT,
        "pf": (gross_win / gross_loss) if gross_loss else float("inf"),
        "ambiguous_pct": 100 * sum(t["ambiguous"] for t in trades) / n,
    }


def fmt(name, s):
    return (f"{name:<14} {s['n']:>5} {s['target_pct']:>7.1f} {s['stop_pct']:>7.1f} "
            f"{s['eod_pct']:>6.1f} {s['win_pct']:>7.1f} {s['expectancy']:>9.2f} "
            f"{s['dollars']:>11,.0f} {s['max_dd']:>10,.0f} {s['pf']:>6.2f}")


HEADER = (f"{'signal':<14} {'n':>5} {'TP%':>7} {'SL%':>7} {'EOD%':>6} "
          f"{'win%':>7} {'E[pts]':>9} {'net $/1ct':>11} {'maxDD $':>10} {'PF':>6}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/spy_daily_rth.csv")
    p.add_argument("--stop", type=float, default=10.0, help="ES points")
    p.add_argument("--target", type=float, default=40.0, help="ES points")
    p.add_argument("--cost", type=float, default=0.5,
                   help="round-turn cost in ES points (commission + slippage)")
    args = p.parse_args()

    bars = load(args.data)
    print(f"SPY RTH daily bars as S&P proxy: {len(bars)} sessions "
          f"{bars[0]['date']} -> {bars[-1]['date']}")
    print(f"Entry at the 09:30 open, stop {args.stop:g} ES pts, target "
          f"{args.target:g} ES pts, cost {args.cost:g} pts round turn, "
          f"flat at the 16:00 close.\n")

    for resolution in RESOLUTIONS:
        print(f"--- ambiguous days resolved: {resolution.upper()} ---")
        print(HEADER)
        for name, sig in SIGNALS.items():
            trades = run(bars, sig, args.stop, args.target, args.cost, resolution)
            print(fmt(name, stats(trades)))
        print()

    amb = stats(run(bars, SIGNALS["always_long"], args.stop, args.target,
                    args.cost, "pessimistic"))["ambiguous_pct"]
    print(f"Days where both the stop and the target were touched (order unknown "
          f"from a daily bar): {amb:.1f}%\n")

    print("--- per calendar year, gap signal, heuristic resolution ---")
    print(f"{'year':<14} {'n':>5} {'TP%':>7} {'SL%':>7} {'EOD%':>6} {'win%':>7} "
          f"{'E[pts]':>9} {'net $/1ct':>11} {'maxDD $':>10} {'PF':>6}")
    by_year = defaultdict(list)
    for t in run(bars, SIGNALS["gap"], args.stop, args.target, args.cost, "heuristic"):
        by_year[t["date"].year].append(t)
    for year in sorted(by_year):
        print(fmt(str(year), stats(by_year[year])))
    print()

    print("--- break-even target hit-rate required at this R:R ---")
    rr = args.target / args.stop
    be = 100 * (args.stop + args.cost) / (args.stop + args.target)
    print(f"R:R = 1:{rr:g}; ignoring end-of-day exits, the target must be hit "
          f"first on at least {be:.1f}% of trades to break even.")


if __name__ == "__main__":
    main()
