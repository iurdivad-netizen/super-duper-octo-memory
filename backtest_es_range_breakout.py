#!/usr/bin/env python3
"""
The 08:00 ET 15-minute candle defines a RANGE (its high and its low).
From 09:30 the range is traded as a breakout: long above the high, short below
the low, entered at the open of the bar after the one that breaks.

Runs on either timeframe. On a 3-minute file the 08:00 candle is rebuilt from
its five 3m bars, so the same range is used whichever file is supplied — the
only thing that changes is how finely the breakout and the bracket are resolved.

Two ways to handle a session that is already outside the range at 09:30, which
is common because the 08:00 candle is narrow:

    fresh   only a break that happens after 09:30 counts; if price is already
            outside at the open, the session is skipped
    state   if price is already outside at 09:30, enter immediately in that
            direction; otherwise wait for the break

and two direction rules:

    range   whichever side breaks (the range is the signal)
    colour  only take the break that agrees with the 08:00 candle's colour

    python3 backtest_es_range_breakout.py data/es1_3m_tradingview.csv
    python3 backtest_es_range_breakout.py data/es1_15m_tradingview.csv --stop 20 --target 25
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

SIGNAL_START = dt.time(8, 0)
SIGNAL_END = dt.time(8, 15)      # exclusive: the 15m candle covers 08:00-08:15


def build_sessions(bars):
    by_date = defaultdict(list)
    for b in bars:
        by_date[b["ts"].date()].append(b)
    out = []
    for date in sorted(by_date):
        day = sorted(by_date[date], key=lambda b: b["ts"])
        sig = [b for b in day if SIGNAL_START <= b["ts"].time() < SIGNAL_END]
        if not sig or sig[0]["ts"].time() != SIGNAL_START:
            continue
        if not any(b["ts"].time() == dt.time(9, 30) for b in day):
            continue
        out.append({
            "date": date,
            "high": max(b["high"] for b in sig),
            "low": min(b["low"] for b in sig),
            "colour": 1 if sig[-1]["close"] >= sig[0]["open"] else -1,
            "bars": day,
        })
    return out


def find_entry(s, entry_start, entry_end, mode, direction_rule):
    hi, lo = s["high"], s["low"]
    path = [b for b in s["bars"] if entry_start <= b["ts"].time() <= entry_end]
    if not path:
        return None
    first = path[0]
    outside = 1 if first["open"] > hi else (-1 if first["open"] < lo else 0)
    if outside and mode == "fresh":
        return None                      # already broken before the open
    if outside and mode == "state":
        d = outside
        if direction_rule == "colour" and d != s["colour"]:
            return None
        return d, first["open"], [b for b in s["bars"] if b["ts"] >= first["ts"]]

    for i, bar in enumerate(path):
        up, down = bar["high"] > hi, bar["low"] < lo
        if up and down:                  # both sides in one bar: unresolvable
            return "ambiguous", None, None
        if up or down:
            d = 1 if up else -1
            if direction_rule == "colour" and d != s["colour"]:
                return None
            rest = [b for b in s["bars"] if b["ts"] > bar["ts"]]
            if not rest:
                return None
            return d, rest[0]["open"], rest
    return None


def resolve(entry, path, d, stop, target, resolution, exit_time):
    t_level = entry + target * d
    s_level = entry - stop * d
    bars = [b for b in path if b["ts"].time() <= exit_time]
    for bar in bars:
        if d > 0:
            hit_t, hit_s = bar["high"] >= t_level, bar["low"] <= s_level
        else:
            hit_t, hit_s = bar["low"] <= t_level, bar["high"] >= s_level
        if hit_t and hit_s:
            if resolution == "pessimistic":
                return "stop", -stop, True
            if resolution == "optimistic":
                return "target", target, True
            up = bar["close"] >= bar["open"]
            first = ("stop" if up else "target") if d > 0 else \
                    ("stop" if not up else "target")
            return first, (target if first == "target" else -stop), True
        if hit_t:
            return "target", target, False
        if hit_s:
            return "stop", -stop, False
    if not bars:
        return "no-exit", 0.0, False
    return "eod", (bars[-1]["close"] - entry) * d, False


def run(sessions, stop, target, cost, resolution, mode, direction_rule,
        entry_start, entry_end, exit_time, invert=False):
    trades, skipped, amb = [], 0, 0
    for s in sessions:
        found = find_entry(s, entry_start, entry_end, mode, direction_rule)
        if found is None:
            skipped += 1
            continue
        if found[0] == "ambiguous":
            amb += 1
            continue
        d, entry, path = found
        if invert:
            d = -d
        outcome, pnl, a = resolve(entry, path, d, stop, target, resolution, exit_time)
        if outcome == "no-exit":
            continue
        trades.append({"date": s["date"], "dir": d, "outcome": outcome,
                       "pnl": pnl - cost, "ambiguous": a})
    return trades, skipped, amb


def summarise(trades, dollars=50.0):
    n = len(trades)
    if n < 5:
        return None
    c = defaultdict(int)
    for t in trades:
        c[t["outcome"]] += 1
    p = [t["pnl"] for t in trades]
    m = statistics.mean(p)
    se = statistics.stdev(p) / math.sqrt(n)
    eq = peak = mdd = 0.0
    for x in p:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    gw = sum(x for x in p if x > 0)
    gl = -sum(x for x in p if x < 0)
    return {"n": n, "tp": 100 * c["target"] / n, "sl": 100 * c["stop"] / n,
            "eod": 100 * c["eod"] / n, "E": m, "t": m / se, "net": sum(p) * dollars,
            "dd": mdd * dollars, "pf": gw / gl if gl else float("inf"),
            "amb": 100 * sum(t["ambiguous"] for t in trades) / n}


HEADER = (f"{'':<22}{'n':>5}{'TP%':>7}{'SL%':>7}{'EOD%':>7}{'E[pts]':>9}{'t':>7}"
          f"{'net $':>11}{'maxDD $':>10}{'PF':>6}{'amb%':>7}")


def line(label, s):
    return (f"{label:<22}{s['n']:>5}{s['tp']:>7.1f}{s['sl']:>7.1f}{s['eod']:>7.1f}"
            f"{s['E']:>+9.2f}{s['t']:>+7.2f}{s['net']:>11,.0f}{s['dd']:>10,.0f}"
            f"{s['pf']:>6.2f}{s['amb']:>7.1f}")


def hhmm(v):
    h, m = v.split(":")
    return dt.time(int(h), int(m))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--stop", type=float, default=10.0)
    p.add_argument("--target", type=float, default=40.0)
    p.add_argument("--cost", type=float, default=0.5)
    p.add_argument("--entry-start", default="09:30")
    p.add_argument("--entry-end", default="15:00")
    p.add_argument("--exit-time", default="15:57")
    p.add_argument("--tz-shift", type=int, default=0)
    args = p.parse_args()

    bars = engine.load_bars(args.csv, args.tz_shift)
    sessions = build_sessions(bars)
    es, ee, xt = hhmm(args.entry_start), hhmm(args.entry_end), hhmm(args.exit_time)
    rng = [s["high"] - s["low"] for s in sessions]
    print(f"{args.csv}: {len(bars):,} bars, {len(sessions)} sessions "
          f"{sessions[0]['date']} -> {sessions[-1]['date']}")
    print(f"08:00 15m range: median {statistics.median(rng):.2f} pts")
    print(f"breakout from {args.entry_start}, stop {args.stop:g} / target "
          f"{args.target:g}, cost {args.cost:g}, flat after {args.exit_time}\n")

    for mode in ("fresh", "state"):
        for rule in ("range", "colour"):
            print(f"=== {mode} break, direction = {rule} ===")
            print(HEADER)
            for resolution in ("pessimistic", "heuristic", "optimistic"):
                tr, sk, am = run(sessions, args.stop, args.target, args.cost,
                                 resolution, mode, rule, es, ee, xt)
                s = summarise(tr)
                if s:
                    print(line(resolution, s))
            tr, sk, am = run(sessions, args.stop, args.target, args.cost,
                             "heuristic", mode, rule, es, ee, xt, invert=True)
            s = summarise(tr)
            if s:
                print(line("  inverted", s))
            print(f"  sessions with no trade: {sk}   both sides in one bar: {am}\n")


if __name__ == "__main__":
    main()
