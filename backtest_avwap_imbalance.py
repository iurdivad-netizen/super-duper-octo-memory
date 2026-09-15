"""Port of avwap_imbalance_bullet_strategy.pine -- measures 1:4 geometry availability.

Answers one question: how often does the source's own setup actually offer 1:4,
and what is the hit rate when it does. Counters mirror the Pine dashboard.
"""
import csv, sys, math, argparse
from datetime import datetime, timedelta, timezone

def rma(vals, n):
    out, acc = [], None
    for i, v in enumerate(vals):
        if v is None: out.append(None); continue
        if acc is None:
            if i + 1 >= n:
                seed = [x for x in vals[i+1-n:i+1] if x is not None]
                acc = sum(seed)/len(seed) if len(seed) == n else None
            out.append(acc)
        else:
            acc = (acc*(n-1) + v)/n
            out.append(acc)
    return out

def load(path, tz_shift_hours=0):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            t = r["time"] if "time" in r else r["timestamp"]
            try:
                dt = datetime.fromisoformat(t)
            except ValueError:
                dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone(timedelta(hours=tz_shift_hours)))
            vol = r.get("Volume") or r.get("volume") or "0"
            def g(k):
                v = r.get(k, "")
                try: return float(v)
                except (TypeError, ValueError): return None
            rows.append(dict(dt=dt,
                             o=float(r["open"]), h=float(r["high"]),
                             l=float(r["low"]),  c=float(r["close"]),
                             v=float(vol or 0),
                             # TradingView-supplied reference series, when present
                             tv_vw=g("New York VWAP"),
                             tv_up1=g("VWAP_NY - STDEV +1"),
                             tv_dn1=g("VWAP_NY - STDEV -1")))
    rows.sort(key=lambda x: x["dt"])
    return rows

