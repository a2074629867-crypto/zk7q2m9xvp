# -*- coding: utf-8 -*-
"""r2_speed_calib.py —— 给第二轮回填标定语速尺子（本批同源样本重标，不搬别批的绝对值）。

为什么必须有这个脚本
--------------------
1. finish_r2.py 现用 ratio = 新时长/旧时长 ∈ [0.65, 1.55] 判回填。这个尺子隐含
   「旧文件是对的」。但这批旧文件本身就是因为念飞了才重生成：
   c3_0954 18 词 1.66s = 651wpm / c2_0265 9 词 1.22s = 443wpm。
   拿坏文件当基准，方向正好反了 —— 修好变长了反而超标被判死。
2. 「全时长 wpm 统一带宽」也不行：DECISIONS.md:295 已实测否决
   （1 词 71 / 2-3 词 129 / 4-7 词 167 / 8-15 词 170 / >15 词 176），
   短句必然是假阳性。只对 >=4 词判档，短条只报数值。
3. 但 167/170/176 是**另一批样本**的口径，不能直接搬过来（HANDOFF.md:77 三处
   口径冲突就是这么来的）。必须在本批 955 条同源成品上重标。
4. c3_0954 的病不是时长而是「7.52s 里只有 0.42s 有声」。所以除了 wpm，
   还要一个有占比 —— DECISIONS.md:287 已经踩过「单帧过线就算有声」，
   这里用 5 帧中值平滑 + 最短 50ms 连续段，单帧过线不算有声。

用法：
  python r2_speed_calib.py                 # 标定 + 判 45 条候选
  python r2_speed_calib.py --json _r2_ruler.json
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
OUT = "G:/_setup/_audio_ch123/out"
NEW = "G:/_setup/_regen_r2_out"
R2 = "G:/_setup/_regen_r2.json"

FRAME = 0.02      # 帧长 20ms
HOP = 0.01        # 帧移 10ms
MIN_RUN = 5       # 连续 >=50ms 才算有声段（DECISIONS.md:287：单帧过线不算）
BUCKETS = [(1, 1), (2, 3), (4, 7), (8, 15), (16, 10 ** 6)]
BUCKET_NAMES = ["1词", "2-3词", "4-7词", "8-15词", ">15词"]


def words(t):
    """只数含字母的 token。弯引号/破折号先换成空格，避免 'well,' 被拆。"""
    for ch in (",", ".", ";", ":", "!", "?", "\u2018", "\u2019", "\u201c", "\u201d",
               "\u2014", "\u2013", "(", ")", "\u2026"):
        t = t.replace(ch, " ")
    return len([x for x in t.split() if any(c.isalpha() for c in x)])


def voiced(sec_path):
    """返回 (总时长, 有声秒数)。有声 = 平滑后连续 >=50ms 的超阈值段。"""
    y, sr = sf.read(sec_path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    n = len(y)
    if n == 0:
        return 0.0, 0.0
    fl, hp = int(FRAME * sr), int(HOP * sr)
    nf = max(0, 1 + (n - fl) // hp)
    if nf < 3:
        db = 20 * np.log10(np.sqrt((y ** 2).mean()) + 1e-9)
        return n / sr, (n / sr if db > -50 else 0.0)
    e = np.array([np.sqrt((y[i * hp:i * hp + fl] ** 2).mean()) for i in range(nf)])
    d = 20 * np.log10(np.maximum(e, 1e-9))
    # 5 帧中值平滑：单帧尖峰压掉，不制造假有声（DECISIONS.md:287）
    k = 2
    sm = np.array([np.median(d[max(0, i - k):i + k + 1]) for i in range(nf)])
    thr = max(float(np.percentile(sm, 95)) - 35.0, -55.0)
    m = sm > thr
    # 只保留连续 >=MIN_RUN 的段
    keep = np.zeros(nf, bool)
    i = 0
    while i < nf:
        if m[i]:
            j = i
            while j < nf and m[j]:
                j += 1
            if j - i >= MIN_RUN:
                keep[i:j] = True
            i = j
        else:
            i += 1
    return n / sr, float(keep.sum() * HOP)


def bucket_of(w):
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo <= w <= hi:
            return i
    return len(BUCKETS) - 1


def prof(path, w):
    d, v = voiced(path)
    return {
        "dur": round(d, 2),
        "voiced": round(v, 2),
        "voiced_ratio": round(v / d, 3) if d > 0 else 0.0,
        "w": w,
        "wpm_full": round(w / d * 60, 0) if d > 0 else 0,
        "wpm_voiced": round(w / v * 60, 0) if v > 0.1 else 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    text = {}
    for line in open(PLAN, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            text[r["id"]] = r["text"]

    targets = [x["id"] for x in json.load(open(R2, encoding="utf-8"))]
    tset = set(targets)

    # ---- 标定集：out 里除 45 条目标旧版之外的全部成品 ----
    files = sorted(glob.glob(os.path.join(OUT, "*.wav")))
    calib = []
    for p in files:
        i = os.path.basename(p)[:-4]
        if i in tset or i not in text:
            continue
        calib.append((i, prof(p, words(text[i]))))
    print("标定集 %d 条（out 共 %d，剔除 45 条待修旧版）" % (len(calib), len(files)))

    # ---- 分档统计（只给 4 词以上出可判区间）----
    edges = []
    print("\n%-8s %5s %8s %8s %8s %8s %8s %8s" % (
        "档", "n", "wpm中位", "p10", "p90", "voic中位", "voic%中位", "voic%p05"))
    for bi, name in enumerate(BUCKET_NAMES):
        rows = [p for _, p in calib if bucket_of(p["w"]) == bi]
        if not rows:
            print("%-8s %5d  (空)" % (name, 0))
            edges.append(None)
            continue
        wf = sorted(r["wpm_full"] for r in rows)
        wv = sorted(r["wpm_voiced"] for r in rows if r["wpm_voiced"] > 0)
        vr = sorted(r["voiced_ratio"] for r in rows)
        def q(A, f):
            return A[min(len(A) - 1, max(0, int(f * len(A))))] if A else 0
        print("%-8s %5d %8.0f %8.0f %8.0f %8.0f %8.2f %8.2f" % (
            name, len(rows), q(wf, .5), q(wf, .10), q(wf, .90),
            q(wv, .5), q(vr, .5), q(vr, .05)))
        edges.append({"n": len(rows), "wpm_p10": q(wf, .10), "wpm_med": q(wf, .5),
                      "wpm_p90": q(wf, .90), "voiced_ratio_p05": q(vr, .05),
                      "voiced_ratio_med": q(vr, .5)})

    # ---- 判 45 条候选 ----
    print("\n=== 45 条候选：新 vs 旧 ===")
    print("%-9s %3s %7s %7s %7s %7s %7s %7s  %s" % (
        "id", "w", "旧dur", "新dur", "旧wpm", "新wpm", "新voic%", "新v_wpm", "判"))
    verdicts = {}
    rows_out = []
    for i in targets:
        pn = os.path.join(NEW, i + ".wav")
        po = os.path.join(OUT, i + ".wav")
        if not (os.path.exists(pn) and os.path.exists(po)):
            continue
        w = words(text[i])
        old, new = prof(po, w), prof(pn, w)
        bi = bucket_of(w)
        bad = []
        # 1) 有声占比：绝对硬伤，不分档
        if new["voiced_ratio"] < 0.35:
            bad.append("有声仅%.0f%%" % (new["voiced_ratio"] * 100))
        if new["voiced"] < 0.30:
            bad.append("有声%.2fs" % new["voiced"])
        # 2) 语速：只对 >=4 词分档判，短条只报数值
        e = edges[bi]
        if w >= 4 and e:
            lo, hi = e["wpm_p10"] * 0.80, e["wpm_p90"] * 1.25
            if new["wpm_full"] > hi:
                bad.append("太快%.0f>%.0f" % (new["wpm_full"], hi))
            elif new["wpm_full"] < lo:
                bad.append("太慢%.0f<%.0f" % (new["wpm_full"], lo))
        else:
            # 短条（1-3 词）wpm 无意义，只看绝对时长
            if new["dur"] > 3.0:
                bad.append("短句%.2fs过长" % new["dur"])
            elif new["dur"] < 0.35:
                bad.append("短句%.2fs过短" % new["dur"])
        ok = not bad
        verdicts[i] = "OK" if ok else " | ".join(bad)
        print("%-9s %3d %7.2f %7.2f %7.0f %7.0f %6.0f%% %7.0f  %s" % (
            i, w, old["dur"], new["dur"], old["wpm_full"], new["wpm_full"],
            new["voiced_ratio"] * 100, new["wpm_voiced"], verdicts[i]))
        rows_out.append({"id": i, "w": w, "old": old, "new": new,
                         "bucket": BUCKET_NAMES[bi], "verdict": verdicts[i],
                         "ok": ok})

    nok = sum(1 for v in verdicts.values() if v == "OK")
    print("\n按新尺子：合格 %d / 不合格 %d（共 %d）" % (nok, len(verdicts) - nok, len(verdicts)))
    if a.json:
        json.dump({"edges": edges, "items": rows_out},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("写 -> %s" % a.json)


if __name__ == "__main__":
    main()
