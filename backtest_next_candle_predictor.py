#!/usr/bin/env python3
"""
Walk-forward validator for the `next_candle_predictor.pine` model.

This is a bar-for-bar replica of the Pine logic so the indicator's claims can be
checked against real data *before* trusting the on-chart panel. Everything is
strictly causal: the forecast for bar t+1 is produced from counts that contain
bars <= t only ("predict, then update"), so every number reported here is
out-of-sample by construction.

Two models are measured independently:

  COLOR  hierarchical Markov chain over the last 1..N candle colors, with
         empirical-Bayes back-off (level k shrinks toward level k-1, level 1
         shrinks toward the unconditional green rate).
         Benchmarks: always-predict-the-majority-color, and the base-rate
         probabilistic forecast (Brier skill score).

  SIZE   EWMA of candle range, multiplied by a state-conditional factor
         (state = colour pattern x volatility bucket), shrunk toward 1.0.
         Benchmark: the plain EWMA (multiplier fixed at 1.0).

TRAIN / HOLDOUT SPLIT
Pass --split 0.75 to learn on the first 75% of the candles and report the last
25% separately. With --freeze (the default) the model stops learning at the
boundary, so the holdout answers a question walk-forward cannot: does what the
model learned in the past still hold later, or has the market moved underneath
it? The gap between the two columns is the overfit/decay measure.

--tune runs a parameter grid on the TRAIN portion only, picks the winner there,
and reports it once on the untouched holdout. It also prints where the
train-best config actually ranks on the holdout — if it lands mid-pack, the
tuning surface is noise and you should not tune.

Usage:
    python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv
    python3 backtest_next_candle_predictor.py data/es1_3m_tradingview.csv --nprev 5
    python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --split 0.75
    python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv --split 0.75 --tune
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys

# --- shared constants (must match the .pine file) ----------------------------
MAXN = 8
IDX_PER_CTX = 2 ** (MAXN + 1) - 2      # 510 slots: levels 1..8 laid end to end
SIZE_STATES = 3 * 8                     # 3 volatility buckets x 8 colour patterns


# -----------------------------------------------------------------------------
# data
# -----------------------------------------------------------------------------
def load_ohlc(path: str):
    """Read a TradingView CSV export -> list of (open, high, low, close)."""
    rows = []
    with open(path, newline="") as fh:
        sniff = fh.readline()
        fh.seek(0)
        delim = ";" if sniff.count(";") > sniff.count(",") else ","
        for rec in csv.DictReader(fh, delimiter=delim):
            keys = {k.lower().strip(): k for k in rec}
            try:
                rows.append((
                    float(rec[keys["open"]]),
                    float(rec[keys["high"]]),
                    float(rec[keys["low"]]),
                    float(rec[keys["close"]]),
                ))
            except (KeyError, ValueError, TypeError):
                continue
    return rows


# -----------------------------------------------------------------------------
# colour model
# -----------------------------------------------------------------------------
def pat_id(colors, end, k):
    """Pattern id of the k colours ending at bar `end`, oldest bit first."""
    v = 0
    for j in range(k - 1, -1, -1):
        v = v * 2 + colors[end - j]
    return v


LEVEL_BASE = [0] * (MAXN + 1)
for _k in range(1, MAXN + 1):
    LEVEL_BASE[_k] = 2 ** _k - 2


class ColorModel:
    """Hierarchical Markov chain with empirical-Bayes back-off."""

    def __init__(self, nprev=3, s_link=50.0, s_root=10.0, n_ctx=1):
        self.n = nprev
        self.s = s_link
        self.s0 = s_root
        self.tot = [0.0] * (IDX_PER_CTX * n_ctx)
        self.grn = [0.0] * (IDX_PER_CTX * n_ctx)
        self.g_tot = 0.0
        self.g_grn = 0.0

    def base_rate(self):
        return (self.g_grn + self.s0 * 0.5) / (self.g_tot + self.s0)

    def ladder(self, colors, end, ctx):
        """P(next candle green) after each back-off level 1..N."""
        p = self.base_rate()
        out = []
        for k in range(1, self.n + 1):
            idx = ctx * IDX_PER_CTX + LEVEL_BASE[k] + pat_id(colors, end, k)
            p = (self.grn[idx] + self.s * p) / (self.tot[idx] + self.s)
            out.append((p, self.tot[idx], self.grn[idx]))
        return out

    def update(self, colors, t, ctx, w=1.0):
        """Fold bar t's outcome into the counts keyed on the pattern before it."""
        y = colors[t]
        self.g_tot += w
        self.g_grn += w * y
        for k in range(1, self.n + 1):
            idx = ctx * IDX_PER_CTX + LEVEL_BASE[k] + pat_id(colors, t - 1, k)
            self.tot[idx] += w
            self.grn[idx] += w * y