def run(rows, *, mode="reclaim", min_rr=4.0, sd_mult=1.0, disp_mult=1.0,
        need_body=True, max_wait=20, stop_buf_ticks=2.0, tick=0.25,
        point_value=20.0, bullet=1000.0, sess=(8*60+30, 9*60+30),
        slip_ticks=4.0, comm_per_side=2.04, reclaim_mid=False,
        stop_basis="auto", bias_on_entry=False, use_tv_vwap=False,
        anchor_hour=0, fixed_r_target=None, flat_eod=True):

    n = len(rows)
    tr = [None]*n
    for i in range(n):
        if i == 0: tr[i] = rows[i]["h"]-rows[i]["l"]
        else:
            pc = rows[i-1]["c"]
            tr[i] = max(rows[i]["h"]-rows[i]["l"], abs(rows[i]["h"]-pc), abs(rows[i]["l"]-pc))
    atr = rma(tr, 14)

    # anchored VWAP, reset at NY midnight (rows carry -04:00/-05:00 ET offsets)
    sPV = sV = sP2V = 0.0
    vw, sd = [None]*n, [None]*n
    prev_h = None
    for i, r in enumerate(rows):
        hh = r["dt"].hour
        if prev_h is None or (hh == anchor_hour and prev_h != anchor_hour):
            sPV = sV = sP2V = 0.0
        prev_h = hh
        p = (r["h"]+r["l"]+r["c"])/3.0
        sPV += p*r["v"]; sV += r["v"]; sP2V += p*p*r["v"]
        if sV > 0:
            vw[i] = sPV/sV
            sd[i] = math.sqrt(max(sP2V/sV - vw[i]*vw[i], 0.0))
    if use_tv_vwap:
        for i, r in enumerate(rows):
            vw[i] = r.get("tv_vw")
            u, d = r.get("tv_up1"), r.get("tv_dn1")
            sd[i] = ((u - d) / 2.0) if (u is not None and d is not None) else None

    C = dict(form=0, trig=0, rej_bias=0, rej_rr=0, rej_qty=0, taken=0,
             win=0, loss=0, tgt=0, stp=0, eod=0, pnl=0.0, sumR=0.0,
             rr_avail=[], risk_pts=[], days=set())

    # state
    lTop=lBot=lSw=None; lAge=0
    sTop=sBot=sSw=None; sAge=0
    pos=None  # dict(dir, entry, stop, tgt, qty, i)
    trades=[]

    for i in range(2, n):
        r = rows[i]
        mins = r["dt"].hour*60 + r["dt"].minute
        in_win = sess[0] <= mins < sess[1]
        h,l,c,o = r["h"],r["l"],r["c"],r["o"]
        h1,l1,c1,o1 = rows[i-1]["h"],rows[i-1]["l"],rows[i-1]["c"],rows[i-1]["o"]
        h2,l2 = rows[i-2]["h"],rows[i-2]["l"]

        # ---- manage open position (stop/target intrabar, stop wins ties) ----
        if pos:
            hit_stop = (l <= pos["stop"]) if pos["dir"]>0 else (h >= pos["stop"])
            hit_tgt  = (h >= pos["tgt"])  if pos["dir"]>0 else (l <= pos["tgt"])
            exit_px = None; why=None
            if hit_stop:
                exit_px = pos["stop"] - pos["dir"]*slip_ticks*tick; why="stop"
            elif hit_tgt:
                exit_px = pos["tgt"]; why="target"
            elif flat_eod and not in_win:
                exit_px = c; why="eod"
            if exit_px is not None:
                gross = pos["dir"]*(exit_px-pos["entry"])*point_value*pos["qty"]
                net = gross - 2*comm_per_side*pos["qty"]
                C["pnl"] += net; C["sumR"] += net/bullet
                C["win" if net>0 else "loss"] += 1
                C[{"stop":"stp","target":"tgt","eod":"eod"}[why]] += 1
                trades.append(dict(dt=pos["dt"], dir=pos["dir"], why=why, net=net,
                                   R=net/bullet, rr=pos["rr"], risk=pos["riskpts"]))
                pos=None

        disp_ok = (disp_mult<=0) or (atr[i-1] is None) or ((h1-l1) >= disp_mult*atr[i-1])
        bull_disp = (not need_body) or (c1 > o1)
        bear_disp = (not need_body) or (c1 < o1)
        upGap = (h2 < l) and disp_ok and bull_disp
        dnGap = (l2 > h) and disp_ok and bear_disp
        recl = (mode == "reclaim")

        formL = dnGap if recl else upGap
        formS = upGap if recl else dnGap
        if formL:
            lTop = l2 if recl else l
            lBot = h  if recl else h2
            lSw  = min(l, l1, l2); lAge = 0
        if formS:
            sTop = l  if recl else l2
            sBot = h2 if recl else h
            sSw  = max(h, h1, h2); sAge = 0
        if lTop is not None and not formL: lAge += 1
        if sTop is not None and not formS: sAge += 1
        if lTop is not None and (lAge > max_wait or c < lSw): lTop=lBot=lSw=None
        if sTop is not None and (sAge > max_wait or c > sSw): sTop=sBot=sSw=None

        if in_win and (formL or formS):
            C["form"] += 1; C["days"].add(r["dt"].date())

        use_seq = (stop_basis=="seq") or (stop_basis=="auto" and recl)

        for d in (1,-1):
            if d>0 and lTop is None: continue
            if d<0 and sTop is None: continue
            if d>0:
                lvl = (lTop+lBot)/2.0 if reclaim_mid else lTop
                fired = (c > lvl) and (c1 <= lvl)
                stop_ref = lSw if use_seq else lBot
                stop = stop_ref - stop_buf_ticks*tick
                risk = c - stop; rew = (vw[i]-c) if vw[i] else None
                bias_lvl = c if bias_on_entry else lvl
                bias = (sd[i] is not None) and bias_lvl < (vw[i]-sd_mult*sd[i])
            else:
                lvl = (sTop+sBot)/2.0 if reclaim_mid else sBot
                fired = (c < lvl) and (c1 >= lvl)
                stop_ref = sSw if use_seq else sTop
                stop = stop_ref + stop_buf_ticks*tick
                risk = stop - c; rew = (c-vw[i]) if vw[i] else None
                bias_lvl = c if bias_on_entry else lvl
                bias = (sd[i] is not None) and bias_lvl > (vw[i]+sd_mult*sd[i])
            if not (in_win and fired): continue
            C["trig"] += 1
            rr = (rew/risk) if (risk and risk>0 and rew is not None) else 0.0
            if not bias:
                C["rej_bias"] += 1; continue
            C["rr_avail"].append(rr); C["risk_pts"].append(risk)
            if rr < min_rr:
                C["rej_rr"] += 1; continue
            qty = min(int(bullet//(risk*point_value)), 50) if risk*point_value>0 else 0
            if qty < 1:
                C["rej_qty"] += 1; continue
            if pos is None and i+1 < n:
                ep = rows[i+1]["o"] + d*slip_ticks*tick
                tgt = (ep + d*fixed_r_target*risk) if fixed_r_target else vw[i]
                pos = dict(dir=d, entry=ep, stop=stop,
                           tgt=tgt, qty=qty, rr=rr, riskpts=risk, dt=r["dt"])
                C["taken"] += 1
    return C, trades

def report(name, C, trades, min_rr):
    nt = C["win"]+C["loss"]
    print(f"\n{'='*66}\n{name}\n{'='*66}")
    print(f"  sessions with a setup        {len(C['days'])}")
    print(f"  imbalances formed in window  {C['form']}")
    print(f"  reclaim triggers             {C['trig']}")
    print(f"    rejected - bias zone       {C['rej_bias']}")
    print(f"    rejected - no 1:{min_rr:g} geom     {C['rej_rr']}")
    print(f"    rejected - stop too wide   {C['rej_qty']}")
    print(f"  TRADES TAKEN                 {C['taken']}")
    if C["rr_avail"]:
        a = sorted(C["rr_avail"])
        pct = lambda q: a[min(int(q*len(a)), len(a)-1)]
        print(f"  available R:R at trigger (n={len(a)}):"
              f" med {pct(.5):.2f}  p75 {pct(.75):.2f}  p90 {pct(.9):.2f}  max {a[-1]:.2f}")
        print(f"    share offering >= 1:{min_rr:g}      {100*sum(1 for x in a if x>=min_rr)/len(a):.1f}%")
        rp = sorted(C["risk_pts"])
        print(f"  stop width (pts): med {rp[len(rp)//2]:.1f}  p90 {rp[int(.9*len(rp))]:.1f}")
    if nt:
        print(f"  closed {nt}  target {C['tgt']}  stop {C['stp']}  flat-eod {C['eod']}")
        print(f"  HIT RATE (target)            {100*C['tgt']/nt:.1f}%")
        print(f"  avg R                        {C['sumR']/nt:+.3f}")
        print(f"  net P&L                      ${C['pnl']:+,.0f}")
    else:
        print("  no closed trades")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("--name", default="")
    ap.add_argument("--tick", type=float, default=0.25)
    ap.add_argument("--pv", type=float, default=20.0)
    ap.add_argument("--slip", type=float, default=4.0)
    ap.add_argument("--comm", type=float, default=2.04)
    ap.add_argument("--minrr", type=float, default=4.0)
    ap.add_argument("--mode", default="reclaim")
    ap.add_argument("--dispmult", type=float, default=1.0)
    ap.add_argument("--maxwait", type=int, default=20)
    ap.add_argument("--stopbasis", default="auto")
    ap.add_argument("--mid", action="store_true")
    ap.add_argument("--biasentry", action="store_true")
    ap.add_argument("--sess", default="0830-0930")
    a = ap.parse_args()
    s,e = a.sess.split("-")
    sess = (int(s[:2])*60+int(s[2:]), int(e[:2])*60+int(e[2:]))
    rows = load(a.csv)
    C,T = run(rows, mode=a.mode, min_rr=a.minrr, tick=a.tick, point_value=a.pv,
              slip_ticks=a.slip, comm_per_side=a.comm, disp_mult=a.dispmult,
              max_wait=a.maxwait, stop_basis=a.stopbasis, reclaim_mid=a.mid,
              bias_on_entry=a.biasentry, sess=sess)
    report(a.name or f"{a.csv} mode={a.mode} minRR={a.minrr:g}", C, T, a.minrr)
