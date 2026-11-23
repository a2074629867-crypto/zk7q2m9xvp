# -*- coding: utf-8 -*-
"""起伏尺子三方对照：把三套口径跑在同一批音频上，看谁复现文档里的 26.5/36.5/38.7。

A 带构建口径 mt_rhythm_bands.measure：先 floor_norm(−56)，再剔静音帧，语音帧等分 21 段取 p90
B 现行校验口径 narr_check.l1_unit：时间等分 21 段取 p90，再剔掉 < max−25dB 的槽
C 文档口径（span_calib V2）：时间等分 21 段取 p90，全 21 槽不剔

用法：python span_variants.py [--limit N]
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import mt_rhythm_bands as MB  # noqa: E402

NPT = 21
HUMAN = "E:/ttsds/data/ref_human"
PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
AUD = "G:/_setup/_audio_ch123/out"


def span_b(y, sr):
    """现行 l1_unit：时间等分 21 槽，每槽 p90，剔掉 < max−25 的槽后取极差。"""
    db, _ = MB.frame_db(y, sr)
    if len(db) < NPT:
        return None
    prof = []
    for i in range(NPT):
        a = int(i * len(db) / NPT)
        b = max(a + 1, int((i + 1) * len(db) / NPT))
        prof.append(float(np.percentile(db[a:b], 90)))
    spoken = [p for p in prof if p > max(prof) - 25.0]
    return round(max(spoken) - min(spoken), 1) if len(spoken) >= 3 else None


def span_c(y, sr):
    """文档口径：时间等分 21 槽，全槽极差，不剔、不补底噪。"""
    db, _ = MB.frame_db(y, sr)
    if len(db) < NPT:
        return None
    prof = []
    for i in range(NPT):
        a = int(i * len(db) / NPT)
        b = max(a + 1, int((i + 1) * len(db) / NPT))
        prof.append(float(np.percentile(db[a:b], 90)))
    return round(max(prof) - min(prof), 1)


def span_a(y, sr):
    """带构建口径：直接调 measure()，取它自己的 energy_span。"""
    d = MB.measure(y, sr, "narr")
    return d.get("energy_span")


def load(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    return y, sr


def q(v):
    v = [x for x in v if x is not None]
    if not v:
        return (0, 0, 0, 0)
    return (len(v), *[round(float(np.percentile(v, p)), 1) for p in (5, 50, 95)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(HUMAN, "*.wav")))
    if a.limit:
        files = files[: a.limit]
    print("真人 ref_human：%d 条" % len(files), flush=True)
    A, B, C = [], [], []
    for i, f in enumerate(files):
        try:
            y, sr = load(f)
        except Exception:
            continue
        A.append(span_a(y, sr))
        B.append(span_b(y, sr))
        C.append(span_c(y, sr))
        if (i + 1) % 40 == 0:
            print("  %d/%d" % (i + 1, len(files)), flush=True)

    print()
    print("%-14s %5s %8s %8s %8s" % ("口径", "n", "p05", "p50", "p95"))
    for nm, arr in (("A 带构建", A), ("B 现行校验", B), ("C 文档口径", C)):
        n, p5, p50, p95 = q(arr)
        print("%-14s %5d %8.1f %8.1f %8.1f" % (nm, n, p5, p50, p95))
    print("文档 REQUIREMENTS §28 记的真人值：  26.5     36.5     38.7")

    # 我们自己的旁白
    ids = []
    for line in open(PLAN, encoding="utf-8"):
        r = json.loads(line)
        if r.get("speaker") == "narrator":
            p = os.path.join(AUD, r["id"] + ".wav")
            if os.path.exists(p):
                ids.append(p)
    if a.limit:
        ids = ids[: a.limit]
    print()
    print("我们的旁白：%d 条" % len(ids), flush=True)
    A2, B2, C2 = [], [], []
    for i, f in enumerate(ids):
        try:
            y, sr = load(f)
        except Exception:
            continue
        A2.append(span_a(y, sr))
        B2.append(span_b(y, sr))
        C2.append(span_c(y, sr))
        if (i + 1) % 100 == 0:
            print("  %d/%d" % (i + 1, len(ids)), flush=True)

    print()
    print("%-14s %5s %8s %8s %8s" % ("口径", "n", "p05", "p50", "p95"))
    for nm, arr in (("A 带构建", A2), ("B 现行校验", B2), ("C 文档口径", C2)):
        n, p5, p50, p95 = q(arr)
        print("%-14s %5d %8.1f %8.1f %8.1f" % (nm, n, p5, p50, p95))

    out = {"human": {"A": A, "B": B, "C": C}, "ours": {"A": A2, "B": B2, "C": C2}}
    json.dump(out, open("G:/_setup/_span_variants.json", "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
