#!/usr/bin/env python3
"""
"Note the direction of the 08:00 candle, then trade the retest of its level in
that direction."

    the 08:00 ET 15m candle sets both the bias and a level
    price must first trade away from that level in the bias direction
    when price comes back and touches the level, enter there in the bias direction
    stop / target from the entry level; flat at the session close

"The level" is not one thing, so all four readings are tested:

    breakout  the side price broke out of -- the candle high for a bullish
              candle, its low for a bearish one (the usual meaning)
    close     the candle's close
    mid       the candle's midpoint
    far       the opposite edge -- a deeper pullback into the candle body

Entry is a limit at the level, so the fill is the level itself. The bar that
delivers the retest is a problem the same way a stop-and-target bar is: once
price has touched the level, that bar's remaining path is unknown. Trades where
the entry bar also reaches the stop are therefore reported both ways --
counted as stopped (pessimistic) and as surviving (optimistic).

    python3 backtest_es_retest.py data/es1_15m_tradingview.csv
    python3 backtest_es_retest.py data/es1_15m_tradingview.csv --level close --stop 15 --target 30
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

LEVELS = ("breakout", "close", "mid", "far")


def level_of(signal_bar, direction, kind):
    hi, lo = signal_bar["high"], signal_bar["low"]
    if kind == "breakout":
        return hi if direction > 0 else lo
    if kind == "far":
        return lo if direction > 0 else hi
    if kind == "close":
        return signal_bar["close"]
    return (hi + lo) / 2


def find_trade(day, kind, direction, entry_start, entry_end, require_hold=False):
    """Walk the session; return (entry_level, bars_after_entry, entry_bar)."""
    level = level_of(day["signal"], direction, kind)
    armed = False
    for i, bar in enumerate(day["session"]):
        t = bar["ts"].time()
        if bar["ts"] <= day["signal"]["ts"]:
            continue
        # price has to leave the level in the bias direction before a retest
        if not armed:
            if (bar["high"] > level) if direction > 0 else (bar["low"] < level):
                armed = True
            continue
        if not (entry_start <= t <= entry_end):
            continue
        touched = bar["low"] <= level if direction > 0 else bar["high"] >= level
        if touched:
            if require_hold:
                # the level has to hold: the retest candle must close back on
                # the signal's side of it, otherwise price simply went through
                held = (bar["close"] >= level if direction > 0
                        else bar["close"] <= level)
                if not held:
                    continue
            return level, day["session"][i + 1:], bar
    return None, None, None


def resolve_from(entry, path, direction, stop, target, resolution):
    """Bracket resolved from a bar-boundary entry: no intrabar assumption at
    the entry itself, only the usual one if a later bar holds both levels."""
    if direction > 0:
        t_level, s_level = entry + target, entry - stop
    else:
        t_level, s_level = entry - target, entry + stop
    for bar in path:
        if direction > 0:
            hit_t, hit_s = bar["high"] >= t_level, bar["low"] <= s_level
        else:
            hit_t, hit_s = bar["low"] <= t_level, bar["high"] >= s_level
        if hit_t and hit_s:
            if resolution == "pessimistic":
                return "stop", -stop, True
            if resolution == "optimistic":
                return "target", target, True
            up = bar["close"] >= bar["open"]
            first = ("stop" if up else "target") if direction > 0 else \
                    ("stop" if not up else "target")
            return first, (target if first == "target" else -stop), True
        if hit_t:
            return "target", target, False
        if hit_s:
            return "stop", -stop, False
    if not path:
        return "no-exit", 0.0, False
    return "eod", (path[-1]["close"] - entry) * direction, False


def resolve(level, entry_bar, rest, direction, stop, target, resolution, exit_time):
    """Outcome of the bracket, entered at `level` on `entry_bar`."""
    if direction > 0:
        t_level, s_level = level + target, level - stop
    else:
        t_level, s_level = level - target, level + stop

    # The entry bar's path after the touch is unknown: if that bar reached
    # either level, the outcome depends on an assumption whichever way it is
    # resolved, so flag it as ambiguous even when the trade runs on.
    entry_bar_stop = (entry_bar["low"] <= s_level if direction > 0
                      else entry_bar["high"] >= s_level)
    entry_bar_target = (entry_bar["high"] >= t_level if direction > 0
                        else entry_bar["low"] <= t_level)
    amb = entry_bar_stop or entry_bar_target
    if entry_bar_stop and entry_bar_target:
        if resolution == "optimistic":
            return "target", target, True
        return "stop", -stop, True
    if entry_bar_stop and resolution == "pessimistic":
        return "stop", -stop, True
    if entry_bar_target and resolution == "optimistic":
        return "target", target, True

    path = [b for b in rest if b["ts"].time() <= exit_time]
    for bar in path:
        if direction > 0:
            hit_t, hit_s = bar["high"] >= t_level, bar["low"] <= s_level
        else:
            hit_t, hit_s = bar["low"] <= t_level, bar["high"] >= s_level
        if hit_t and hit_s:
            if resolution == "pessimistic":
                return "stop", -stop, True
            if resolution == "optimistic":
                return "target", target, True
            up = bar["close"] >= bar["open"]
            first = ("stop" if up else "target") if direction > 0 else \
                    ("stop" if not up else "target")
            return first, (target if first == "target" else -stop), True
        if hit_t:
            return "target", target, amb
        if hit_s:
            return "stop", -stop, amb
    if not path:
        return "no-exit", 0.0, amb
    return "eod", (path[-1]["close"] - level) * direction, amb


def build(bars, signal_time, exit_time):
    days = defaultdict(list)
    for b in bars:
        days[b["ts"].date()].append(b)
    out = []
    for date in sorted(days):
        session = days[date]
        signal = next((b for b in session if b["ts"].time() == signal_time), None)
        if signal is None:
            continue
        if not any(b["ts"].time() == dt.time(9, 30) for b in session):
            continue          # only real RTH sessions
        out.append({"date": date, "signal": signal, "session": session})
    return out


def run(days, kind, mode, stop, target, cost, resolution, entry_start,
        entry_end, exit_time, fill="next-open", require_hold=False):
    """fill='next-open': market order at the open of the bar after the touch.
       fill='level':     resting limit at the level itself."""
    trades = []
    for day in days:
        d = 1 if day["signal"]["close"] >= day["signal"]["open"] else -1
        if mode == "invert":
            d = -d
        elif mode == "long":
            d = 1
        elif mode == "short":
            d = -1
        level, rest, entry_bar = find_trade(day, kind, d, entry_start, entry_end,
                                            require_hold)
        if level is None:
            continue
        if fill == "level":
            entry = level
            outcome, pnl, amb = resolve(level, entry_bar, rest, d, stop, target,
                                        resolution, exit_time)
        else:
            path = [b for b in rest if b["ts"].time() <= exit_time]
            if not path:
                continue
            entry = path[0]["open"]
            outcome, pnl, amb = resolve_from(entry, path, d, stop, target,
                                             resolution)
        if outcome == "no-exit":
            continue
        trades.append({"date": day["date"], "dir": d, "outcome": outcome,
                       "pnl": pnl - cost, "ambiguous": amb,
                       "slip": (level - entry) * d})
    return trades


def summarise(trades, dollars=50.0):
    n = len(trades)
    if not n:
        return None
    counts = defaultdict(int)
    for t in trades:
        counts[t["outcome"]] += 1
    p = [t["pnl"] for t in trades]
    mean = statistics.mean(p)
    se = statistics.stdev(p) / math.sqrt(n) if n > 1 else float("inf")
    eq = peak = mdd = 0.0
    for x in p:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    gw = sum(x for x in p if x > 0)
    gl = -sum(x for x in p if x < 0)
    return {"n": n, "tp": 100 * counts["target"] / n, "sl": 100 * counts["stop"] / n,
            "eod": 100 * counts["eod"] / n, "exp": mean, "t": mean / se,
            "net": sum(p) * dollars, "dd": mdd * dollars,
            "pf": gw / gl if gl else float("inf"),
            "amb": 100 * sum(t["ambiguous"] for t in trades) / n}


HEADER = (f"{'':<12}{'n':>5}{'TP%':>7}{'SL%':>7}{'EOD%':>7}{'E[pts]':>9}{'t':>7}"
          f"{'net $':>11}{'maxDD $':>10}{'PF':>7}")


def line(label, s):
    return (f"{label:<12}{s['n']:>5}{s['tp']:>7.1f}{s['sl']:>7.1f}{s['eod']:>7.1f}"
            f"{s['exp']:>9.2f}{s['t']:>7.2f}{s['net']:>11,.0f}{s['dd']:>10,.0f}"
            f"{s['pf']:>7.2f}")


def hhmm(v):
    h, m = v.split(":")
    return dt.time(int(h), int(m))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--level", choices=LEVELS + ("all",), default="all")
    p.add_argument("--stop", type=float, default=10.0)
    p.add_argument("--target", type=float, default=40.0)
    p.add_argument("--cost", type=float, default=0.5)
    p.add_argument("--signal-time", default="08:00")
    p.add_argument("--entry-start", default="09:30")
    p.add_argument("--entry-end", default="15:00")
    p.add_argument("--exit-time", default="15:45")
    p.add_argument("--fill", choices=("next-open", "level"), default="next-open",
                   help="'next-open': enter at the open of the candle after the "
                        "retest candle (realistic, no intrabar assumption). "
                        "'level': resting limit at the level itself.")
    p.add_argument("--require-hold", action="store_true",
                   help="the retest candle must close back on the signal's side "
                        "of the level, so trades where price simply went through "
                        "are skipped")
    p.add_argument("--tz-shift", type=int, default=0)
    args = p.parse_args()

    bars = engine.load_bars(args.csv, args.tz_shift)
    days = build(bars, hhmm(args.signal_time), hhmm(args.exit_time))
    es, ee, xt = (hhmm(args.entry_start), hhmm(args.entry_end), hhmm(args.exit_time))
    print(f"{len(days)} sessions with an {args.signal_time} candle, "
          f"{days[0]['date']} -> {days[-1]['date']}")
    print(f"retest entry between {args.entry_start} and {args.entry_end}, "
          f"stop {args.stop:g} / target {args.target:g}, cost {args.cost:g}, "
          f"flat after {args.exit_time}, fill = {args.fill}\n")

    kinds = LEVELS if args.level == "all" else (args.level,)
    for kind in kinds:
        print(f"=== level = {kind} ===")
        print(HEADER)
        for resolution in ("pessimistic", "heuristic", "optimistic"):
            s = summarise(run(days, kind, "signal", args.stop, args.target,
                              args.cost, resolution, es, ee, xt, args.fill,
                              args.require_hold))
            if s:
                print(line(resolution, s))
        print("  controls (heuristic) -- does the signal matter?")
        for mode, label in (("invert", "inverted"), ("long", "always long"),
                            ("short", "always short")):
            s = summarise(run(days, kind, mode, args.stop, args.target,
                              args.cost, "heuristic", es, ee, xt, args.fill,
                              args.require_hold))
            if s:
                print(line("  " + label, s))
        print()


if __name__ == "__main__":
    main()
