"""Reference implementation for candle_forecast_v2.pine.

A bar-by-bar mirror of the Pine script: same feature definitions, same online
updates, same predict-then-update ordering, same phase boundaries.  Pure
stdlib, so it runs anywhere; the loop is deliberately written the way Pine
executes rather than vectorised, because the point is fidelity, not speed.

    python3 backtest_candle_forecast_v2.py data/es1_15m_tradingview.csv
    python3 backtest_candle_forecast_v2.py --all
    python3 backtest_candle_forecast_v2.py data/spy_1day.csv --ablate
"""
import argparse
import csv
import math
import os
import sys

# --------------------------------------------------------------------------
# constants shared with the Pine script -- change in both places or not at all
# --------------------------------------------------------------------------
ATR_LEN      = 14
STOCH_LEN    = 20
MOM_SLOW     = 20
MOM_FAST     = 5
VOL_LEN      = 20
ACORR_LEN    = 50
MEDIAN_LEN   = 100
NFEAT        = 17          # 16 features + bias

F_NAMES = ["bias", "ret1", "ret2", "ret3", "mom5", "mom20", "clsPos", "rngRatio",
           "wickSkew", "stochPos", "runLen", "volZ", "gap", "acorr", "bodyFrac",
           "mom5xAc", "stochxAc"]


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def load(path):
    """Return list of (time, o, h, l, c, v).  v is None when the feed has none."""
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
                try:
                    v = float(row[vkey])
                except (ValueError, TypeError):
                    v = None
            bars.append((row[cols["time"]], o, h, l, c, v))
    return bars


# --------------------------------------------------------------------------
# small online primitives -- each has a direct Pine counterpart
# --------------------------------------------------------------------------
class Welford:
    """Running mean/variance.  Feeds the per-feature z-score normaliser that
    makes the model portable across instruments and timeframes."""
    __slots__ = ("n", "mean", "m2")

    def __init__(self):
        self.n = 0; self.mean = 0.0; self.m2 = 0.0

    def push(self, x):
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.m2 += d * (x - self.mean)

    def sd(self):
        return math.sqrt(self.m2 / (self.n - 1)) if self.n > 1 else 0.0


class Ring:
    """Fixed-size circular buffer.  Pine uses a plain float array the same way."""
    __slots__ = ("buf", "cap", "idx", "n")

    def __init__(self, cap):
        self.buf = [0.0] * cap; self.cap = cap; self.idx = 0; self.n = 0

    def push(self, x):
        self.buf[self.idx] = x
        self.idx = (self.idx + 1) % self.cap
        if self.n < self.cap:
            self.n += 1

    def values(self):
        return self.buf[:self.n]

    def quantile(self, q):
        if self.n == 0:
            return float("nan")
        s = sorted(self.values())
        pos = q * (len(s) - 1)
        lo = int(math.floor(pos)); hi = min(lo + 1, len(s) - 1)
        return s[lo] + (s[hi] - s[lo]) * (pos - lo)

    def median(self):
        return self.quantile(0.5)


def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z)) if z < 700 else 1.0
    e = math.exp(z) if z > -700 else 0.0
    return e / (1.0 + e)


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


