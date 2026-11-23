# -*- coding: utf-8 -*-
"""对白 vs 旁白的漂移特征零分布对比
目的：mt_seg_drift 的 CEN/SLP/HNR 阈值来自 180 条旁白零分布，
     用到对白上是否系统性偏严？用对白自身干净子集重建阈值。
"""
import json, os, statistics as st

P = "G:/_setup"
cache = json.load(open(os.path.join(P, "_drift_cache.json"), encoding="utf-8"))
gate = {x["wav"][:-4]: x for x in json.load(open(os.path.join(P, "_gate_dlg_v29.json"), encoding="utf-8"))}

# 干净子集：nat PASS + speaker PASS + scs 非 MANUAL
clean = set()
for sid, g in gate.items():
    gg = g["gates"]
    if gg.get("nat") == "PASS" and gg.get("speaker") == "PASS" and gg.get("scs") != "MANUAL":
        clean.add(sid)
print("对白干净子集 %d 条" % len(clean))


def pct(v, q):
    v = sorted(v)
    if not v:
        return None
    i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
    return v[i]


def collect(rows):
    cen, slp, hnr, rms = [], [], [], []
    for x in rows:
        for p in (x.get("pairs") or []):
            if p.get("dcen") is not None:
                cen.append(abs(p["dcen"]))
            if p.get("dslp") is not None:
                slp.append(abs(p["dslp"]))
            if p.get("dhnr") is not None:
                hnr.append(p["dhnr"])          # 只关心下降，取负值分布
            if p.get("drms") is not None:
                rms.append(abs(p["drms"]))
    return cen, slp, hnr, rms


dlg = [x for x in cache if x["n_win"] >= 3 and os.path.basename(x["file"])[:-4] in clean]
nar = [x for x in cache if x["n_win"] >= 3 and os.path.basename(x["file"])[:-4] not in gate]
print("对白可用 %d 条 / 旁白可用 %d 条" % (len(dlg), len(nar)))

for label, rows in (("对白(干净168)", dlg), ("旁白(全部)", nar)):
    cen, slp, hnr, rms = collect(rows)
    print("\n=== %s  窗对数 %d ===" % (label, len(cen)))
    for name, v, unit in (("|Δ谱质心比|", cen, ""), ("|Δ谱倾斜|", slp, "dB/kHz"), ("HNR降", hnr, "dB"), ("|ΔRMS|", rms, "dB")):
        if name == "HNR降":
            vv = [-x for x in v if x < 0]
            print("  %-12s n=%5d  p50 %.2f  p95 %.2f  p99 %.2f  p999 %.2f %s" %
                  (name, len(vv), pct(vv, .5) or 0, pct(vv, .95) or 0, pct(vv, .99) or 0, pct(vv, .999) or 0, unit))
        else:
            print("  %-12s n=%5d  p50 %.2f  p95 %.2f  p99 %.2f  p999 %.2f %s" %
                  (name, len(v), pct(v, .5), pct(v, .95), pct(v, .99), pct(v, .999), unit))

print("\n当前生产阈值（来自旁白 p99/p95）：CEN %.2f/%.2f  SLP %.1f/%.1f  HNR %.1f/%.1f" % (1.20, 0.89, 6.7, 4.8, 15.0, 9.0))
