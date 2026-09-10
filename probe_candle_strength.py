"""Measure the 'Next Candle Predictor' candle-strength formula.

Replicates the pasted Pine formula bar-for-bar, in its *intended* form (the
volume SMA computed correctly, which the Pine version does not do), and scores
its next-candle direction call against always-predicting-the-running-majority.

    strength_i = (body*bw + wick*ww) * (vol/avgvol) * vw * dir
    signal     = sign(mean(strength_1..len)) with a dead-zone threshold

Usage:
    python3 probe_candle_strength.py data/es1_15m_tradingview.csv
    python3 probe_candle_strength.py --all
"""
import csv, math, os, statistics, sys

BW, WW, VW = 0.5, 0.1, 0.5          # the script's defaults
DEAD_PCT   = 0.05                   # dead-bar filter, per DEV_NOTES lesson
DEAD_WIN   = 100


def load(path):
    bars = []
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh)
        cols = {k.lower(): k for k in rd.fieldnames}
        vkey = cols.get("volume")
        for row in rd:
            try:
                o = float(row[cols["open"]]); h = float(row[cols["high"]])
                l = float(row[cols["low"]]);  c = float(row[cols["close"]])
            except (ValueError, TypeError, KeyError):
                continue
            v = None
            if vkey:
                try:    v = float(row[vkey])
                except (ValueError, TypeError): v = None
            bars.append((o, h, l, c, v))
    return bars


def strength(o, h, l, c, v, avgvol):
    body = abs(c - o)
    wick = (h - l) - body
    d    = 1 if c > o else (-1 if c < o else 0)
    vf   = max(v / avgvol, 0.1) if (v and avgvol and avgvol > 0) else 1.0
    return (body * BW + wick * WW) * vf * VW * d


def atr(bars, n=14):
    """Wilder RMA of true range, causal. Used only to normalise the threshold."""
    out, prev = [], None
    for i, (o, h, l, c, v) in enumerate(bars):
        tr = (h - l) if i == 0 else max(h - l, abs(h - bars[i-1][3]), abs(l - bars[i-1][3]))
        prev = tr if prev is None else prev + (tr - prev) / n
        out.append(prev)
    return out


def run(bars, length, thresh_atr, lag_as_written, burn=200):
    """Walk forward. Returns per-bar (signal, realised_dir) for scored bars."""
    a = atr(bars)
    rng = [b[1] - b[2] for b in bars]
    recs = []
    up_ct = dn_ct = 0
    maj_hist = []
    for t in range(burn, len(bars) - 1):
        # --- dead-bar filter: exclude synthetic/stale bars from the window ---
        med = statistics.median(rng[max(0, t - DEAD_WIN):t]) or 0.0
        window = range(t - length, t) if lag_as_written else range(t - length + 1, t + 1)
        if any(rng[j] < DEAD_PCT * med for j in window) or rng[t + 1] < DEAD_PCT * med:
            continue
        # --- the formula ---
        tot = 0.0
        for j in window:
            avgvol = 0.0
            vs = [bars[k][4] for k in range(j - length + 1, j + 1) if bars[k][4] is not None]
            avgvol = max(sum(vs) / len(vs), 1.0) if vs else 0.0
            tot += strength(*bars[j], avgvol)
        avg = tot / length
        # scale-free threshold: strength carries price units, so gate on ATR
        gate = thresh_atr * a[t]
        sig = 1 if avg > gate else (-1 if avg < -gate else 0)
        # --- realised direction of the bar being forecast ---
        no, nc = bars[t + 1][0], bars[t + 1][3]
        real = 1 if nc > no else (-1 if nc < no else 0)
        if real == 0:
            continue
        # running majority baseline (expanding, per DEV_NOTES correction)
        maj = 1 if up_ct >= dn_ct else -1
        recs.append((sig, real, maj, abs(avg) / a[t] if a[t] else 0.0, rng[t + 1] / a[t] if a[t] else 0.0))
        if real > 0: up_ct += 1
        else:        dn_ct += 1
    return recs


def score(recs):
    act = [r for r in recs if r[0] != 0]
    if len(act) < 50:
        return None
    n    = len(act)
    mc   = [1 if s == r else 0 for s, r, m, _, _ in act]
    bc   = [1 if m == r else 0 for s, r, m, _, _ in act]
    acc  = sum(mc) / n
    base = sum(bc) / n
    d    = [x - y for x, y in zip(mc, bc)]
    md   = sum(d) / n
    sd   = statistics.pstdev(d) or 1e-12
    z    = md / (sd / math.sqrt(n))
    fire = n / len(recs)
    # does |strength| carry information about next-bar SIZE?
    xs = [r[3] for r in recs]; ys = [r[4] for r in recs]
    corr = 0.0
    if len(xs) > 100:
        mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
        sx = math.sqrt(sum((x-mx)**2 for x in xs)); sy = math.sqrt(sum((y-my)**2 for y in ys))
        if sx > 0 and sy > 0:
            corr = sum((x-mx)*(y-my) for x, y in zip(xs, ys)) / (sx*sy)
    return dict(n=n, acc=acc, base=base, edge=(acc-base)*100, z=z, fire=fire, corr=corr)


def main():
    args = sys.argv[1:]
    files = ([os.path.join("data", f) for f in sorted(os.listdir("data")) if f.endswith(".csv")]
             if "--all" in args else [a for a in args if not a.startswith("--")])
    files = [f for f in files if "trades" in f or True]
    print(f"{'file':<28}{'len':>4}{'thr':>7}{'n':>7}{'acc':>8}{'base':>8}{'edge':>8}{'z':>7}{'fire':>7}{'|s|~rng':>9}")
    print("-" * 93)
    for path in files:
        bars = load(path)
        if len(bars) < 600:
            continue
        for length in (3, 5, 10):
            for thr in (0.0, 0.05, 0.20):
                r = score(run(bars, length, thr, lag_as_written=False))
                if r is None:
                    continue
                print(f"{os.path.basename(path):<28}{length:>4}{thr:>7.2f}{r['n']:>7}"
                      f"{r['acc']*100:>7.2f}%{r['base']*100:>7.2f}%{r['edge']:>+8.2f}"
                      f"{r['z']:>+7.2f}{r['fire']*100:>6.0f}%{r['corr']:>+9.3f}")
        print()


if __name__ == "__main__":
    main()