# --------------------------------------------------------------------------
# metric accumulator, one per phase
# --------------------------------------------------------------------------
class Score:
    def __init__(self):
        self.n = 0
        self.hit = 0            # model correct
        self.baseHit = 0        # majority-baseline correct
        self.dSum = 0.0         # paired difference, model - baseline
        self.dSq = 0.0
        self.green = 0
        self.ll = 0.0           # model log-loss
        self.ll0 = 0.0          # base-rate log-loss
        self.br = 0.0           # model Brier
        self.br0 = 0.0
        self.sizeAbs = 0.0      # |pred - actual| / atr
        self.baseAbs = 0.0      # |ewma - actual| / atr
        self.altAbs  = [0.0, 0.0, 0.0]   # |alt baseline - actual| / atr
        self.cover = 0
        self.coverN = 0
        # confidence-gated subset
        self.cn = 0
        self.chit = 0

    def add(self, y, p, pbase, majority, sizeErr, baseErr, inBand, conf_gate, altErr=None):
        self.n += 1
        self.green += y
        mHit = 1 if ((p > 0.5) == (y == 1)) else 0
        bHit = 1 if (majority == y) else 0
        self.hit += mHit
        self.baseHit += bHit
        d = mHit - bHit
        self.dSum += d
        self.dSq += d * d
        eps = 1e-12
        self.ll -= math.log(max(p if y else 1.0 - p, eps))
        self.ll0 -= math.log(max(pbase if y else 1.0 - pbase, eps))
        self.br += (p - y) ** 2
        self.br0 += (pbase - y) ** 2
        self.sizeAbs += sizeErr
        self.baseAbs += baseErr
        if altErr:
            for k in range(3):
                self.altAbs[k] += altErr[k]
        if inBand is not None:
            self.coverN += 1
            self.cover += 1 if inBand else 0
        if conf_gate:
            self.cn += 1
            self.chit += mHit

    # -- derived ----------------------------------------------------------
    @property
    def acc(self):        return self.hit / self.n if self.n else float("nan")
    @property
    def baseAcc(self):    return self.baseHit / self.n if self.n else float("nan")
    @property
    def edge(self):       return self.acc - self.baseAcc

    @property
    def z(self):
        """Paired z on the per-bar correctness difference vs the majority rule."""
        if self.n < 2:
            return float("nan")
        m = self.dSum / self.n
        var = (self.dSq - self.n * m * m) / (self.n - 1)
        if var <= 0:
            return 0.0
        return m / math.sqrt(var / self.n)

    @property
    def llSkill(self):    return 1.0 - self.ll / self.ll0 if self.ll0 else float("nan")
    @property
    def bss(self):        return 1.0 - self.br / self.br0 if self.br0 else float("nan")
    @property
    def sizeSkill(self):
        return 1.0 - self.sizeAbs / self.baseAbs if self.baseAbs else float("nan")
    def altSkill(self, k):
        return 1.0 - self.sizeAbs / self.altAbs[k] if self.altAbs[k] else float("nan")
    @property
    def coverage(self):   return self.cover / self.coverN if self.coverN else float("nan")
    @property
    def confAcc(self):    return self.chit / self.cn if self.cn else float("nan")


# --------------------------------------------------------------------------
# the model
# --------------------------------------------------------------------------
class Forecaster:
    def __init__(self, cfg):
        self.cfg = cfg
        self.w  = [0.0] * NFEAT          # direction weights
        self.g2 = [0.0] * NFEAT          # AdaGrad accumulators
        self.sw  = [0.0] * NFEAT         # size weights
        self.sg2 = [0.0] * NFEAT
        self.norm = [Welford() for _ in range(NFEAT)]
        self.platt_a = 1.0
        self.platt_b = 0.0

    # -- feature standardisation -----------------------------------------
    def standardise(self, raw):
        out = [0.0] * NFEAT
        out[0] = 1.0                                   # bias, never normalised
        for i in range(1, NFEAT):
            w = self.norm[i]
            sd = w.sd()
            out[i] = 0.0 if sd <= 1e-12 else clamp((raw[i] - w.mean) / sd, -5.0, 5.0)
        return out

    def observe(self, raw):
        for i in range(1, NFEAT):
            self.norm[i].push(raw[i])

    # -- forward ----------------------------------------------------------
    def logit(self, xs):
        return sum(self.w[i] * xs[i] for i in range(NFEAT))

    def pdir(self, xs, calibrated):
        z = self.logit(xs)
        if calibrated:
            z = self.platt_a * z + self.platt_b
        return sigmoid(z)

    def psize(self, xs):
        return sum(self.sw[i] * xs[i] for i in range(NFEAT))

    # -- online updates ---------------------------------------------------
    def update_dir(self, xs, y, bias_only=False):
        p = sigmoid(self.logit(xs))
        err = p - y
        lr, l2 = self.cfg.lr, self.cfg.l2
        # The intercept is state, not a fitted parameter: the unconditional
        # green rate drifts, and a frozen intercept would forecast the training
        # window's drift forever.  It keeps updating in every phase, exactly as
        # the range EWMA does -- otherwise the model loses to the majority rule
        # for a reason that has nothing to do with its features.
        rng = range(1) if bias_only else range(NFEAT)
        for i in rng:
            g = err * xs[i] + (l2 * self.w[i] if i else 0.0)
            self.g2[i] += g * g
            self.w[i] -= lr * g / (math.sqrt(self.g2[i]) + 1e-8)

    def update_size(self, xs, target):
        err = self.psize(xs) - target
        lr, l2 = self.cfg.slr, self.cfg.l2
        for i in range(NFEAT):
            g = err * xs[i] + (l2 * self.sw[i] if i else 0.0)
            self.sg2[i] += g * g
            self.sw[i] -= lr * g / (math.sqrt(self.sg2[i]) + 1e-8)

    def update_platt(self, z, y):
        p = sigmoid(self.platt_a * z + self.platt_b)
        err = p - y
        lr = self.cfg.plr
        self.platt_a -= lr * err * z
        self.platt_b -= lr * err


