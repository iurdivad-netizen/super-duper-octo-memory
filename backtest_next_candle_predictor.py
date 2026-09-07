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

Usage:
    python3 backtest_next_candle_predictor.py data/es1_15m_tradingview.csv
    python3 backtest_next_candle_predictor.py data/es1_3m_tradingview.csv --nprev 5
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
def run(bars, nprev=3, s_link=50.0, s_root=10.0, lam=0.94, s_mult=40.0,
        size_n=2, burn_in=500, band_win=300, band_lo=0.10, band_hi=0.90,
        basis="close_open"):
    if basis == "close_close":
        colors = [1] + [1 if bars[i][3] > bars[i - 1][3] else 0
                        for i in range(1, len(bars))]
    else:
        colors = [1 if c > o else 0 for o, h, l, c in bars]

    cm = ColorModel(nprev, s_link, s_root)
    sm = SizeModel(lam, s_mult, size_n)

    n_sc = hits = green_seen = 0
    brier = brier_base = logloss = 0.0
    lvl_hits = [0] * (nprev + 1)
    lvl_n = [0] * (nprev + 1)

    n_sz = cover = 0
    mae = mae_naive = ape = 0.0
    err_win = []
    body_sum = body_cnt = 0.0

    pend = None      # forecast built at the close of bar t-1, scored on bar t

    for t in range(len(bars)):
        o, h, l, c = bars[t]
        rng = h - l
        body = abs(c - o)
        prev_ew = sm.ew                       # EWMA as of the close of bar t-1

        # -- 1. score the forecast made at the close of bar t-1 ---------------
        if pend is not None:
            y = colors[t]
            scoring = t > burn_in
            if scoring:
                n_sc += 1
                green_seen += y
                hits += 1 if ((pend["p"] >= 0.5) == (y == 1)) else 0
                brier += (pend["p"] - y) ** 2
                brier_base += (pend["base"] - y) ** 2
                pc = min(max(pend["p"], 1e-6), 1 - 1e-6)
                logloss += -(y * math.log(pc) + (1 - y) * math.log(1 - pc))
                for k in range(1, nprev + 1):
                    lvl_n[k] += 1
                    lvl_hits[k] += 1 if ((pend["lad"][k - 1] >= 0.5) == (y == 1)) else 0

            if pend["rng"] > 0:
                if scoring:
                    n_sz += 1
                    mae += abs(pend["rng"] - rng)
                    mae_naive += abs(pend["naive"] - rng)
                    ape += (abs(pend["rng"] - rng) / rng) if rng > 0 else 0.0
                    if not math.isnan(pend["lo"]) and pend["lo"] <= rng <= pend["hi"]:
                        cover += 1
                # the error window is a rolling calibration sample, always fed
                err_win.append(rng / pend["rng"])
                if len(err_win) > band_win:
                    err_win.pop(0)

            # the state that was live when the forecast was made now has an
            # outcome attached to it -> fold the realised ratio into that state
            if pend["state"] is not None and pend["ew"] > 0:
                st = pend["state"]
                sm.sum_r[st] += rng / pend["ew"]
                sm.cnt[st] += 1.0
                if rng > 0:
                    sm.body_r[st] += body / rng
                    sm.body_c[st] += 1.0
                    body_sum += body / rng
                    body_cnt += 1.0

        # -- 2. fold bar t's colour outcome into the Markov counts ------------
        if t >= MAXN + 2:
            cm.update(colors, t, 0)

        # -- 3. advance the EWMA with bar t, then forecast bar t+1 ------------
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

    # -- report ---------------------------------------------------------------
    res = {"n": n_sc}
    if n_sc:
        base_green = green_seen / n_sc
        majority = max(base_green, 1 - base_green)
        acc = hits / n_sc
        se = math.sqrt(majority * (1 - majority) / n_sc)
        res.update(
            base_green=base_green,
            majority=majority,
            accuracy=acc,
            edge=acc - majority,
            z=(acc - majority) / se if se > 0 else 0.0,
            brier=brier / n_sc,
            brier_base=brier_base / n_sc,
            bss=1 - (brier / n_sc) / (brier_base / n_sc) if brier_base > 0 else 0.0,
            logloss=logloss / n_sc,
            levels=[(k, lvl_hits[k] / lvl_n[k]) for k in range(1, nprev + 1) if lvl_n[k]],
        )
    if n_sz:
        res.update(
            n_size=n_sz,
            mae=mae / n_sz,
            mae_naive=mae_naive / n_sz,
            skill=1 - (mae / n_sz) / (mae_naive / n_sz),
            mape=100 * ape / n_sz,
            coverage=100 * cover / n_sz,
            body_ratio=body_sum / body_cnt if body_cnt else float("nan"),
        )
    return res


def report(name, r):
    print(f"\n=== {name} ===")
    if not r.get("n"):
        print("  no scored bars")
        return
    print(f"  scored bars                {r['n']}")
    print("  -- colour ------------------------------------------------")
    print(f"  base rate P(green)         {r['base_green']*100:6.2f}%")
    print(f"  always-majority accuracy   {r['majority']*100:6.2f}%   <- the bar to beat")
    print(f"  model accuracy             {r['accuracy']*100:6.2f}%")
    print(f"  edge over majority         {r['edge']*100:+6.2f} pp   (z = {r['z']:+.2f})")
    print(f"  Brier  model / base-rate   {r['brier']:.5f} / {r['brier_base']:.5f}")
    print(f"  Brier skill score          {r['bss']:+.5f}   <- >0 means real skill")
    print(f"  log loss                   {r['logloss']:.5f}")
    print("  accuracy by back-off level: " +
          "  ".join(f"L{k}={a*100:.2f}%" for k, a in r["levels"]))
    if "n_size" in r:
        print("  -- size --------------------------------------------------")
        print(f"  MAE model / plain EWMA     {r['mae']:.4f} / {r['mae_naive']:.4f}")
        print(f"  size skill vs EWMA         {r['skill']*100:+6.2f}%   <- >0 means the")
        print("                                        state multiplier adds value")
        print(f"  MAPE                       {r['mape']:6.2f}%")
        print(f"  80% band coverage          {r['coverage']:6.2f}%   (target 80%)")
        print(f"  mean body/range            {r['body_ratio']:6.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", default="data/es1_15m_tradingview.csv")
    ap.add_argument("--nprev", type=int, default=3)
    ap.add_argument("--sweep", action="store_true",
                    help="run every pattern length 1..8 and compare")
    ap.add_argument("--basis", choices=["close_open", "close_close"],
                    default="close_open")
    ap.add_argument("--burn-in", type=int, default=500)
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        sys.exit(f"no such file: {args.csv}")
    bars = load_ohlc(args.csv)
    print(f"loaded {len(bars)} bars from {args.csv}  (basis: {args.basis})")

    if args.sweep:
        for n in range(1, MAXN + 1):
            report(f"N = {n}", run(bars, nprev=n, burn_in=args.burn_in,
                                   basis=args.basis))
    else:
        report(f"N = {args.nprev}", run(bars, nprev=args.nprev,
                                        burn_in=args.burn_in, basis=args.basis))


if __name__ == "__main__":
    main()
