# -*- coding: utf-8 -*-
"""看 c2_0191 在各版里的停顿明细（只读，不改任何东西）。"""
import json, sys, numpy as np, soundfile as sf

ID = "c2_0191"


def gaps(path, pause_min=0.15, drop_db=20.0, floor_db=-60.0):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    fl = int(0.02 * sr)
    k = 1 + (len(y) - fl) // fl
    idx = np.arange(fl)[None, :] + fl * np.arange(k)[:, None]
    seg = y[idx].astype(np.float64)
    db = 20 * np.log10(np.sqrt((seg ** 2).mean(1)) + 1e-12)
    thr = max(floor_db, float(np.percentile(db, 90)) - drop_db)
    low = db < thr
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
    hop = fl / float(sr)
    out = [(a * hop, (b - a) * hop) for a, b in runs if (b - a) * hop >= pause_min]
    return len(y) / float(sr), sr, out, thr


def show(tag, path):
    d, sr, g, thr = gaps(path)
    print("--- %s  %s" % (tag, path))
    print("    dur %.3fs  sr %d  thr %.1fdBFS  gaps %d" % (d, sr, thr, len(g)))
    inner = [(s, l) for s, l in g if s > 0.02 and s + l < d - 0.02]
    for s, l in inner:
        print("      %6.3f → %6.3f  %5.3fs" % (s, s + l, l))
    if inner:
        vals = [l for _, l in inner]
        print("    inner n=%d  sum=%.3f  min=%.3f max=%.3f" % (len(vals), sum(vals), min(vals), max(vals)))
    print()


def jfind(p):
    if not __import__("os").path.exists(p):
        print("MISS", p)
        return None
    o = json.load(open(p, encoding="utf-8"))
    if isinstance(o, dict):
        for k in (ID, ID + ".wav"):
            if k in o:
                return k, o[k]
        # 可能是 {items:[...]} 或 {cond_id: {...}}
        for k, v in o.items():
            if isinstance(v, dict) and v.get("id") == ID:
                return k, v
        print("  未在 dict 里找到，top keys:", list(o.keys())[:6])
    elif isinstance(o, list):
        for it in o:
            if isinstance(it, dict) and it.get("id") == ID:
                return "list", it
        print("  未在 list 里找到，len=", len(o))
    return None


for p in [r"G:\_setup\_pause_norm_report.json",
          r"G:\_setup\pause_llm_narr_v3.json",
          r"G:\_setup\_pause_regen1123_report.json"]:
    print("=" * 70)
    print("JSON:", p)
    r = jfind(p)
    if r:
        k, v = r
        s = json.dumps(v, ensure_ascii=False)
        print("  key=%s  len=%d" % (k, len(s)))
        print("  " + s[:1500])
    print()

for tag, p in [("验收版 out(统一0.70)", r"G:\_setup\_audio_ch123\out\c2_0191.wav"),
               ("新库 norm(无三档)", r"G:\_setup\_regen_1123_norm\c2_0191.wav"),
               ("新库 norm_paused(三档)", r"G:\_setup\_regen_1123_norm_paused\c2_0191.wav"),
               ("_regen_final", r"G:\_setup\_regen_final\c2_0191.wav")]:
    show(tag, p)
