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


PHASES = ("train", "valid", "test")


def run(bars, nprev=3, s_link=50.0, s_root=10.0, lam=0.94, s_mult=40.0,
        size_n=2, burn_in=500, band_win=300, band_lo=0.10, band_hi=0.90,
        basis="close_open", size_basis="range", train=0.75, valid=0.20,
        freeze_at=None, dead_pct=5.0, dead_len=200):
    """One causal pass over the bars, scored into three windows.

    train / valid  are fractions of the series; whatever is left is the test
    window. `freeze_at` is the fraction at which the model stops learning
    (None = never, i.e. plain walk-forward). Learning and scoring are separate
    concerns: a window can be scored whether or not the model is still fitting.
    """
    if basis == "close_close":
        colors = [1] + [1 if bars[i][3] > bars[i - 1][3] else 0
                        for i in range(1, len(bars))]
    else:
        colors = [1 if c > o else 0 for o, h, l, c in bars]

    nb = len(bars)
    t_end = int(nb * train)
    v_end = int(nb * (train + valid))
    f_end = int(nb * freeze_at) if freeze_at is not None else nb + 1

    cm = ColorModel(nprev, s_link, s_root)
    sm = SizeModel(lam, s_mult, size_n)
    acc = {ph: _blank() for ph in PHASES}
    err_win = []
    pend = None
    rng_hist = []      # rolling sample for the dead-bar median
    dead = []          # per-bar dead flag
    n_dead = 0

    for t in range(nb):
        o, h, l, c = bars[t]
        if size_basis == "truerange" and t > 0:
            pc = bars[t - 1][3]
            rng = max(h, pc) - min(l, pc)
        else:
            rng = h - l
        body = abs(c - o)

        # -- dead-bar filter --------------------------------------------------
        # Some feeds emit synthetic bars when the market is shut (gold and FX
        # over the weekend, for instance) with a range near zero and a stale
        # price. Those bars are not observations; left in, they manufacture
        # enormous fake colour persistence. Compare against a rolling MEDIAN,
        # which survives a sample that is a third dead.
        med = None
        if len(rng_hist) >= 50:
            srt = sorted(rng_hist)
            med = srt[len(srt) // 2]
        is_dead = bool(dead_pct > 0 and med and rng < dead_pct / 100.0 * med)
        dead.append(is_dead)
        n_dead += is_dead
        rng_hist.append(rng)
        if len(rng_hist) > dead_len:
            rng_hist.pop(0)

        def clean(end, k):
            """True when bars end-k+1 .. end are all live."""
            lo_ = max(0, end - k + 1)
            return not any(dead[lo_:end + 1])

        prev_ew = sm.ew
        phase = "train" if t < t_end else ("valid" if t < v_end else "test")
        # The EWMA is state, not a fitted parameter: freezing it would only make
        # the later windows predict stale volatility. The counts are what freeze.
        learn = t < f_end

        # -- 1. score the forecast made at the close of bar t-1 ---------------
        if pend is not None and not is_dead:
            y = colors[t]
            a = acc[phase]
            if t > burn_in:
                a["n"] += 1
                a["green"] += y
                a["hits"] += 1 if ((pend["p"] >= 0.5) == (y == 1)) else 0
                a["brier"] += (pend["p"] - y) ** 2
                a["brier_ref"] += (pend["base"] - y) ** 2
                pc_ = min(max(pend["p"], 1e-6), 1 - 1e-6)
                a["ll"] += -(y * math.log(pc_) + (1 - y) * math.log(1 - pc_))
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
        # Both the outcome bar and every bar of its pattern must be live.
        if learn and t >= MAXN + 2 and not is_dead and clean(t - 1, nprev):
            cm.update(colors, t, 0)

        # -- 3. advance the EWMA, then forecast bar t+1 -----------------------
        # A dead bar must not drag the volatility baseline down with it.
        if not is_dead:
            sm.ew = rng if prev_ew is None else lam * prev_ew + (1 - lam) * rng

        pend = None
        if t >= MAXN + 3 and sm.ew and sm.ew > 0 and not is_dead and clean(t, nprev):
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

    out = {ph: _metrics(acc[ph]) for ph in PHASES}
    out["dead"] = {"n": n_dead, "pct": 100.0 * n_dead / max(nb, 1)}
    return out


def evaluate(bars, train=0.75, valid=0.20, **kw):
    """Two passes; see the docstring below."""
    """Full 75 / 20 / 5 protocol, which needs two passes.

    Pass 1 freezes at the end of TRAIN, so the VALID column is a clean read of
    the train-fitted model — that is the column you compare parameters on.
    Pass 2 freezes at the end of VALID, so the TEST column is read by a model
    fitted on everything before it, which is what live deployment looks like.
    TEST is never used to choose anything.
    """
    p1 = run(bars, train=train, valid=valid, freeze_at=train, **kw)
    p2 = run(bars, train=train, valid=valid, freeze_at=train + valid, **kw)
    return {"train": p1["train"], "valid": p1["valid"], "test": p2["test"],
            "dead": p1["dead"]}


COL_ROWS = [
    ("base rate P(green)",   "base_green", 100, "{:.2f}",  "%"),
    ("always-majority acc.", "majority",   100, "{:.2f}",  "%"),
    ("model accuracy",       "accuracy",   100, "{:.2f}",  "%"),
    ("edge over majority",   "edge",       100, "{:+.2f}", " pp"),
    ("  z-score",            "z",            1, "{:+.2f}", ""),
    ("Brier skill score",    "bss",          1, "{:+.5f}", ""),
]
SZ_ROWS = [
    ("MAE",               "mae",       1, "{:.5f}",  ""),
    ("MAE, plain EWMA",   "mae_naive", 1, "{:.5f}",  ""),
    ("skill vs EWMA",     "skill",   100, "{:+.2f}", "%"),
    ("MAPE",              "mape",      1, "{:.2f}",  "%"),
    ("80% band coverage", "coverage",  1, "{:.2f}",  "%"),
]


def _cell(m, key, scale, fmt, sfx):
    if not m.get("n") or key not in m:
        return "-"
    return fmt.format(m[key] * scale) + sfx


def report(name, res, cols=("train", "valid", "test")):
    if res.get("dead", {}).get("n"):
        d = res["dead"]
        print(f"\n  dead bars skipped: {d['n']:,} ({d['pct']:.1f}% of the file)")
    cols = [c for c in cols if res.get(c, {}).get("n")]
    if not cols:
        print(f"\n=== {name} ===\n  no scored bars")
        return
    w = 16
    print(f"\n=== {name} ===")
    print(f"  {'':26}" + "".join(f"{c.upper():>{w}}" for c in cols))
    print(f"  {'scored bars':26}" +
          "".join(f"{res[c]['n']:>{w},}" for c in cols))
    print("  -- colour " + "-" * (16 + w * len(cols)))
    for label, key, sc, fmt, sfx in COL_ROWS:
        print(f"  {label:26}" +
              "".join(f"{_cell(res[c], key, sc, fmt, sfx):>{w}}" for c in cols))
    if "n_size" in res[cols[0]]:
        print("  -- size " + "-" * (18 + w * len(cols)))
        for label, key, sc, fmt, sfx in SZ_ROWS:
            print(f"  {label:26}" +
                  "".join(f"{_cell(res[c], key, sc, fmt, sfx):>{w}}" for c in cols))


# -----------------------------------------------------------------------------
# tuning: select on VALID, read TEST exactly once
# -----------------------------------------------------------------------------
def _rank_of(values, target):
    """Percentile rank of `target` within `values`. 100 = best, 50 = mid-pack."""
    vals = [v for v in values if v is not None]
    if not vals:
        return float("nan")
    return 100.0 * (1.0 - sum(1 for v in vals if v > target) / len(vals))


def tune(bars, train=0.75, valid=0.20, **base_kw):
    kw = dict(base_kw, train=train, valid=valid)
    nb = len(bars)
    print("\n" + "=" * 74)
    print(f"TUNING — fit on the first {train*100:.0f}%, select on the next "
          f"{valid*100:.0f}%, read the last {(1-train-valid)*100:.0f}% once")
    print(f"         {int(nb*train)} train / {int(nb*valid)} valid / "
          f"{nb - int(nb*(train+valid))} test bars")
    print("=" * 74)

    def sweep(configs, apply_fn, metric, label, scale, fmt):
        results = [run(bars, **apply_fn(cfg), **kw, freeze_at=train)
                   for cfg in configs]
        tr = [r["train"].get(metric) for r in results]
        va = [r["valid"].get(metric) for r in results]
        best = max(range(len(configs)),
                   key=lambda i: va[i] if va[i] is not None else -9)
        tbest = max(range(len(configs)),
                    key=lambda i: tr[i] if tr[i] is not None else -9)
        print(f"\n{label} — selected on VALID: {configs[best]}")
        print(f"         valid {fmt.format(va[best]*scale)}   "
              f"(train {fmt.format(tr[best]*scale)})")
        lo = min(v for v in va if v is not None) * scale
        hi = max(v for v in va if v is not None) * scale
        print(f"         valid spread over {len(configs)} configs: "
              f"{fmt.format(lo)} .. {fmt.format(hi)}")
        print(f"         the TRAIN-best config would rank at the "
              f"{_rank_of(va, va[tbest]):.0f}th percentile on valid"
              f"   (~50th = tuning is noise)")
        return configs[best]

    n, sl = sweep([(n, sl) for n in (1, 2, 3, 4, 5) for sl in (10.0, 50.0, 200.0)],
                  lambda c: dict(nprev=c[0], s_link=c[1]),
                  "bss", "colour", 1, "{:+.5f}")
    lam, smu, sn = sweep([(lm, sm_, sn_) for lm in (0.90, 0.94, 0.97)
                          for sm_ in (10.0, 40.0, 100.0) for sn_ in (0, 1, 2, 3)],
                         lambda c: dict(lam=c[0], s_mult=c[1], size_n=c[2]),
                         "skill", "size  ", 100, "{:+.2f}%")

    best = evaluate(bars, nprev=n, s_link=sl, lam=lam, s_mult=smu, size_n=sn, **kw)
    report(f"SELECTED  N={n} s_link={sl:.0f} lambda={lam} shrink={smu:.0f} "
           f"size_n={sn}", best)
    print("\n  TEST is the only column that was never used to choose anything.")
    return best


# -----------------------------------------------------------------------------
# cross-symbol batch
# -----------------------------------------------------------------------------
def batch(paths, burn_in=200, basis="close_open", size_basis="range", **kw):
    """Plain walk-forward over every dataset, so small files stay well powered."""
    print(f"\n{'symbol':22}{'bars':>7}{'colour edge':>13}{'z':>7}"
          f"{'BSS':>10}{'size skill':>12}{'coverage':>10}{'dead':>9}")
    print("-" * 90)
    for path in paths:
        bars = load_ohlc(path)
        if len(bars) < 400:
            print(f"{os.path.basename(path):22}{len(bars):>7}   too few bars")
            continue
        res = run(bars, burn_in=burn_in, basis=basis, size_basis=size_basis,
                  train=1.0, valid=0.0, **kw)
        r = res["train"]
        print(f"{os.path.basename(path).replace('.csv',''):22}{r['n']:>7,}"
              f"{r['edge']*100:>+12.2f}%{r['z']:>7.2f}{r['bss']:>+10.5f}"
              f"{r.get('skill',0)*100:>+11.2f}%{r.get('coverage',0):>9.1f}%"
              f"{res['dead']['pct']:>8.1f}%")
    print("-" * 90)
    print("  colour edge = model accuracy minus always-predict-majority.")
    print("  |z| < 2 is noise. size skill = MAE reduction vs a plain EWMA.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="*", default=["data/es1_15m_tradingview.csv"])
    ap.add_argument("--nprev", type=int, default=3)
    ap.add_argument("--sweep", action="store_true",
                    help="run every pattern length 1..8 and compare")
    ap.add_argument("--split3", action="store_true",
                    help="three-way split: fit on train, select on valid, read "
                         "test once")
    ap.add_argument("--train", type=float, default=0.75, metavar="F")
    ap.add_argument("--valid", type=float, default=0.20, metavar="F")
    ap.add_argument("--tune", action="store_true",
                    help="grid on train, select on valid, read test once")
    ap.add_argument("--all", action="store_true",
                    help="walk-forward over every OHLC file in data/")
    ap.add_argument("--basis", choices=["close_open", "close_close"],
                    default="close_open")
    ap.add_argument("--size-basis", choices=["range", "truerange"],
                    default="range",
                    help="what the size model predicts: the visible high-low "
                         "range, or true range (includes the gap) which matters "
                         "on instruments that gap overnight")
    ap.add_argument("--dead-pct", type=float, default=5.0, metavar="P",
                    help="drop bars whose range is below P%% of the rolling "
                         "median range — synthetic weekend/closed-market bars. "
                         "0 disables the filter")
    ap.add_argument("--burn-in", type=int, default=500)
    args = ap.parse_args()

    if args.all:
        known = ["es1_15m_tradingview", "es1_3m_tradingview", "eurusd_1h",
                 "xauusd_1h", "btcusd_1h", "aapl_1h", "spy_1day"]
        paths = [f"data/{k}.csv" for k in known if os.path.exists(f"data/{k}.csv")]
        batch(paths, burn_in=min(args.burn_in, 200), basis=args.basis,
              size_basis=args.size_basis, nprev=args.nprev,
              dead_pct=args.dead_pct)
        return

    for path in args.csv:
        if not os.path.exists(path):
            sys.exit(f"no such file: {path}")
        bars = load_ohlc(path)
        print(f"\nloaded {len(bars)} bars from {path}  (basis: {args.basis}, "
              f"size: {args.size_basis})")
        kw = dict(burn_in=args.burn_in, basis=args.basis,
                  size_basis=args.size_basis, dead_pct=args.dead_pct)

        if args.tune:
            tune(bars, train=args.train, valid=args.valid, **kw)
        elif args.split3:
            report(f"N = {args.nprev}",
                   evaluate(bars, train=args.train, valid=args.valid,
                            nprev=args.nprev, **kw))
        elif args.sweep:
            for n in range(1, MAXN + 1):
                report(f"N = {n}", run(bars, nprev=n, train=1.0, valid=0.0, **kw),
                       cols=("train",))
        else:
            report(f"N = {args.nprev}",
                   run(bars, nprev=args.nprev, train=1.0, valid=0.0, **kw),
                   cols=("train",))


if __name__ == "__main__":
    main()
