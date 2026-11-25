# -*- coding: utf-8 -*-
"""
_prosody5.py —— 照抄 ProsodyLM (arXiv 2507.20091, COLM 2025) 的词级五维韵律表示。

不自创 S/r/F/J。五维与论文 §3.1 一一对应：
  1. duration       词时长 (s)
  2. log_f0_range   词内 F0 动态范围 = log2(p90/p10)，输出半音 st
  3. log_f0_median  词级 F0 中位，减句内中位后输出 st（对应论文的 [SPK F0] 归一）
  4. log_f0_slope   词内 log-F0 对时间的最小二乘斜率，输出 st/s
  5. log_energy     词内有声段 RMS，输出 dBFS

关键实现约束（上一版踩过）：**F0 必须整句一次估完再按词切片**。
逐词建分析窗会在 0.24s 的词上给出 -600 st/s 这种荒谬斜率。

"词与词之间的差别" = 相邻两词五维向量之差 Δ5。

用法:
  python _prosody5.py c2_0191 --ver old
  python _prosody5.py c2_0191 --ver new
  python _prosody5.py --all --out _prosody5_all.json
"""
import sys, os, json, math, argparse
import numpy as np
import soundfile as sf
import parselmouth

HOP = 0.01
PITCH_FLOOR, PITCH_CEIL = 60.0, 350.0
MIN_SLOPE_DUR = 0.12       # 短于此不估斜率（采样点不足，斜率纯噪声）
VER = {
    "old": ("_audio_ch123/out", "_wl_out2.json"),
    "new": ("_regen_final", "_wl_final2.json"),
}


def load_words(tab_path, sid):
    d = json.load(open(tab_path, encoding="utf-8"))
    for k, v in d.items():
        if k.endswith("/" + sid):
            return v["words"]
    return None


def track(y, sr):
    """整句一次估 F0 + 能量，返回 (times, f0_hz, energy_db)。"""
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    pitch = snd.to_pitch(time_step=HOP, pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEIL)
    f0 = pitch.selected_array["frequency"].astype(float)
    t = pitch.xs()

    hop = int(HOP * sr)
    n = len(y) // hop
    e = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) + 1e-12 for i in range(n)])
    edb = 20 * np.log10(e)
    et = (np.arange(n) + 0.5) * HOP
    # 对齐到 F0 帧时间轴
    edb = np.interp(t, et, edb) if n > 1 else np.full_like(t, edb[0])
    return t, f0, edb


def word_feats(t, f0, edb, t0, t1):
    m = (t >= t0) & (t < t1)
    if m.sum() < 2:
        return {"dur": round(t1 - t0, 3), "f0_range_st": None, "f0_med_st": None,
                "f0_slope_st_s": None, "energy_db": None, "voiced_ratio": 0.0}
    dur = t1 - t0
    v = m & (f0 > 0)
    e_v = float(np.mean(edb[m]))
    energy_db = round((20 * math.log10(10 ** (e_v / 20))) if e_v > -90 else -90.0, 1)

    if v.sum() < 3:
        return {"dur": round(dur, 3), "f0_range_st": None, "f0_med_st": None,
                "f0_slope_st_s": None, "energy_db": energy_db,
                "voiced_ratio": round(float(v.sum() / m.sum()), 2)}

    tv, fv = t[v], f0[v]
    st = 12 * np.log2(fv / 100.0)
    p10, p50, p90 = np.percentile(st, [10, 50, 90])

    if dur >= MIN_SLOPE_DUR and tv[-1] - tv[0] > 0.05 and len(tv) >= 5:
        slope = float(np.polyfit(tv - tv[0], st, 1)[0]) * 12 / 12  # st per s
    else:
        slope = 0.0

    return {"dur": round(dur, 3),
            "f0_range_st": round(float(p90 - p10), 1),
            "f0_med_st": round(float(p50), 1),
            "f0_slope_st_s": round(slope, 1),
            "energy_db": energy_db,
            "voiced_ratio": round(float(v.sum() / m.sum()), 2)}


def run_sentence(sid, ver):
    wav_dir, tab = VER[ver]
    wav = os.path.join(wav_dir, sid + ".wav")
    if not os.path.exists(wav):
        return None
    words = load_words(tab, sid)
    if not words:
        return None
    y, sr = sf.read(wav, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    t, f0, edb = track(y, sr)

    feats = []
    for w in words:
        f = word_feats(t, f0, edb, w["start"], w["end"])
        f["w"] = w["w"]
        f["t0"], f["t1"] = round(w["start"], 2), round(w["end"], 2)
        feats.append(f)

    meds = [f["f0_med_st"] for f in feats if f["f0_med_st"] is not None]
    base = float(np.median(meds)) if meds else 0.0
    for f in feats:
        f["f0_med_rel"] = None if f["f0_med_st"] is None else round(f["f0_med_st"] - base, 1)

    pairs = []
    for a, b in zip(feats[:-1], feats[1:]):
        def d(k):
            return None if (a.get(k) is None or b.get(k) is None) else round(b[k] - a[k], 1)
        pairs.append({"w0": a["w"], "w1": b["w"],
                      "d_dur": d("dur"), "d_range": d("f0_range_st"),
                      "d_med": d("f0_med_rel"), "d_slope": d("f0_slope_st_s"),
                      "d_energy": d("energy_db")})
    return {"id": sid, "ver": ver, "words": feats, "pairs": pairs}


def show(r):
    print(f"\n=== {r['id']} / {r['ver']} ===")
    print(f"{'word':<13}{'t0':>6}{'dur':>6}{'F0med':>7}{'range':>7}{'slope':>8}{'energy':>8}{'vR':>5}")
    for f in r["words"]:
        g = lambda k: ("   n/a" if f[k] is None else f"{f[k]:>6}")
        print(f"{f['w']:<13}{f['t0']:>6.2f}{f['dur']:>6.2f}{g('f0_med_rel'):>7}"
              f"{g('f0_range_st'):>7}{g('f0_slope_st_s'):>8}{g('energy_db'):>8}{f['voiced_ratio']:>5.2f}")
    print("-- Δ5（Δmed/Δrange 单位 st，Δslope st/s，Δdur s，ΔE dB）")
    for p in r["pairs"]:
        g = lambda k: ("  n/a" if p[k] is None else f"{p[k]:+.1f}")
        print(f"  {p['w0']:<12}→ {p['w1']:<12} Δmed {g('d_med'):>6}  Δrng {g('d_range'):>6}"
              f"  Δslp {g('d_slope'):>7}  Δdur {g('d_dur'):>6}  ΔE {g('d_energy'):>6}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sid", nargs="?")
    ap.add_argument("--ver", default="new", choices=list(VER))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="_prosody5_all.json")
    a = ap.parse_args()

    if a.sid:
        r = run_sentence(a.sid, a.ver)
        if not r:
            print("missing:", a.sid, a.ver); sys.exit(1)
        show(r)
        json.dump(r, open(f"_prosody5_{a.sid}_{a.ver}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        return

    ids = [l.strip() for l in open("_narr_ids716.json", encoding="utf-8")
           .read().strip("[]\n ").replace('"', "").split(",") if l.strip()]
    out = {}
    for ver in ("old", "new"):
        n = 0
        for sid in ids:
            r = run_sentence(sid, ver)
            if r:
                out[f"{sid}|{ver}"] = r
                n += 1
        print(f"{ver}: {n} sentences")
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("→", a.out)


if __name__ == "__main__":
    main()