class Cfg:
    def __init__(self, **kw):
        self.lr       = kw.get("lr", 0.10)
        self.slr      = kw.get("slr", 0.05)
        self.plr      = kw.get("plr", 0.02)
        self.l2       = kw.get("l2", 1e-2)
        self.lam      = kw.get("lam", 0.94)
        self.burnin   = kw.get("burnin", 200)
        self.trainPct = kw.get("trainPct", 0.75)
        self.testPct  = kw.get("testPct", 0.20)
        self.deadPct  = kw.get("deadPct", 0.05)
        self.basis    = kw.get("basis", "co")     # co | cc
        self.bandWin  = kw.get("bandWin", 500)
        self.bandQ    = kw.get("bandQ", 0.10)
        self.confZ    = kw.get("confZ", 0.02)     # |p-0.5| gate for the conf row
        self.freeze   = kw.get("freeze", True)
        self.drop     = kw.get("drop", set())     # feature indices to zero out


# --------------------------------------------------------------------------
# the bar loop
# --------------------------------------------------------------------------
def run(bars, cfg):
    n = len(bars)
    if n < cfg.burnin + 100:
        return None

    last_idx  = n - 1
    train_end = int(round(last_idx * cfg.trainPct))
    test_end  = int(round(last_idx * (cfg.trainPct + cfg.testPct)))

    m = Forecaster(cfg)
    phases = {"TRAIN": Score(), "TEST": Score(), "CALIB": Score()}

    # rolling state
    atr = None
    ewma = None
    ewfast = None            # lambda 0.90 -- a much less lazy baseline
    prev_tr = None
    prev_c = None
    closes, highs, lows = [], [], []
    vol_sum, vol_hist = 0.0, []
    run_len = 0
    acorr_ring = Ring(ACORR_LEN)
    med_ring   = Ring(MEDIAN_LEN)
    band_ring  = Ring(cfg.bandWin)
    body_hist  = []          # last few signed bodies for lagged returns
    dead_count = 0
    scored_gate = 0

    # forecast locked at the previous close
    pend = None              # (xs, p, z, predRange, ewma_at_lock, atr_at_lock, lo, hi)
    green_seen, green_tot = 0, 0

    for i, (t, o, h, l, c, v) in enumerate(bars):
        rng  = h - l
        tr   = rng if prev_c is None else max(rng, abs(h - prev_c), abs(l - prev_c))
        atr  = tr if atr is None else atr + (tr - atr) / ATR_LEN          # Wilder RMA
        ewma = tr if ewma is None else cfg.lam * ewma + (1 - cfg.lam) * tr
        ewfast = tr if ewfast is None else 0.90 * ewfast + 0.10 * tr

        med_ring.push(rng)
        med = med_ring.median()
        dead = med_ring.n >= 20 and med > 0 and rng < cfg.deadPct * med
        if dead:
            dead_count += 1

        # ---- 1. score the forecast locked at the previous close ---------
        if pend is not None and not dead and atr > 0:
            xs_p, p_p, z_p, predR, ew_p, atr_p, lo_p, hi_p, ewf_p, ptr_p = pend
            y = 1 if (c > o if cfg.basis == "co" else (prev_c is not None and c > prev_c)) else 0
            pbase = (green_seen + 0.5) / (green_tot + 1.0)
            majority = 1 if pbase >= 0.5 else 0
            sizeErr = abs(predR - tr) / atr_p
            baseErr = abs(ew_p - tr) / atr_p
            inBand  = (lo_p <= tr <= hi_p) if not math.isnan(lo_p) else None
            altErr = [abs(ewf_p - tr) / atr_p,                 # EWMA(0.90)
                      abs(atr_p - tr) / atr_p,                 # ATR(14) itself
                      abs((ptr_p if ptr_p else atr_p) - tr) / atr_p]   # last TR
            phase = "TRAIN" if i <= train_end else "TEST" if i <= test_end else "CALIB"
            gate = abs(p_p - 0.5) >= cfg.confZ
            phases[phase].add(y, p_p, pbase, majority, sizeErr, baseErr, inBand, gate, altErr)
            if gate:
                scored_gate += 1

            # ---- 2. learn from it, in the right window ------------------
            learning = (i <= train_end) or (not cfg.freeze)
            if learning:
                m.update_dir(xs_p, y)
                if ew_p > 0:
                    m.update_size(xs_p, math.log(max(tr, 1e-12) / ew_p))
            else:
                m.update_dir(xs_p, y, bias_only=True)
                if i > test_end:
                    m.update_platt(z_p, y)       # 5% window recalibrates only

            # band error ratio, always live
            if predR > 0:
                band_ring.push(tr / predR)
            green_seen += y
            green_tot += 1

        # ---- 3. build this bar's features -------------------------------
        closes.append(c); highs.append(h); lows.append(l)
        body = c - o
        body_hist.append(body)
        if v is not None:
            vol_hist.append(v); vol_sum += v
            if len(vol_hist) > VOL_LEN:
                vol_sum -= vol_hist.pop(0)

        if True:
            sgn = 1 if body > 0 else -1 if body < 0 else 0
            prev_sgn = 0
            if len(body_hist) > 1:
                pb = body_hist[-2]
                prev_sgn = 1 if pb > 0 else -1 if pb < 0 else 0
            run_len = (run_len + sgn) if sgn != 0 and sgn == prev_sgn else sgn
            run_len = clamp(run_len, -8, 8)
            acorr_ring.push(float(sgn * prev_sgn))

        raw = [0.0] * NFEAT
        ok = atr > 0 and i >= max(MOM_SLOW, ACORR_LEN)
        if ok:
            uw = h - max(o, c); lw = min(o, c) - l
            raw[0]  = 1.0
            raw[1]  = body / atr
            raw[2]  = body_hist[-2] / atr if len(body_hist) > 1 else 0.0
            raw[3]  = body_hist[-3] / atr if len(body_hist) > 2 else 0.0
            raw[4]  = (c - closes[-1 - MOM_FAST]) / atr
            raw[5]  = (c - closes[-1 - MOM_SLOW]) / atr
            raw[6]  = (2.0 * (c - l) / rng - 1.0) if rng > 0 else 0.0
            raw[7]  = math.log(max(rng, 1e-12) / atr) if rng > 0 else -5.0
            raw[8]  = ((uw - lw) / rng) if rng > 0 else 0.0
            hh = max(highs[-STOCH_LEN:]); ll = min(lows[-STOCH_LEN:])
            raw[9]  = (2.0 * (c - ll) / (hh - ll) - 1.0) if hh > ll else 0.0
            raw[10] = run_len / 8.0
            vavg = vol_sum / len(vol_hist) if vol_hist else 0.0
            raw[11] = math.log(max(v, 1.0) / max(vavg, 1.0)) if (v is not None and vavg > 0) else 0.0
            raw[12] = (o - prev_c) / atr if prev_c is not None else 0.0
            ac = sum(acorr_ring.values()) / acorr_ring.n if acorr_ring.n else 0.0
            raw[13] = ac
            raw[14] = (abs(body) / rng) if rng > 0 else 0.0
            raw[15] = raw[4] * ac
            raw[16] = raw[9] * ac
            for d in cfg.drop:
                raw[d] = 0.0

        # ---- 4. lock the forecast for the next bar ----------------------
        pend = None
        if ok and not dead and m.norm[1].n >= cfg.burnin:
            xs = m.standardise(raw)
            m.observe(raw)
            z = m.logit(xs)
            calibrated = i > test_end or not cfg.freeze
            p = sigmoid(m.platt_a * z + m.platt_b) if calibrated else sigmoid(z)
            predR = ewma * math.exp(clamp(m.psize(xs), -1.5, 1.5))
            lo = hi = float("nan")
            if band_ring.n >= 50:
                lo = predR * band_ring.quantile(cfg.bandQ)
                hi = predR * band_ring.quantile(1.0 - cfg.bandQ)
            pend = (xs, p, z, predR, ewma, atr, lo, hi, ewfast, prev_tr)
        elif ok:
            m.observe(raw)

        prev_c = c
        prev_tr = tr

    return {
        "phases": phases, "model": m, "bars": n,
        "train_end": train_end, "test_end": test_end,
        "dead": dead_count / n if n else 0.0,
    }


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def fmt_phase(name, s):
    if s.n == 0:
        return f"  {name:<7} (no scored bars)"
    return (f"  {name:<7} n={s.n:>6}  acc {s.acc*100:6.2f}%  "
            f"base {s.baseAcc*100:6.2f}%  edge {s.edge*100:+5.2f}pp  z {s.z:+5.2f}  "
            f"LL-skill {s.llSkill:+.5f}  BSS {s.bss:+.5f}  "
            f"size {s.sizeSkill*100:+6.2f}%  cover {s.coverage*100:5.1f}%")


