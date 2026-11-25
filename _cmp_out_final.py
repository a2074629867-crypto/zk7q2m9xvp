# -*- coding: utf-8 -*-
"""验收版(_audio_ch123/out, 统一0.70停顿) vs 三档版(_regen_final) 整库对比。

只读，不写音频。输出：
  1. 逐条 dur / 句内语速 / 停顿结构（碎停顿 <0.3s 处数、成整停顿 ≥0.3s 处数、停顿总长）
  2. voiced RMS 与方差
  3. 汇总分布 + 逐条胜负计数
"""
import json, os, sys, glob
import numpy as np
import soundfile as sf

sys.path.insert(0, r"G:\_setup")
from _speedlib import speech_time

OUT = r"G:\_setup\_audio_ch123\out"
FIN = r"G:\_setup\_regen_final"
WL_OUT = r"G:\_setup\_wl_words.json"
WL_FIN = r"G:\_setup\_wl_regen1123.json"


def gaps_detail(y, sr, pause_min=0.15, drop_db=20.0, floor_db=-60.0):
    fl = int(0.02 * sr)
    if len(y) < fl * 5:
        return []
    k = 1 + (len(y) - fl) // fl
    idx = np.arange(fl)[None, :] + fl * np.arange(k)[:, None]
    seg = y[idx].astype(np.float64)
    db = 20 * np.log10(np.sqrt((seg ** 2).mean(1)) + 1e-12)
    thr = max(floor_db, float(np.percentile(db, 90)) - drop_db)
    low = db < thr
    hop = fl / float(sr)
    runs, i, n = [], 0, len(low)
    while i < n:
        if low[i]:
            j = i
            while j < n and low[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    dur = len(y) / float(sr)
    out = []
    for a, b in runs:
        s, l = a * hop, (b - a) * hop
        if l < pause_min:
            continue
        if s <= 0.02 or s + l >= dur - 0.02:
            continue
        out.append(l)
    return out


def voiced_rms(y, sr):
    fl = int(0.02 * sr)
    k = 1 + (len(y) - fl) // fl
    idx = np.arange(fl)[None, :] + fl * np.arange(k)[:, None]
    seg = y[idx].astype(np.float64)
    rms = np.sqrt((seg ** 2).mean(1))
    db = 20 * np.log10(rms + 1e-12)
    v = rms[db > (np.percentile(db, 90) - 25)]
    if len(v) == 0:
        return -80.0
    return 20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)


def wc(path, table):
    o = json.load(open(table, encoding="utf-8"))
    v = o.get(path.replace("\\", "/"))
    if v is None:
        return None
    w = v["words"] if isinstance(v, dict) else v
    return len(w)


def measure(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    dur, sp, gs, mg, ld, tl = speech_time(y, sr)
    gd = gaps_detail(y, sr)
    frag = sum(1 for x in gd if x < 0.30)
    solid = sum(1 for x in gd if x >= 0.30)
    return dict(dur=dur, speech=sp, gap_sum=gs, maxgap=mg,
                nfrag=frag, nsolid=solid, ngap=len(gd),
                rms=voiced_rms(y, sr), sr=sr)


def main():
    ids = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(OUT, "*.wav")))
    rows = []
    miss = []
    for i, cid in enumerate(ids):
        po, pf = os.path.join(OUT, cid + ".wav"), os.path.join(FIN, cid + ".wav")
        if not os.path.exists(pf):
            miss.append(cid)
            continue
        a, b = measure(po), measure(pf)
        no, nf = wc(po, WL_OUT), wc(pf, WL_FIN)
        rows.append(dict(id=cid, n_old=no, n_new=nf,
                         wpm_old=(no / a["speech"] * 60 if no else None),
                         wpm_new=(nf / b["speech"] * 60 if nf else None),
                         old=a, new=b))
        if (i + 1) % 100 == 0:
            print("... %d/%d" % (i + 1, len(ids)), flush=True)

    def agg(key, src):
        v = [r[src][key] for r in rows if r[src][key] is not None]
        v = np.array(v, dtype=float)
        return (float(np.percentile(v, 10)), float(np.median(v)),
                float(np.percentile(v, 90)), float(v.mean()))

    print("\n=== N = %d  个共同条目；缺新版 %d 条 %s" % (len(rows), len(miss), miss[:8]))
    print("\n%-28s %10s %10s %10s %10s" % ("指标", "old p10/p50", "p90", "new p10/p50", "p90"))
    for key, name in [("dur", "总时长 s"), ("speech", "句内发声 s"),
                      ("gap_sum", "句内停顿总长 s"), ("maxgap", "最长停顿 s"),
                      ("nfrag", "碎停顿(<0.30s) 处"), ("nsolid", "成整停顿(>=0.30s) 处"),
                      ("rms", "voiced RMS dBFS")]:
        o, n = agg(key, "old"), agg(key, "new")
        print("%-28s %5.2f/%5.2f %10.2f %5.2f/%5.2f %10.2f"
              % (name, o[0], o[1], o[2], n[0], n[1], n[2]))

    for key, name, prec in [("wpm_old", "句中语速 wpm", 1)]:
        vo = np.array([r["wpm_old"] for r in rows if r["wpm_old"]], float)
        vn = np.array([r["wpm_new"] for r in rows if r["wpm_new"]], float)
        print("\n句中语速 wpm  old p10/p50/p90 = %.0f/%.0f/%.0f   new = %.0f/%.0f/%.0f"
              % (np.percentile(vo, 10), np.median(vo), np.percentile(vo, 90),
                 np.percentile(vn, 10), np.median(vn), np.percentile(vn, 90)))

    # RMS 跨度
    ro = np.array([r["old"]["rms"] for r in rows], float)
    rn = np.array([r["new"]["rms"] for r in rows], float)
    print("voiced RMS  中位 %.2f / 跨度(p5-p95) %.2f dB   新版 %.2f / %.2f dB"
          % (np.median(ro), np.percentile(ro, 95) - np.percentile(ro, 5),
             np.median(rn), np.percentile(rn, 95) - np.percentile(rn, 5)))

    # 胜负
    frag_better = sum(1 for r in rows if r["new"]["nfrag"] < r["old"]["nfrag"])
    frag_worse = sum(1 for r in rows if r["new"]["nfrag"] > r["old"]["nfrag"])
    print("\n碎停顿更少 %d 条 / 更多 %d 条 / 相同 %d 条"
          % (frag_better, frag_worse, len(rows) - frag_better - frag_worse))
    tot_frag_o = sum(r["old"]["nfrag"] for r in rows)
    tot_frag_n = sum(r["new"]["nfrag"] for r in rows)
    print("碎停顿总数  old %d  →  new %d  (%+.1f%%)"
          % (tot_frag_o, tot_frag_n, 100.0 * (tot_frag_n - tot_frag_o) / max(1, tot_frag_o)))

    # 逐条最差
    rows.sort(key=lambda r: r["new"]["nfrag"] - r["old"]["nfrag"], reverse=True)
    print("\n碎停顿变多最多的 8 条：")
    for r in rows[:8]:
        print("  %s  old %d → new %d" % (r["id"], r["old"]["nfrag"], r["new"]["nfrag"]))

    json.dump([{k: v for k, v in r.items()} for r in rows],
              open(r"G:\_setup\_cmp_out_final.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n已写 G:/_setup/_cmp_out_final.json")


if __name__ == "__main__":
    main()