# -----------------------------------------------------------------------------
# size model
# -----------------------------------------------------------------------------
class SizeModel:
    """EWMA range with a state-conditional multiplier, shrunk toward 1.0."""

    def __init__(self, lam=0.94, s_mult=40.0, size_n=2, lo=0.75, hi=1.30):
        self.lam = lam
        self.s = s_mult
        self.size_n = size_n
        self.lo = lo
        self.hi = hi
        self.ew = None
        self.sum_r = [0.0] * SIZE_STATES
        self.cnt = [0.0] * SIZE_STATES
        self.body_r = [0.0] * SIZE_STATES
        self.body_c = [0.0] * SIZE_STATES

    def bucket(self, rng, prev_ew):
        if prev_ew is None or prev_ew <= 0:
            return 1
        vr = rng / prev_ew
        return 0 if vr < self.lo else (1 if vr < self.hi else 2)

    def state(self, colors, t, rng, prev_ew):
        pid = pat_id(colors, t, self.size_n) if self.size_n > 0 else 0
        return self.bucket(rng, prev_ew) * 8 + pid

    def mult(self, st):
        return (self.sum_r[st] + self.s * 1.0) / (self.cnt[st] + self.s)

    def body_ratio(self, st, global_body):
        return (self.body_r[st] + self.s * global_body) / (self.body_c[st] + self.s)


