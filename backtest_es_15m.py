#!/usr/bin/env python3
"""
The strategy exactly as specified, on real 15-minute ES data.

    the 08:00 ET candle decides the direction (close vs open)
    enter at the 09:30 ET open in that direction
    10-point stop, 40-point target
    flat at the session close if neither is hit

Because 15-minute bars cannot say which level a bar touched first, every bar
that contains both the stop and the target is reported three ways: stop first
(pessimistic), target first (optimistic), and the bar's-close heuristic in
between.  The count of such bars is printed so the ambiguity is visible rather
than hidden inside a single number.

Input: a CSV of 15-minute ES bars.  A TradingView chart export works as is
(Chart -> ... -> Export chart data), and so does any file with columns for
timestamp, open, high, low, close.  Header names are matched case-insensitively
against: time/date/datetime/timestamp, open, high, low, close.

    python3 backtest_es_15m.py ES_15m.csv
    python3 backtest_es_15m.py ES_15m.csv --stop 10 --target 40 --signal-time 08:00
    python3 backtest_es_15m.py ES_15m.csv --tz-shift -1   # data stamped in CT

Timestamps are used as given; --tz-shift adds whole hours if the export is not
in exchange time (New York).  Point values are the instrument's own points, so
run it on ES for ES points; --dollars-per-point sets the contract multiplier
($50 for ES, $5 for MES).
"""

import argparse
import csv
import datetime as dt
from collections import defaultdict

RESOLUTIONS = ("pessimistic", "heuristic", "optimistic")

TIME_KEYS = ("time", "datetime", "date", "timestamp")


def parse_timestamp(value):
    v = value.strip().strip('"')
    if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
        return dt.datetime.fromtimestamp(int(v), tz=dt.timezone.utc).replace(tzinfo=None)
    v = v.replace("T", " ").replace("Z", "")
    # strip a trailing UTC offset (+HH:MM / -HH:MM) so the wall-clock time is
    # used as given -- a TradingView export is already stamped in exchange time
    head, tail = v[:10], v[10:]
    for sign in ("+", "-"):
        if sign in tail:
            tail = tail.split(sign)[0]
    v = head + tail
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return dt.datetime.strptime(v.strip(), fmt)
        except ValueError:
            continue
    raise SystemExit(f"unrecognised timestamp: {value!r}")


def sniff(path):
    with open(path, newline="") as fh:
        sample = fh.read(8192)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def load_bars(path, tz_shift):
    delim = sniff(path)
    bars = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delim)
        if not reader.fieldnames:
            raise SystemExit(f"{path}: no header row")
        cols = {(name or "").strip().lower().lstrip("﻿"): name
                for name in reader.fieldnames}
        tkey = next((cols[k] for k in TIME_KEYS if k in cols), None)
        missing = [c for c in ("open", "high", "low", "close") if c not in cols]
        if tkey is None or missing:
            raise SystemExit(f"{path}: need a time column and OHLC; "
                             f"found {reader.fieldnames}")
        for row in reader:
            if not row.get(tkey):
                continue
            try:
                o, h, l, c = (float(row[cols[k]]) for k in ("open", "high", "low", "close"))
            except (TypeError, ValueError):
                continue
            bars.append({"ts": parse_timestamp(row[tkey]) + dt.timedelta(hours=tz_shift),
                         "open": o, "high": h, "low": l, "close": c})
    bars.sort(key=lambda b: b["ts"])
    return bars


def hhmm(value):
    h, m = value.split(":")
    return dt.time(int(h), int(m))


def build_days(bars, signal_time, entry_time, exit_time):
    days = defaultdict(list)
    for b in bars:
        days[b["ts"].date()].append(b)
    out = []
    for date in sorted(days):
        session = days[date]
        signal = next((b for b in session if b["ts"].time() == signal_time), None)
        entry = next((b for b in session if b["ts"].time() == entry_time), None)
        if signal is None or entry is None:
            continue
        path = [b for b in session
                if entry_time <= b["ts"].time() <= exit_time]
        out.append({"date": date, "signal": signal, "entry": entry, "path": path})
    return out


def signal_direction(day):
    return 1 if day["signal"]["close"] >= day["signal"]["open"] else -1


def resolve(day, d, stop, target, resolution, entry_mode):
    entry_bar = day["entry"]
    entry = entry_bar["open"] if entry_mode == "open" else entry_bar["close"]
    if d > 0:
        t_level, s_level = entry + target, entry - stop
    else:
        t_level, s_level = entry - target, entry + stop

    path = day["path"] if entry_mode == "open" else day["path"][1:]
    for bar in path:
        if d > 0:
            hit_t, hit_s = bar["high"] >= t_level, bar["low"] <= s_level
        else:
            hit_t, hit_s = bar["low"] <= t_level, bar["high"] >= s_level
        if hit_t and hit_s:
            if resolution == "pessimistic":
                first = "stop"
            elif resolution == "optimistic":
                first = "target"
            else:
                up = bar["close"] >= bar["open"]
                first = ("stop" if up else "target") if d > 0 else \
                        ("stop" if not up else "target")
            return (first, target if first == "target" else -stop, True)
        if hit_t:
            return ("target", target, False)
        if hit_s:
            return ("stop", -stop, False)
    if not path:
        return ("no-data", 0.0, False)
    return ("eod", (path[-1]["close"] - entry) * d, False)


