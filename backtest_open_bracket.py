#!/usr/bin/env python3
"""
"Enter at the 09:30 ET open, 10-point stop, 40-point target, flat at the close"
measured on S&P 500 RTH data (SPY as the index proxy).

The 08:00 ET signal candle cannot be sourced in this environment (no futures and
no pre-market data from any reachable provider), so this script measures the
half of the system that *is* measurable: what the 10/40 bracket does from the
09:30 open, unconditionally and under every direction rule that RTH data can
express.  Direction rules that need pre-market input are left to the 15-minute
engine in backtest_es_15m.py, which runs on a real ES export.

Path resolution
---------------
Each session is walked as an ordered list of (high, low) segments: two 4-hour
segments by default, seven 1-hour segments for the sessions where the coarser
data cannot say which level came first.  A segment that touches only one level
resolves the trade.  A segment that touches both is unresolvable at that
granularity, so the trade is reported three ways -- stop first (pessimistic),
target first (optimistic), and the day's-close heuristic in between.  The truth
of any tick-level backtest lies inside the pessimistic/optimistic band.

Prices are SPY points; 1 SPY point ~= 10 ES points (see POINTS_PER_SPY).
"""

import argparse
import csv
import datetime as dt
import math
import random
from collections import defaultdict

POINTS_PER_SPY = 10.0        # ES index points per SPY point
ES_DOLLARS_PER_POINT = 50.0  # ES contract multiplier

RESOLUTIONS = ("pessimistic", "heuristic", "optimistic")


def load_sessions(path):
    sessions = {}
    with open(path) as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            sessions[r["date"]] = {
                "date": dt.date.fromisoformat(r["date"]),
                "open": float(r["open"]),
                "close": float(r["close"]),
                "segments": [(float(r["am_high"]), float(r["am_low"])),
                             (float(r["pm_high"]), float(r["pm_low"]))],
                "granularity": "4h",
            }
    return sessions


def apply_hourly(sessions, path):
    """Replace the two 4h segments with 1h segments where we have them."""
    hourly = defaultdict(list)
    try:
        fh = open(path)
    except FileNotFoundError:
        return 0
    with fh:
        for r in csv.DictReader(fh, delimiter=";"):
            hourly[r["date"]].append((r["time"], float(r["high"]), float(r["low"])))
    used = 0
    for date, bars in hourly.items():
        if date not in sessions:
            continue
        bars.sort()
        sessions[date]["segments"] = [(h, l) for _, h, l in bars]
        sessions[date]["granularity"] = "1h"
        used += 1
    return used


