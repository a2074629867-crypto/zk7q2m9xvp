# -*- coding: utf-8 -*-
"""口径校准：哪一版 energy_span 才能复现文档里的数字。

文档基准（REQUIREMENTS §28，2026-10-29 实测）：
  真人 ref_human 159 条  p05/p50/p95 = 26.5 / 36.5 / 38.7
  我们旁白 716 条        p50 = 25.1（同一口径下）
NPT=21，每槽取 p90，span = 极差。

四个候选口径：
  V1 现版：只留「相对最大槽 25dB 内」的语音槽（2026-11-11 改的）
  V2 全槽：21 槽全算，不剔除任何槽（原始定义）
  V3 补噪：数字静音填到 −58dBFS 后，21 槽全算（§25b 生产链口径）
  V4 补噪+剔槽：先补到 −58，再按 25dB 剔槽
哪一版能把「真人 p50≈36.5、我们≈25.1」同时对上，就是被标定过的口径。
"""
import glob
import json

import numpy as np
import soundfile as sf

NPT = 21


def frame_db(x, sr, fl=0.02, hop=0.02):
    n = int(fl * sr)
    h = int(hop * sr)
    if len(x) < n:
        return np.array([-200.0])
    k = 1 + (len(x) - n) // h
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    seg = x[idx]
    rms = np.sqrt((seg.astype(np.float64) ** 2).mean(1)) + 1e-12
    return 20 * np.log10(rms)


def prof_of(db):
    p = []
    for i in range(NPT):
        a = int(i * len(db) / NPT)
        b = max(a + 1, int((i + 1) * len(db) / NPT))
        p.append(float(np.percentile(db[a:b], 90)))
    return p


def spans(y, sr):
    db = frame_db(y, sr)
    p = prof_of(db)
    out = {}
    # V2 全槽
    out["V2"] = max(p) - min(p)
    # V1 剔槽（现版）
    sp = [q for q in p if q > max(p) - 25.0]
    out["V1"] = (max(sp) - min(sp)) if len(sp) >= 3 else None
    # V3 补噪到 −58 后全槽
    dbn = db.copy()
    zero = dbn < -70.0          # 数字静音帧
    if zero.any():
        dbn[zero] = -58.0
    # 整体平移：把安静帧中位压到 −58（真人实测 −56.5）
    q = np.percentile(dbn, 5)
    if q > -70:
        dbn = dbn - (q + 58.0)
    pn = prof_of(dbn)
    out["V3"] = max(pn) - min(pn)
    spn = [a for a in pn if a > max(pn) - 25.0]
    out["V4"] = (max(spn) - min(spn)) if len(spn) >= 3 else None
    return out


def collect(files):
    acc = {k: [] for k in ("V1", "V2", "V3", "V4")}
    for f in files:
        try:
            y, sr = sf.read(f, dtype="float32")
        except Exception:
            continue
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        if len(y) / sr < 1.0:
            continue
        for k, v in spans(y, sr).items():
            if v is not None:
                acc[k].append(v)
    return acc


human = sorted(glob.glob("E:/ttsds/data/ref_human/*.wav"))
cast = [json.loads(l) for l in open("G:/_setup/_castle_en_ch123_cast.jsonl", encoding="utf-8") if l.strip()]
ours_ids = sorted({r["id"] for r in cast if r.get("speaker") == "narrator"})
ours = ["G:/_setup/_audio_ch123/out/%s.wav" % i for i in ours_ids]

print("真人 %d / 我们 %d\n" % (len(human), len(ours)))
H = collect(human)
O = collect(ours)
print("%-4s | %-32s | %s" % ("口径", "真人 p05/p50/p95 (n)", "我们 p50 (n)"))
print("-" * 78)
for k in ("V1", "V2", "V3", "V4"):
    h = np.array(H[k], dtype=float)
    o = np.array(O[k], dtype=float)
    print("%-4s | %5.1f / %5.1f / %5.1f (%d)      | %5.1f (%d)"
          % (k, np.percentile(h, 5), np.percentile(h, 50), np.percentile(h, 95), len(h),
             np.percentile(o, 50), len(o)))
print("\n文档基准：真人 26.5 / 36.5 / 38.7，我们 25.1")
