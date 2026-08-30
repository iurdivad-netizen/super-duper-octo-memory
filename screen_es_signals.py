#!/usr/bin/env python3
"""
Do any of these signals predict the session's direction at all?

No bracket, no stop, no target -- just: the signal says up or down, and the
session goes up or down. A signal that cannot beat a coin flip here cannot be
rescued by entry timing or position management, which is the trap the rest of
this study kept falling into.

Every candidate is computable strictly before 09:30 ET except the two marked
"post-open", which are listed separately because they need the first RTH
candle. Outcomes:

    close    sign of (16:00 close - 09:30 open)          -- did the day end my way
    noon     sign of (12:00 open - 09:30 open)           -- did the morning go my way
    first20  did price travel +20 or -20 from the open first, from the signal's
             point of view (this is the bracket-relevant one)

Read the z column, not the hit rate. With ~230 sessions a hit rate needs to
reach about 56.5% to clear two standard errors, and ~12 candidates are tested
against 3 outcomes, so treat |z| under 3 as noise.
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

RTH_OPEN, RTH_LAST = dt.time(9, 30), dt.time(15, 45)


def build_sessions(bars):
    by_date = defaultdict(list)
    for b in bars:
        by_date[b["ts"].date()].append(b)

    sessions = []
    for date in sorted(by_date):
        day = by_date[date]
        rth = [b for b in day if RTH_OPEN <= b["ts"].time() <= RTH_LAST]
        if not rth or rth[0]["ts"].time() != RTH_OPEN:
            continue
        overnight = [b for b in day if b["ts"].time() < RTH_OPEN]
        sessions.append({
            "date": date, "rth": rth, "overnight": overnight,
            "bar": {b["ts"].time(): b for b in day},
        })

    for i, s in enumerate(sessions):
        s["prev"] = sessions[i - 1] if i else None
        s["prev3"] = sessions[i - 3] if i >= 3 else None
    return sessions


def at(s, hh, mm):
    return s["bar"].get(dt.time(hh, mm))


# ---------------------------------------------------------------- signals --
def sig_0800(s):
    b = at(s, 8, 0)
    return None if b is None else (1 if b["close"] >= b["open"] else -1)


def sig_premarket_drift(s):
    a, b = at(s, 8, 0), at(s, 9, 15)
    return None if (a is None or b is None) else (1 if b["close"] >= a["open"] else -1)


def sig_gap(s):
    if not s["prev"]:
        return None
    return 1 if s["rth"][0]["open"] >= s["prev"]["rth"][-1]["close"] else -1


def sig_overnight_position(s):
    on = s["overnight"]
    if not on:
        return None
    hi, lo = max(b["high"] for b in on), min(b["low"] for b in on)
    if hi == lo:
        return None
    return 1 if s["rth"][0]["open"] >= (hi + lo) / 2 else -1


def sig_overnight_momentum(s):
    """did the overnight high come after the overnight low"""
    on = s["overnight"]
    if not on:
        return None
    hi_i = max(range(len(on)), key=lambda i: on[i]["high"])
    lo_i = min(range(len(on)), key=lambda i: on[i]["low"])
    return 1 if hi_i > lo_i else -1


def sig_prev_day(s):
    if not s["prev"]:
        return None
    p = s["prev"]["rth"]
    return 1 if p[-1]["close"] >= p[0]["open"] else -1


def sig_prev_close_in_range(s):
    if not s["prev"]:
        return None
    p = s["prev"]["rth"]
    hi, lo = max(b["high"] for b in p), min(b["low"] for b in p)
    if hi == lo:
        return None
    return 1 if p[-1]["close"] >= (hi + lo) / 2 else -1


def sig_momentum_3d(s):
    if not s["prev3"]:
        return None
    return (1 if s["prev"]["rth"][-1]["close"] >= s["prev3"]["rth"][-1]["close"]
            else -1)


def sig_prior_range_break(s):
    """open outside yesterday's RTH range; no trade when inside it"""
    if not s["prev"]:
        return None
    p = s["prev"]["rth"]
    hi, lo = max(b["high"] for b in p), min(b["low"] for b in p)
    o = s["rth"][0]["open"]
    if o > hi:
        return 1
    if o < lo:
        return -1
    return None


def sig_overnight_vwap(s):
    on = s["overnight"]
    if not on:
        return None
    ref = statistics.mean(b["close"] for b in on)
    return 1 if s["rth"][0]["open"] >= ref else -1


def sig_0800_and_gap(s):
    """the 08:00 candle, but only when the gap agrees with it"""
    a, b = sig_0800(s), sig_gap(s)
    return a if (a is not None and a == b) else None


def sig_0800_big(s):
    """the 08:00 candle, but only when it is a wide one (top third by range)"""
    b = at(s, 8, 0)
    return None if b is None else (1 if b["close"] >= b["open"] else -1)


def sig_opening_candle(s):
    b = at(s, 9, 30)
    return None if b is None else (1 if b["close"] >= b["open"] else -1)


def sig_opening_drive(s):
    """09:30 candle direction, only when it closes in the top/bottom third"""
    b = at(s, 9, 30)
    if b is None or b["high"] == b["low"]:
        return None
    pos = (b["close"] - b["low"]) / (b["high"] - b["low"])
    if pos >= 2 / 3:
        return 1
    if pos <= 1 / 3:
        return -1
    return None


