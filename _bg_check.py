# -*- coding: utf-8 -*-
"""验证「背景起伏」是真实韵律，还是 F0 跟踪抖动造成的假象。
同一批词，用 4 套从敏感到保守的 F0 跟踪设置重算，看幅度怎么变。"""
import json, os, statistics as st, numpy as np, parselmouth

d = json.load(open('_align_dataset.json', encoding='utf-8'))
N = 30

SETS = [
    ("当前 0.01s/vt.20",  dict(time_step=0.01, voicing_threshold=0.20), 0,   0),
    ("平滑 0.02s/vt.30",  dict(time_step=0.02, voicing_threshold=0.30), 800, 0),
    ("平滑 0.03s/vt.45",  dict(time_step=0.03, voicing_threshold=0.45), 600, 10),
    ("保守 0.04s/vt.60",  dict(time_step=0.04, voicing_threshold=0.60), 500, 20),
]

def words_of(rec):
    return [(w["key"], float(w["t0"]), float(w["t1"]))
            for w in rec["words"]
            if w.get("t0") is not None and w.get("t1") is not None and w.get("key")]

def amp_of(pit, t0, t1):
    """词内 F0 的 max-min（半音）+ 有声帧数"""
    try:
        f = pit.selected_array["frequency"]
        ts = pit.xs()
        m = (ts >= t0) & (ts < t1)
        v = f[m]
        v = v[v > 0]
        if len(v) < 2:
            return None, len(v), int(m.sum())
        return 12 * np.log2(v.max() / v.min()), len(v), int(m.sum())
    except Exception:
        return None, 0, 0

def run(side, kind, limit):
    recs = [r for r in d["records"]
            if r["side"] == side and (kind is None or (r["take"] or {}).get("kind") == kind)]
    recs = recs[:limit]
    out = {}
    for tag, kw, lp, sm in SETS:
        adv_amp, oth_amp, cov = [], [], []
        for r in recs:
            p = os.path.join(".", r["wav"])
            if not os.path.exists(p):
                continue
            s = parselmouth.Sound(p)
            if lp:
                s = parselmouth.praat.call(s, "Filter (pass Hann band)...", 0, lp, 100)
            pit = s.to_pitch_ac(pitch_floor=60, pitch_ceiling=250,
                                octave_jump_cost=0.5, voiced_unvoiced_cost=0.2, **kw)
            if sm:
                pit = parselmouth.praat.call(pit, "Smooth", sm)
            adv = r.get("adv")
            for key, t0, t1 in words_of(r):
                a, nv, nt = amp_of(pit, t0, t1)
                if a is None:
                    continue
                cov.append(nv / max(1, nt))
                (adv_amp if (adv and key == adv) else oth_amp).append(a)
        out[tag] = dict(adv=st.median(adv_amp) if adv_amp else None,
                        oth=st.median(oth_amp) if oth_amp else None,
                        n_adv=len(adv_amp), n_oth=len(oth_amp),
                        cov=st.median(cov) if cov else 0)
    return out

print("=== 交付版（30 条）===")
A = run("narr", "delivered", N)
print("%-20s %8s %8s %8s %8s" % ("设置", "副词", "其他词", "差", "有声覆盖"))
for tag, v in A.items():
    if v["adv"] is None:
        continue
    print("%-20s %8.2f %8.2f %8.2f %7.0f%%" % (tag, v["adv"], v["oth"], v["adv"] - v["oth"], 100 * v["cov"]))

print()
print("=== 真人（30 句，用最长词 vs 其余）===")
recs = [r for r in d["records"] if r["side"] == "human"][:N]
for tag, kw, lp, sm in SETS:
    top, rest, cov = [], [], []
    for r in recs:
        p = os.path.join(".", r["wav"])
        if not os.path.exists(p):
            continue
        ws = [w for w in r["words"] if w.get("t0") is not None and w.get("rel_z") is not None]
        if len(ws) < 4:
            continue
        a = max(ws, key=lambda w: w["rel_z"])
        s = parselmouth.Sound(p)
        if lp:
            s = parselmouth.praat.call(s, "Filter (pass Hann band)...", 0, lp, 100)
        pit = s.to_pitch_ac(pitch_floor=60, pitch_ceiling=250,
                            octave_jump_cost=0.5, voiced_unvoiced_cost=0.2, **kw)
        if sm:
            pit = parselmouth.praat.call(pit, "Smooth", sm)
        for w in ws:
            amp, nv, nt = amp_of(pit, float(w["t0"]), float(w["t1"]))
            if amp is None:
                continue
            cov.append(nv / max(1, nt))
            (top if w is a else rest).append(amp)
    if top and rest:
        print("%-20s %8.2f %8.2f %8.2f %7.0f%%" % (tag, st.median(top), st.median(rest),
                                                   st.median(top) - st.median(rest), 100 * st.median(cov)))