def apply_15m(sessions, path):
    """Split a specific 1h segment into its four 15m segments.

    Only the hour that still contains both levels needs this, so the file holds
    just those hours rather than every bar of every day.
    """
    refine = defaultdict(lambda: defaultdict(list))
    try:
        fh = open(path)
    except FileNotFoundError:
        return 0
    with fh:
        for r in csv.DictReader(fh, delimiter=";"):
            refine[r["date"]][r["hour"]].append(
                (r["time"], float(r["high"]), float(r["low"])))
    hours = ["09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]
    used = 0
    for date, per_hour in refine.items():
        s = sessions.get(date)
        if s is None or s["granularity"] != "1h":
            continue
        segments = []
        for idx, hour in enumerate(hours):
            if hour in per_hour:
                for _, h, l in sorted(per_hour[hour]):
                    segments.append((h, l))
            else:
                segments.append(s["segments"][idx])
        sessions[date]["segments"] = segments
        sessions[date]["granularity"] = "1h+15m"
        used += 1
    return used


def resolve(session, direction, stop_pts, target_pts, resolution):
    """(outcome, pnl_es_points, was_ambiguous) for one session, gross of costs."""
    entry = session["open"]
    stop_spy = stop_pts / POINTS_PER_SPY
    target_spy = target_pts / POINTS_PER_SPY
    if direction > 0:
        target_level, stop_level = entry + target_spy, entry - stop_spy
    else:
        target_level, stop_level = entry - target_spy, entry + stop_spy

    for high, low in session["segments"]:
        if direction > 0:
            hit_target, hit_stop = high >= target_level, low <= stop_level
        else:
            hit_target, hit_stop = low <= target_level, high >= stop_level
        if hit_target and hit_stop:
            if resolution == "pessimistic":
                first = "stop"
            elif resolution == "optimistic":
                first = "target"
            else:
                # Price ended the day somewhere; the excursion away from that
                # end point is the more likely one to have come first.
                closed_up = session["close"] >= session["open"]
                first = ("stop" if closed_up else "target") if direction > 0 else \
                        ("stop" if not closed_up else "target")
            return (first, target_pts if first == "target" else -stop_pts, True)
        if hit_target:
            return ("target", target_pts, False)
        if hit_stop:
            return ("stop", -stop_pts, False)

    close_pnl = (session["close"] - entry) * direction * POINTS_PER_SPY
    return ("eod", close_pnl, False)


def prev_map(sessions):
    ordered = sorted(sessions.values(), key=lambda s: s["date"])
    for prev, cur in zip(ordered, ordered[1:]):
        cur["prev_close"] = prev["close"]
        cur["prev_dir"] = 1 if prev["close"] >= prev["open"] else -1
    return [s for s in ordered if "prev_close" in s]


SIGNALS = {
    "always_long":  lambda s: 1,
    "always_short": lambda s: -1,
    "gap":          lambda s: 1 if s["open"] >= s["prev_close"] else -1,
    "gap_inverse":  lambda s: -1 if s["open"] >= s["prev_close"] else 1,
    "prev_day":     lambda s: s["prev_dir"],
    "perfect":      lambda s: 1 if s["close"] >= s["open"] else -1,
}


def run(sessions, signal, stop_pts, target_pts, cost_pts, resolution):
    out = []
    for s in sessions:
        d = signal(s)
        outcome, pnl, amb = resolve(s, d, stop_pts, target_pts, resolution)
        out.append({"date": s["date"], "dir": d, "outcome": outcome,
                    "pnl": pnl - cost_pts, "ambiguous": amb})
    return out


def stats(trades):
    n = len(trades)
    counts = defaultdict(int)
    for t in trades:
        counts[t["outcome"]] += 1
    total = sum(t["pnl"] for t in trades)
    eq = peak = mdd = 0.0
    for t in trades:
        eq += t["pnl"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    gw = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gl = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    return {
        "n": n,
        "target_pct": 100 * counts["target"] / n,
        "stop_pct": 100 * counts["stop"] / n,
        "eod_pct": 100 * counts["eod"] / n,
        "win_pct": 100 * sum(1 for t in trades if t["pnl"] > 0) / n,
        "expectancy": total / n,
        "dollars": total * ES_DOLLARS_PER_POINT,
        "max_dd": mdd * ES_DOLLARS_PER_POINT,
        "pf": (gw / gl) if gl else float("inf"),
        "amb_pct": 100 * sum(t["ambiguous"] for t in trades) / n,
    }


def confidence(trades, dollars, iterations=4000, seed=7):
    """Bootstrap CI for expectancy: is the edge distinguishable from zero?"""
    pnl = [t["pnl"] for t in trades]
    n = len(pnl)
    mean = sum(pnl) / n
    var = sum((x - mean) ** 2 for x in pnl) / (n - 1)
    se = math.sqrt(var / n)
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(pnl, k=n)) / n for _ in range(iterations))
    lo = means[int(0.025 * iterations)]
    hi = means[int(0.975 * iterations)]
    return {"mean": mean, "t": mean / se if se else 0.0, "lo": lo, "hi": hi,
            "lo$": lo * dollars * n, "hi$": hi * dollars * n}


HEADER = (f"{'signal':<13}{'n':>5}{'TP%':>7}{'SL%':>7}{'EOD%':>7}{'win%':>7}"
          f"{'E[pts]':>9}{'net $/1ct':>12}{'maxDD $':>10}{'PF':>7}")