# (label, function, time the outcome is measured from). A signal must never be
# scored against a window that contains its own move, so anything read off the
# 09:30 candle is scored from the 09:45 open -- the first price you could
# actually trade once that candle has closed.
PRE_OPEN = [
    ("08:00 candle", sig_0800, RTH_OPEN),
    ("08:00 wide only", sig_0800_big, RTH_OPEN),
    ("08:00 + gap agree", sig_0800_and_gap, RTH_OPEN),
    ("08:00-09:30 drift", sig_premarket_drift, RTH_OPEN),
    ("overnight gap", sig_gap, RTH_OPEN),
    ("open vs ON mid", sig_overnight_position, RTH_OPEN),
    ("overnight momentum", sig_overnight_momentum, RTH_OPEN),
    ("open vs ON mean", sig_overnight_vwap, RTH_OPEN),
    ("prev day direction", sig_prev_day, RTH_OPEN),
    ("prev close in range", sig_prev_close_in_range, RTH_OPEN),
    ("3-day momentum", sig_momentum_3d, RTH_OPEN),
    ("prior range break", sig_prior_range_break, RTH_OPEN),
]
POST_OPEN = [
    ("09:30 candle", sig_opening_candle, dt.time(9, 45)),
    ("09:30 drive", sig_opening_drive, dt.time(9, 45)),
]


# --------------------------------------------------------------- outcomes --
def outcome_close(s, entry_time=RTH_OPEN):
    entry = next(b for b in s["rth"] if b["ts"].time() == entry_time)
    return s["rth"][-1]["close"] - entry["open"]


def outcome_noon(s, entry_time=RTH_OPEN):
    entry = next(b for b in s["rth"] if b["ts"].time() == entry_time)
    noon = next((b for b in s["rth"] if b["ts"].time() == dt.time(12, 0)), None)
    return None if noon is None else noon["open"] - entry["open"]


def outcome_first20(s, entry_time=RTH_OPEN, dist=20.0):
    """+1 if price travelled +dist before -dist, -1 the other way, else None"""
    path = [b for b in s["rth"] if b["ts"].time() >= entry_time]
    entry = path[0]["open"]
    for b in path:
        up, down = b["high"] >= entry + dist, b["low"] <= entry - dist
        if up and down:
            return None          # same bar, undecidable at 15m
        if up:
            return 1
        if down:
            return -1
    return None


def evaluate(sessions, signal, outcome, big_only=False, entry_time=RTH_OPEN):
    hits, moves = 0, []
    for s in sessions:
        d = signal(s)
        if d is None:
            continue
        if big_only:
            b = at(s, 8, 0)
            if b is None:
                continue
            rng = b["high"] - b["low"]
            if rng < BIG_THRESHOLD:
                continue
        o = outcome(s, entry_time)
        if o is None or o == 0:
            continue
        if isinstance(o, int) and abs(o) == 1 and outcome is outcome_first20:
            hits += (o == d)
            moves.append(1.0 if o == d else -1.0)
        else:
            hits += ((o > 0) == (d > 0))
            moves.append(o * d)
    n = len(moves)
    if n < 30:
        return None
    hit = hits / n
    z = (hit - 0.5) / math.sqrt(0.25 / n)
    mean = statistics.mean(moves)
    t = mean / (statistics.stdev(moves) / math.sqrt(n))
    return {"n": n, "hit": 100 * hit, "z": z, "mean": mean, "t": t}


def split_hits(sessions, signal, outcome, big_only=False, entry_time=RTH_OPEN):
    half = len(sessions) // 2
    a = evaluate(sessions[:half], signal, outcome, big_only, entry_time)
    b = evaluate(sessions[half:], signal, outcome, big_only, entry_time)
    return (a["hit"] if a else float("nan"), b["hit"] if b else float("nan"))


BIG_THRESHOLD = 0.0


def main():
    global BIG_THRESHOLD
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--tz-shift", type=int, default=0)
    args = p.parse_args()

    bars = engine.load_bars(args.csv, args.tz_shift)
    sessions = build_sessions(bars)
    ranges = sorted(at(s, 8, 0)["high"] - at(s, 8, 0)["low"]
                    for s in sessions if at(s, 8, 0))
    BIG_THRESHOLD = ranges[int(len(ranges) * 2 / 3)]

    print(f"{len(sessions)} sessions, {sessions[0]['date']} -> {sessions[-1]['date']}")
    print("outcomes are measured from 09:30 for pre-open signals and from 09:45 "
          "for signals\nread off the 09:30 candle, so no signal is scored "
          "against its own move")
    print(f"a hit rate must reach ~56.5% to clear 2 SE at this sample size; "
          f"'wide' 08:00 candle means range >= {BIG_THRESHOLD:.2f} pts\n")

    outcomes = [("close", outcome_close), ("noon", outcome_noon),
                ("first20", outcome_first20)]
    for title, group in (("computable before 09:30", PRE_OPEN),
                         ("needs the 09:30 candle (post-open)", POST_OPEN)):
        print(f"=== {title} ===")
        head = f"{'signal':<21}{'n':>5}"
        for name, _ in outcomes:
            head += f"{name + ' hit%':>13}{'z':>7}"
        print(head + f"{'1st half':>10}{'2nd half':>10}")
        for label, fn, et in group:
            big = label == "08:00 wide only"
            base = evaluate(sessions, fn, outcome_close, big, et)
            if base is None:
                continue
            row = f"{label:<21}{base['n']:>5}"
            for _, ofn in outcomes:
                r = evaluate(sessions, fn, ofn, big, et)
                row += (f"{r['hit']:>13.1f}{r['z']:>+7.2f}" if r
                        else f"{'-':>13}{'-':>7}")
            h1, h2 = split_hits(sessions, fn, outcome_close, big, et)
            row += f"{h1:>10.1f}{h2:>10.1f}"
            print(row)
        print()


if __name__ == "__main__":
    main()