def pct(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    i = p * (len(sorted_vals) - 1)
    lo = int(math.floor(i))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


# -----------------------------------------------------------------------------
# walk-forward run
# -----------------------------------------------------------------------------
def _blank():
    return {"n": 0, "hits": 0, "green": 0, "brier": 0.0, "brier_ref": 0.0,
            "ll": 0.0, "n_sz": 0, "mae": 0.0, "mae_ref": 0.0, "cover": 0,
            "ape": 0.0, "body": 0.0, "body_n": 0}


def _metrics(a):
    """Turn raw accumulators into the numbers the panel reports."""
    if not a["n"]:
        return {"n": 0}
    base = a["green"] / a["n"]
    maj = max(base, 1 - base)
    acc = a["hits"] / a["n"]
    se = math.sqrt(maj * (1 - maj) / a["n"])
    bs = a["brier"] / a["n"]
    bs_ref = a["brier_ref"] / a["n"]
    m = {
        "n": a["n"], "base_green": base, "majority": maj, "accuracy": acc,
        "edge": acc - maj, "z": (acc - maj) / se if se > 0 else 0.0,
        "brier": bs, "brier_base": bs_ref,
        "bss": 1 - bs / bs_ref if bs_ref > 0 else 0.0,
        "logloss": a["ll"] / a["n"],
    }
    if a["n_sz"]:
        m.update(n_size=a["n_sz"], mae=a["mae"] / a["n_sz"],
                 mae_naive=a["mae_ref"] / a["n_sz"],
                 skill=1 - a["mae"] / a["mae_ref"] if a["mae_ref"] > 0 else 0.0,
                 mape=100 * a["ape"] / a["n_sz"],
                 coverage=100 * a["cover"] / a["n_sz"],
                 body_ratio=a["body"] / a["body_n"] if a["body_n"] else float("nan"))
    return m


def run(bars, nprev=3, s_link=50.0, s_root=10.0, lam=0.94, s_mult=40.0,
        size_n=2, burn_in=500, band_win=300, band_lo=0.10, band_hi=0.90,
        basis="close_open", split=None, freeze=True):
    """Walk the bars once. Returns {"train": {...}, "hold": {...}}.

    With split=None every scored bar lands in "train" and nothing is frozen —
    that is the pure walk-forward mode. With split=0.75 the first 75% of bars
    feed the model, the last 25% are scored separately, and (unless freeze is
    False) the model stops learning at the boundary.
    """
    if basis == "close_close":
        colors = [1] + [1 if bars[i][3] > bars[i - 1][3] else 0
                        for i in range(1, len(bars))]
    else:
        colors = [1 if c > o else 0 for o, h, l, c in bars]

    split_at = int(len(bars) * split) if split else len(bars) + 1

    cm = ColorModel(nprev, s_link, s_root)
    sm = SizeModel(lam, s_mult, size_n)
    acc = {"train": _blank(), "hold": _blank()}
    err_win = []
    pend = None

    for t in range(len(bars)):
        o, h, l, c = bars[t]
        rng = h - l
        body = abs(c - o)
        prev_ew = sm.ew
        hold = t >= split_at
        phase = "hold" if hold else "train"
        # The EWMA is state, not a fitted parameter: freezing it would only make
        # the holdout predict stale volatility. The counts are what get frozen.
        learn = not (hold and freeze)

        # -- 1. score the forecast made at the close of bar t-1 ---------------
        if pend is not None:
            y = colors[t]
            a = acc[phase]
            if t > burn_in:
                a["n"] += 1
                a["green"] += y
                a["hits"] += 1 if ((pend["p"] >= 0.5) == (y == 1)) else 0
                a["brier"] += (pend["p"] - y) ** 2
                a["brier_ref"] += (pend["base"] - y) ** 2
                pc = min(max(pend["p"], 1e-6), 1 - 1e-6)
                a["ll"] += -(y * math.log(pc) + (1 - y) * math.log(1 - pc))
                if pend["rng"] > 0:
                    a["n_sz"] += 1
                    a["mae"] += abs(pend["rng"] - rng)
                    a["mae_ref"] += abs(pend["naive"] - rng)
                    a["ape"] += (abs(pend["rng"] - rng) / rng) if rng > 0 else 0.0
                    if not math.isnan(pend["lo"]) and pend["lo"] <= rng <= pend["hi"]:
                        a["cover"] += 1
                    if rng > 0:
                        a["body"] += body / rng
                        a["body_n"] += 1

            if learn and pend["rng"] > 0:
                err_win.append(rng / pend["rng"])
                if len(err_win) > band_win:
                    err_win.pop(0)

            if learn and pend["state"] is not None and pend["ew"] > 0:
                st = pend["state"]
                sm.sum_r[st] += rng / pend["ew"]
                sm.cnt[st] += 1.0
                if rng > 0:
                    sm.body_r[st] += body / rng
                    sm.body_c[st] += 1.0

        # -- 2. fold bar t's colour outcome into the Markov counts ------------
        if learn and t >= MAXN + 2:
            cm.update(colors, t, 0)

        # -- 3. advance the EWMA, then forecast bar t+1 -----------------------
        sm.ew = rng if prev_ew is None else lam * prev_ew + (1 - lam) * rng

        pend = None
        if t >= MAXN + 3 and sm.ew > 0:
            lad = [x[0] for x in cm.ladder(colors, t, 0)]
            st = sm.state(colors, t, rng, prev_ew)
            prng = sm.ew * sm.mult(st)
            sw = sorted(err_win)
            enough = len(sw) >= 30
            pend = {
                "p": lad[-1], "lad": lad, "base": cm.base_rate(),
                "rng": prng, "naive": sm.ew, "state": st, "ew": sm.ew,
                "lo": prng * pct(sw, band_lo) if enough else float("nan"),
                "hi": prng * pct(sw, band_hi) if enough else float("nan"),
            }

    return {"train": _metrics(acc["train"]), "hold": _metrics(acc["hold"])}


def _fmt_pair(a, b, key, scale=1.0, fmt="{:+.2f}", suffix=""):
    def one(m):
        if not m.get("n") or key not in m:
            return "-"
        return fmt.format(m[key] * scale) + suffix
    return one(a), one(b)


def report(name, res, split=None):
    tr, ho = res["train"], res["hold"]
    two = bool(split) and ho.get("n")
    ca, cb = ("TRAIN", "HOLDOUT") if two else ("WALK-FORWARD", "")

    print(f"\n=== {name} ===")
    if not tr.get("n"):
        print("  no scored bars")
        return
    w = 16
    print(f"  {'':26}{ca:>{w}}{cb:>{w}}")
    print(f"  {'scored bars':26}{tr['n']:>{w},}" +
          (f"{ho['n']:>{w},}" if two else ""))

    print("  -- colour " + "-" * 46)
    for label, key, sc, fmt, sfx in [
            ("base rate P(green)",   "base_green", 100, "{:.2f}",  "%"),
            ("always-majority acc.", "majority",   100, "{:.2f}",  "%"),
            ("model accuracy",       "accuracy",   100, "{:.2f}",  "%"),
            ("edge over majority",   "edge",       100, "{:+.2f}", " pp"),
            ("  z-score",            "z",            1, "{:+.2f}", ""),
            ("Brier skill score",    "bss",          1, "{:+.5f}", ""),
            ("log loss",             "logloss",      1, "{:.5f}",  "")]:
        a, b = _fmt_pair(tr, ho, key, sc, fmt, sfx)
        print(f"  {label:26}{a:>{w}}" + (f"{b:>{w}}" if two else ""))

    if "n_size" in tr:
        print("  -- size " + "-" * 48)
        for label, key, sc, fmt, sfx in [
                ("MAE",               "mae",       1, "{:.4f}",  ""),
                ("MAE, plain EWMA",   "mae_naive", 1, "{:.4f}",  ""),
                ("skill vs EWMA",     "skill",   100, "{:+.2f}", "%"),
                ("MAPE",              "mape",      1, "{:.2f}",  "%"),
                ("80% band coverage", "coverage",  1, "{:.2f}",  "%")]:
            a, b = _fmt_pair(tr, ho, key, sc, fmt, sfx)
            print(f"  {label:26}{a:>{w}}" + (f"{b:>{w}}" if two else ""))

    if two and "skill" in tr and "skill" in ho:
        print("  -- decay " + "-" * 47)
        print(f"  {'size skill drop':26}{'':>{w}}"
              f"{(ho['skill'] - tr['skill']) * 100:>+{w}.2f} pp")


# -----------------------------------------------------------------------------
# parameter tuning — grid on TRAIN only, one read on HOLDOUT
# -----------------------------------------------------------------------------
def _rank_of(values, target, higher_is_better=True):
    """Percentile rank of `target` within `values`. 100 = best, 50 = mid-pack."""
    vals = [v for v in values if v is not None]
    if not vals:
        return float("nan")
    better = sum(1 for v in vals if (v > target if higher_is_better else v < target))
    return 100.0 * (1.0 - better / len(vals))


def _grid_note(label, ho_vals, chosen, scale=1.0, fmt="{:+.5f}"):
    lo = min(v for v in ho_vals if v is not None) * scale
    hi = max(v for v in ho_vals if v is not None) * scale
    rk = _rank_of(ho_vals, chosen)
    print(f"         holdout spread over the grid: {fmt.format(lo)} .. "
          f"{fmt.format(hi)}")
    print(f"         the train-best config lands at the {rk:.0f}th percentile "
          f"on holdout   (~50th = tuning bought nothing)")


def tune(bars, split=0.75, burn_in=500, basis="close_open", freeze=True):
    print(f"\n{'=' * 68}")
    print(f"TUNING — grid fitted on the first {split * 100:.0f}% of the bars, "
          f"read once on the rest")
    print("=" * 68)

    # -- colour grid: pattern length x back-off strength ----------------------
    grid_c, res_c = [], []
    for n in (1, 2, 3, 4, 5):
        for sl in (10.0, 50.0, 200.0):
            grid_c.append((n, sl))
            res_c.append(run(bars, nprev=n, s_link=sl, burn_in=burn_in,
                             basis=basis, split=split, freeze=freeze))
    tr_c = [r["train"].get("bss") for r in res_c]
    ho_c = [r["hold"].get("bss") for r in res_c]
    bi = max(range(len(tr_c)), key=lambda i: tr_c[i] if tr_c[i] is not None else -9)
    print(f"\ncolour — train-best: N={grid_c[bi][0]}  s_link={grid_c[bi][1]:.0f}"
          f"   train BSS {tr_c[bi]:+.5f}  ->  holdout BSS {ho_c[bi]:+.5f}")
    _grid_note("colour", ho_c, ho_c[bi])

    # -- size grid: EWMA decay x shrink strength x colour context -------------
    grid_s, res_s = [], []
    for lam in (0.90, 0.94, 0.97):
        for smu in (10.0, 40.0, 100.0):
            for sn in (0, 1, 2, 3):
                grid_s.append((lam, smu, sn))
                res_s.append(run(bars, lam=lam, s_mult=smu, size_n=sn,
                                 burn_in=burn_in, basis=basis, split=split,
                                 freeze=freeze))
    tr_s = [r["train"].get("skill") for r in res_s]
    ho_s = [r["hold"].get("skill") for r in res_s]
    bj = max(range(len(tr_s)), key=lambda i: tr_s[i] if tr_s[i] is not None else -9)
    lam, smu, sn = grid_s[bj]
    print(f"\nsize   — train-best: lambda={lam}  shrink={smu:.0f}  size_n={sn}"
          f"   train {tr_s[bj] * 100:+.2f}%  ->  holdout {ho_s[bj] * 100:+.2f}%")
    _grid_note("size", ho_s, ho_s[bj], 100.0, "{:+.2f}%")

    n, sl = grid_c[bi]
    best = run(bars, nprev=n, s_link=sl, lam=lam, s_mult=smu, size_n=sn,
               burn_in=burn_in, basis=basis, split=split, freeze=freeze)
    report(f"SELECTED  N={n} s_link={sl:.0f} lambda={lam} shrink={smu:.0f} "
           f"size_n={sn}", best, split)
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", default="data/es1_15m_tradingview.csv")
    ap.add_argument("--nprev", type=int, default=3)
    ap.add_argument("--sweep", action="store_true",
                    help="run every pattern length 1..8 and compare")
    ap.add_argument("--split", type=float, default=None, metavar="F",
                    help="learn on the first F of the bars, report the rest "
                         "separately (e.g. 0.75)")
    ap.add_argument("--no-freeze", action="store_true",
                    help="keep learning through the holdout instead of freezing "
                         "the counts at the split")
    ap.add_argument("--tune", action="store_true",
                    help="grid-search on the train portion only, then read the "
                         "winner once on the holdout")
    ap.add_argument("--basis", choices=["close_open", "close_close"],
                    default="close_open")
    ap.add_argument("--burn-in", type=int, default=500)
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        sys.exit(f"no such file: {args.csv}")
    bars = load_ohlc(args.csv)
    freeze = not args.no_freeze
    print(f"loaded {len(bars)} bars from {args.csv}  (basis: {args.basis})")
    if args.split:
        cut = int(len(bars) * args.split)
        print(f"split at bar {cut}: {cut} train / {len(bars) - cut} holdout"
              f"   (model {'frozen' if freeze else 'still learning'} in holdout)")

    if args.tune:
        tune(bars, split=args.split or 0.75, burn_in=args.burn_in,
             basis=args.basis, freeze=freeze)
    elif args.sweep:
        for n in range(1, MAXN + 1):
            report(f"N = {n}", run(bars, nprev=n, burn_in=args.burn_in,
                                   basis=args.basis, split=args.split,
                                   freeze=freeze), args.split)
    else:
        report(f"N = {args.nprev}",
               run(bars, nprev=args.nprev, burn_in=args.burn_in,
                   basis=args.basis, split=args.split, freeze=freeze),
               args.split)


if __name__ == "__main__":
    main()
