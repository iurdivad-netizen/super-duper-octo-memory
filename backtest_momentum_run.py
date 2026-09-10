#!/usr/bin/env python3
"""Base-rate probe for the momentum-run continuation trade.

Trade model, identical to momentum_run_strategy.pine on default settings:

    signal  N consecutive same-colour candles
    entry   stop order 1 tick beyond the signal candle's extreme,
            valid for `valid_bars` bars
    stop    the signal candle's opposite extreme, 1 tick beyond
    target  entry + RR * R

The point of this script is not to find a profitable parameter set. It is to
measure the realised hit rate against the only number that matters:

    a +RR / -1R bracket on a driftless random walk wins 1 / (1 + RR)

which is 40.0% at RR = 1.5. Anything at or below that is a coin flip you are
paying commission to take.

Intrabar resolution is CONSERVATIVE: when a single bar's range contains both
the stop and the target, the stop is booked. `--optimistic` flips that, so the
two runs bracket the true answer. The gap between them is reported as `amb%`;
where it is small the assumption is not what is driving the result.

Usage:
    python3 backtest_momentum_run.py
    python3 backtest_momentum_run.py --rr 1.0 --fade
"""
import argparse
import csv
import os

# (label, path, tick size, round-trip friction in ticks)
MARKETS = [
    ("ES 15m",   "data/es1_15m_tradingview.csv", 0.25,      3.0),
    ("ES 3m",    "data/es1_3m_tradingview.csv",  0.25,      3.0),
    ("SPY 1D",   "data/spy_1day.csv",            0.01,      3.0),
    ("EURUSD 1h", "data/eurusd_1h.csv",          0.00001,   3.0),
    ("XAUUSD 1h", "data/xauusd_1h.csv",          0.01,     30.0),
    ("BTC 1h",   "data/btcusd_1h.csv",           0.01,    500.0),
]


def load(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append((float(r["open"]), float(r["high"]),
                             float(r["low"]), float(r["close"])))
            except (TypeError, ValueError, KeyError):
                continue
    return rows


def colour(o, c, h, l, min_body):
    rng, body = h - l, abs(c - o)
    if rng <= 0 or body / rng < min_body:
        return 0
    return 1 if c > o else (-1 if c < o else 0)


def run_lengths(bars, min_body):
    out = [0] * len(bars)
    prev = 0
    for i, (o, h, l, c) in enumerate(bars):
        d = colour(o, c, h, l, min_body)
        if d == 0:
            out[i], prev = 0, 0
        elif d == prev:
            out[i] = out[i - 1] + 1
        else:
            out[i], prev = 1, d
    return out


def probe(bars, n, tick, rr=1.5, cost_ticks=3.0, valid_bars=1, min_body=0.0,
          min_risk_ticks=0.0, max_risk_ticks=0.0,
          optimistic=False, fade=False, max_hold=200):
    runs = run_lengths(bars, min_body)
    setups = filled = wins = ambiguous = 0
    net_r = gross_r = 0.0
    widths = []

    for i in range(len(bars) - max_hold - 2):
        o, h, l, c = bars[i]
        d0 = colour(o, c, h, l, min_body)
        if d0 == 0 or runs[i] != n:
            continue
        d = -d0 if fade else d0

        entry = h + tick if d > 0 else l - tick
        stop = l - tick if d > 0 else h + tick
        r = abs(entry - stop)
        if r <= 0:
            continue
        if min_risk_ticks and r < min_risk_ticks * tick:
            continue
        if max_risk_ticks and r > max_risk_ticks * tick:
            continue
        setups += 1
        target = entry + d * rr * r

        fill_bar = None
        for j in range(i + 1, i + 1 + valid_bars):
            if (d > 0 and bars[j][1] >= entry) or (d < 0 and bars[j][2] <= entry):
                fill_bar = j
                break
        if fill_bar is None:
            continue
        filled += 1
        widths.append(r / tick)

        result = None
        for j in range(fill_bar, min(fill_bar + max_hold, len(bars))):
            _, bh, bl, bc = bars[j]
            hit_stop = bl <= stop if d > 0 else bh >= stop
            hit_tgt = bh >= target if d > 0 else bl <= target
            if hit_stop and hit_tgt:
                ambiguous += 1
                result = rr if optimistic else -1.0
                break
            if hit_stop:
                result = -1.0
                break
            if hit_tgt:
                result = rr
                break
        if result is None:  # still open at the horizon: mark to market
            last = bars[min(fill_bar + max_hold, len(bars) - 1)][3]
            result = d * (last - entry) / r

        if result > 0:
            wins += 1
        gross_r += result
        net_r += result - (cost_ticks * tick) / r

    return {
        "setups": setups, "filled": filled,
        "fill_rate": filled / setups if setups else 0.0,
        "win_rate": wins / filled if filled else 0.0,
        "net_r": net_r,
        "gross_per_trade": gross_r / filled if filled else 0.0,
        "r_per_trade": net_r / filled if filled else 0.0,
        "cost_drag": (net_r - gross_r) / filled if filled else 0.0,
        "median_r_ticks": sorted(widths)[len(widths) // 2] if widths else 0.0,
        "amb_rate": ambiguous / filled if filled else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rr", type=float, default=1.5)
    ap.add_argument("--runs", type=int, nargs="+", default=[2, 3, 4, 5])
    ap.add_argument("--valid-bars", type=int, default=1)
    ap.add_argument("--min-body", type=float, default=0.0)
    ap.add_argument("--min-risk", type=float, default=0.0,
                    help="skip setups whose stop distance is under N ticks")
    ap.add_argument("--max-risk", type=float, default=0.0,
                    help="skip setups whose stop distance is over N ticks")
    ap.add_argument("--optimistic", action="store_true",
                    help="book the target when a bar contains both levels")
    ap.add_argument("--fade", action="store_true",
                    help="trade against the run instead of with it")
    args = ap.parse_args()

    breakeven = 100.0 / (1.0 + args.rr)
    print(f"target {args.rr}R  ->  driftless break-even hit rate {breakeven:.1f}%")
    print(f"intrabar ties: {'target' if args.optimistic else 'stop'} wins"
          f"{'   [FADE]' if args.fade else ''}\n")
    print(f"{'market':11s} {'N':>2s} {'setups':>7s} {'filled':>7s} {'fill%':>6s} "
          f"{'win%':>6s} {'vs BE':>6s} {'medR(t)':>8s} {'netR':>9s} {'R/trade':>8s}")

    for label, path, tick, cost in MARKETS:
        if not os.path.exists(path):
            continue
        bars = load(path)
        for n in args.runs:
            s = probe(bars, n, tick, rr=args.rr, cost_ticks=cost,
                      valid_bars=args.valid_bars, min_body=args.min_body,
                      min_risk_ticks=args.min_risk, max_risk_ticks=args.max_risk,
                      optimistic=args.optimistic, fade=args.fade)
            edge = 100 * s["win_rate"] - breakeven
            print(f"{label:11s} {n:2d} {s['setups']:7d} {s['filled']:7d} "
                  f"{100*s['fill_rate']:5.1f}% {100*s['win_rate']:5.1f}% "
                  f"{edge:+5.1f} {s['median_r_ticks']:8.1f} "
                  f"{s['net_r']:9.1f} {s['r_per_trade']:+8.3f}")
        print()


if __name__ == "__main__":
    main()