def fmt(name, s):
    return (f"{name:<13}{s['n']:>5}{s['target_pct']:>7.1f}{s['stop_pct']:>7.1f}"
            f"{s['eod_pct']:>7.1f}{s['win_pct']:>7.1f}{s['expectancy']:>9.2f}"
            f"{s['dollars']:>12,.0f}{s['max_dd']:>10,.0f}{s['pf']:>7.2f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sessions", default="data/spy_rth_sessions.csv")
    p.add_argument("--hourly", default="data/spy_hourly_ambiguous.csv")
    p.add_argument("--refine", default="data/spy_15m_refine.csv")
    p.add_argument("--stop", type=float, default=10.0, help="ES points")
    p.add_argument("--target", type=float, default=40.0, help="ES points")
    p.add_argument("--cost", type=float, default=0.5,
                   help="round-turn commission + slippage, ES points")
    args = p.parse_args()

    raw = load_sessions(args.sessions)
    refined = apply_hourly(raw, args.hourly)
    refined15 = apply_15m(raw, args.refine)
    sessions = prev_map(raw)

    print(f"SPY RTH sessions (S&P proxy): {len(sessions)} days "
          f"{sessions[0]['date']} -> {sessions[-1]['date']}")
    print(f"Path resolution: 4h segments; {refined} sessions refined to 1h, "
          f"{refined15} of those further refined to 15m on the decisive hour")
    print(f"Entry at the 09:30 open, stop {args.stop:g} / target {args.target:g} "
          f"ES points, cost {args.cost:g} pts round turn, flat at 16:00.\n")

    for resolution in RESOLUTIONS:
        print(f"--- unresolvable days counted as: {resolution.upper()} ---")
        print(HEADER)
        for name, sig in SIGNALS.items():
            print(fmt(name, stats(run(sessions, sig, args.stop, args.target,
                                      args.cost, resolution))))
        print()

    for name in ("always_long", "always_short", "gap"):
        s = stats(run(sessions, SIGNALS[name], args.stop, args.target,
                      args.cost, "pessimistic"))
        print(f"still unresolvable at this granularity, {name}: {s['amb_pct']:.1f}% of days")
    print()

    print("--- gap signal by calendar year (heuristic) ---")
    print(HEADER)
    by_year = defaultdict(list)
    for t in run(sessions, SIGNALS["gap"], args.stop, args.target, args.cost, "heuristic"):
        by_year[t["date"].year].append(t)
    for y in sorted(by_year):
        print(fmt(str(y), stats(by_year[y])))
    print()

    be = 100 * (args.stop + args.cost) / (args.stop + args.target)
    print(f"R:R 1:{args.target/args.stop:g} -- the target must be hit first on "
          f"{be:.1f}% of trades just to break even (ignoring end-of-day exits).\n")

    print("--- is the edge distinguishable from zero? (heuristic, "
          "bootstrap 95% CI on expectancy) ---")
    label = "95% CI, pts/trade"
    print(f"{'signal':<13}{'E[pts]':>9}{'t':>7}{label:>22}{'95% CI, total $/1ct':>26}")
    for name, sig in SIGNALS.items():
        c = confidence(run(sessions, sig, args.stop, args.target, args.cost,
                           "heuristic"), ES_DOLLARS_PER_POINT)
        ci = f"{c['lo']:+.2f} to {c['hi']:+.2f}"
        ci_d = f"{c['lo$']:+,.0f} to {c['hi$']:+,.0f}"
        print(f"{name:<13}{c['mean']:>9.2f}{c['t']:>7.2f}{ci:>22}{ci_d:>26}")
    print()

    targets = [15, 20, 25, 30, 40, 50]
    stops = [5, 10, 15, 20, 25, 30]
    corner = "stop \\ target"
    for name in ("gap", "always_long"):
        print(f"--- stop/target sensitivity, {name}, heuristic "
              f"(E[pts] per trade, net of cost) ---")
        print(f"{corner:<14}" + "".join(f"{t:>9}" for t in targets))
        for stop in stops:
            row = f"{stop:<14}"
            for target in targets:
                s = stats(run(sessions, SIGNALS[name], stop, target,
                              args.cost, "heuristic"))
                row += f"{s['expectancy']:>9.2f}"
            print(row)
        print()


if __name__ == "__main__":
    main()