def verdict(s):
    if s.n < 200:
        return "INSUFFICIENT DATA"
    if s.z > 2.0 and s.llSkill > 0:
        return "DIRECTION: edge present"
    if s.z < -2.0:
        return "DIRECTION: worse than the trivial rule"
    return "DIRECTION: no edge (as expected)"


def report(path, res, cfg, show_weights=False):
    p = res["phases"]
    print(f"\n{os.path.basename(path)}  —  {res['bars']} bars, "
          f"train<={res['train_end']}, test<={res['test_end']}, "
          f"dead {res['dead']*100:.1f}%")
    for k in ("TRAIN", "TEST", "CALIB"):
        print(fmt_phase(k, p[k]))
    t = p["TEST"]
    print(f"  -> {verdict(t)}")
    if t.n:
        print(f"  size MAE reduction vs   EWMA(l={cfg.lam})  {t.sizeSkill*100:+6.2f}%"
              f"   EWMA(0.90) {t.altSkill(0)*100:+6.2f}%"
              f"   ATR(14) {t.altSkill(1)*100:+6.2f}%"
              f"   last TR {t.altSkill(2)*100:+6.2f}%")
        sz = "SIZE: real skill" if t.altSkill(1) > 0.02 else "SIZE: no material skill"
        print(f"  -> {sz} ({t.altSkill(1)*100:+.2f}% MAE vs ATR(14), "
              f"band coverage {t.coverage*100:.1f}% vs {100*(1-2*cfg.bandQ):.0f}% target)")
    if show_weights:
        m = res["model"]
        print("  direction weights (|w| desc):")
        order = sorted(range(NFEAT), key=lambda i: -abs(m.w[i]))
        for i in order[:8]:
            print(f"      {F_NAMES[i]:<10} {m.w[i]:+.4f}")
        print("  size weights (|w| desc):")
        order = sorted(range(NFEAT), key=lambda i: -abs(m.sw[i]))
        for i in order[:8]:
            print(f"      {F_NAMES[i]:<10} {m.sw[i]:+.4f}")
        print(f"  platt: a={m.platt_a:.4f} b={m.platt_b:+.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--weights", action="store_true")
    ap.add_argument("--ablate", action="store_true")
    ap.add_argument("--nofreeze", action="store_true")
    ap.add_argument("--basis", default="co", choices=["co", "cc"])
    ap.add_argument("--lr", type=float, default=0.10)
    ap.add_argument("--slr", type=float, default=0.05)
    ap.add_argument("--l2", type=float, default=1e-2)
    ap.add_argument("--lam", type=float, default=0.94)
    ap.add_argument("--dead-pct", type=float, default=0.05)
    a = ap.parse_args()

    kw = dict(basis=a.basis, lr=a.lr, slr=a.slr, l2=a.l2, lam=a.lam,
              deadPct=a.dead_pct, freeze=not a.nofreeze)
    cfg = Cfg(**kw)

    if a.all:
        files = sorted(f for f in os.listdir("data") if f.endswith(".csv"))
        print(f"{'file':<26}{'bars':>7}{'edge':>9}{'z':>7}{'LLskill':>10}"
              f"{'size':>9}{'cover':>8}   verdict")
        for f in files:
            bars = load(os.path.join("data", f))
            res = run(bars, Cfg(**kw))
            if not res:
                print(f"{f:<26}{len(bars):>7}   (too short)")
                continue
            t = res["phases"]["TEST"]
            if t.n == 0:
                print(f"{f:<26}{len(bars):>7}   (no scored test bars)")
                continue
            print(f"{f:<26}{res['bars']:>7}{t.edge*100:>+8.2f}%{t.z:>+7.2f}"
                  f"{t.llSkill:>+10.5f}{t.altSkill(1)*100:>+8.2f}%{t.coverage*100:>7.1f}%"
                  f"   {verdict(t)}")
        return

    if not a.csv:
        ap.error("give a csv or --all")

    bars = load(a.csv)
    res = run(bars, cfg)
    if not res:
        print("too few bars"); sys.exit(1)
    report(a.csv, res, cfg, show_weights=a.weights)

    if a.ablate:
        base = res["phases"]["TEST"]
        print("\n  ablation — TEST log-loss skill when each feature is zeroed:")
        print(f"      {'(none)':<12} {base.llSkill:+.5f}   size {base.sizeSkill*100:+6.2f}%")
        for i in range(1, NFEAT):
            c2 = Cfg(**kw); c2.drop = {i}
            r2 = run(bars, c2)
            t2 = r2["phases"]["TEST"]
            print(f"      {F_NAMES[i]:<12} {t2.llSkill:+.5f}   size {t2.sizeSkill*100:+6.2f}%"
                  f"   (Δ {(t2.llSkill-base.llSkill):+.5f} / "
                  f"{(t2.sizeSkill-base.sizeSkill)*100:+.2f}pp)")


if __name__ == "__main__":
    main()