def stats(trades, dollars):
    n = len(trades)
    if not n:
        return None
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
    return {"n": n,
            "tp": 100 * counts["target"] / n,
            "sl": 100 * counts["stop"] / n,
            "eod": 100 * counts["eod"] / n,
            "win": 100 * sum(1 for t in trades if t["pnl"] > 0) / n,
            "exp": total / n,
            "net": total * dollars,
            "dd": mdd * dollars,
            "pf": gw / gl if gl else float("inf"),
            "amb": 100 * sum(t["ambiguous"] for t in trades) / n}


HEADER = (f"{'':<14}{'n':>5}{'TP%':>7}{'SL%':>7}{'EOD%':>7}{'win%':>7}"
          f"{'E[pts]':>9}{'net $':>12}{'maxDD $':>10}{'PF':>7}")


def line(label, s):
    return (f"{label:<14}{s['n']:>5}{s['tp']:>7.1f}{s['sl']:>7.1f}{s['eod']:>7.1f}"
            f"{s['win']:>7.1f}{s['exp']:>9.2f}{s['net']:>12,.0f}{s['dd']:>10,.0f}"
            f"{s['pf']:>7.2f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv", help="15-minute OHLC export (TradingView format works)")
    p.add_argument("--stop", type=float, default=10.0)
    p.add_argument("--target", type=float, default=40.0)
    p.add_argument("--cost", type=float, default=0.5,
                   help="round-turn commission + slippage in points")
    p.add_argument("--signal-time", default="08:00", help="signal candle open, ET")
    p.add_argument("--entry-time", default="09:30", help="entry candle open, ET")
    p.add_argument("--exit-time", default="15:45", help="last bar held, ET")
    p.add_argument("--entry-mode", choices=("open", "close"), default="open",
                   help="'open': fill at the entry candle's open (as specified). "
                        "'close': wait for that candle to close, then enter")
    p.add_argument("--invert", action="store_true", help="trade against the signal")
    p.add_argument("--tz-shift", type=int, default=0,
                   help="whole hours to add to the file's timestamps")
    p.add_argument("--dollars-per-point", type=float, default=50.0,
                   help="50 for ES, 5 for MES, 20 for NQ, 2 for MNQ")
    p.add_argument("--trades-csv", help="write the trade log here")
    args = p.parse_args()

    bars = load_bars(args.csv, args.tz_shift)
    if not bars:
        raise SystemExit("no bars parsed")
    days = build_days(bars, hhmm(args.signal_time), hhmm(args.entry_time),
                      hhmm(args.exit_time))
    if not days:
        raise SystemExit(f"no session had both a {args.signal_time} and a "
                         f"{args.entry_time} bar -- check --tz-shift and the "
                         f"export's timezone")

    print(f"{args.csv}: {len(bars)} bars, {bars[0]['ts']} -> {bars[-1]['ts']}")
    print(f"{len(days)} sessions with both a {args.signal_time} signal candle "
          f"and a {args.entry_time} entry")
    print(f"stop {args.stop:g} / target {args.target:g} pts, cost {args.cost:g} pts, "
          f"flat after {args.exit_time}"
          f"{', signal inverted' if args.invert else ''}\n")

    results = {}
    for resolution in RESOLUTIONS:
        trades = []
        for day in days:
            d = signal_direction(day)
            if args.invert:
                d = -d
            outcome, pnl, amb = resolve(day, d, args.stop, args.target,
                                        resolution, args.entry_mode)
            if outcome == "no-data":
                continue
            trades.append({"date": day["date"], "dir": d, "outcome": outcome,
                           "pnl": pnl - args.cost, "ambiguous": amb})
        results[resolution] = trades

    print(HEADER)
    for resolution in RESOLUTIONS:
        print(line(resolution, stats(results[resolution], args.dollars_per_point)))

    print(f"\nbars containing both levels (order unknown at 15m): "
          f"{stats(results['pessimistic'], args.dollars_per_point)['amb']:.1f}% of trades")

    be = 100 * (args.stop + args.cost) / (args.stop + args.target)
    print(f"break-even target-first rate at 1:{args.target/args.stop:g} = {be:.1f}%")

    by_year = defaultdict(list)
    for t in results["heuristic"]:
        by_year[t["date"].year].append(t)
    if len(by_year) > 1:
        print("\nby year (heuristic):")
        print(HEADER)
        for y in sorted(by_year):
            print(line(str(y), stats(by_year[y], args.dollars_per_point)))

    longs = [t for t in results["heuristic"] if t["dir"] > 0]
    shorts = [t for t in results["heuristic"] if t["dir"] < 0]
    print("\nby signal direction (heuristic):")
    print(HEADER)
    for label, group in (("signal long", longs), ("signal short", shorts)):
        if group:
            print(line(label, stats(group, args.dollars_per_point)))

    if args.trades_csv:
        with open(args.trades_csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "direction", "outcome_pessimistic",
                        "outcome_heuristic", "outcome_optimistic", "pnl_heuristic"])
            for p_, h_, o_ in zip(results["pessimistic"], results["heuristic"],
                                  results["optimistic"]):
                w.writerow([h_["date"], h_["dir"], p_["outcome"], h_["outcome"],
                            o_["outcome"], round(h_["pnl"], 2)])
        print(f"\ntrade log -> {args.trades_csv}")


if __name__ == "__main__":
    main()
