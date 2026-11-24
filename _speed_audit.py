# -*- coding: utf-8 -*-
"""逐句语速审计：新旧两版用同一把尺子（_speedlib 句中语速）。

产出 _speed_audit.json：
  rows[i] = {id, ch, words, rate, new:{dur,speech,wpm,share}, old:{...}}
另打印分布、逐章分布、离群清单。

用法：
  G:/Python310/python.exe -u _speed_audit.py
  G:/Python310/python.exe -u _speed_audit.py --target 190
"""
import argparse
import io
import json
import os
import sys

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
sys.path.insert(0, ROOT)
from _speedlib import speech_time  # noqa: E402

PLAN = os.path.join(ROOT, "_castle_en_ch123_plan_v2.jsonl")
# 全量旁白清单（726 条）：plan v2 只有 716 条，另有 10 句带弯引号的
# 历史缺口只在 _narr_plan_for_pause.jsonl 里，音频已补齐，必须一起审。
PLAN_ALL = os.path.join(ROOT, "_narr_plan_for_pause.jsonl")
NEW = os.path.join(ROOT, "_regen_1123_paused")
OLD = os.path.join(ROOT, "_audio_ch123/out")
OUT = os.path.join(ROOT, "_speed_audit.json")


def measure(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    return speech_time(y, sr)[:2]          # (dur, speech)


def pct(v, q):
    return float(np.percentile(v, q)) if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=float, default=None,
                    help="句中语速目标（wpm）；不给则用行业标准换算")
    ap.add_argument("--band", type=float, default=0.12,
                    help="允许带宽（相对目标的比例），默认 ±12%%")
    ap.add_argument("--min-words", type=int, default=4,
                    help="少于这个词数的句子不参与语速判定（wpm 噪声太大）")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--new", default=None)
    ap.add_argument("--old", default=None)
    a = ap.parse_args()
    global NEW, OLD
    if a.new:
        NEW = a.new
    if a.old:
        OLD = a.old

    plan = [json.loads(l) for l in io.open(PLAN, encoding="utf-8") if l.strip()]
    rate = {r["id"]: float(r.get("rate") or 1.0) for r in plan
            if r.get("speaker") == "narrator"}
    allrows = [json.loads(l) for l in io.open(PLAN_ALL, encoding="utf-8") if l.strip()]
    narr = [r for r in allrows if r.get("speaker") == "narrator"]
    # 去重并保证顺序稳定
    seen, ordered = set(), []
    for r in narr:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        ordered.append(r)

    rows = []
    for r in ordered:
        sid = r["id"]
        nw = r.get("words") or len((r.get("text") or "").split())
        rec = dict(id=sid, ch=r.get("chapter"), words=nw,
                   rate=rate.get(sid, 1.0))
        for tag, d in (("new", NEW), ("old", OLD)):
            p = os.path.join(d, sid + ".wav")
            if not os.path.exists(p):
                rec[tag] = None
                continue
            dur, sp = measure(p)
            rec[tag] = dict(dur=round(dur, 3), speech=round(sp, 3),
                            share=round(sp / dur, 4) if dur > 0 else None,
                            wpm=round(nw / sp * 60.0, 1) if sp > 0.15 else None)
        rows.append(rec)

    json.dump(rows, io.open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    def dist(tag):
        v = [r[tag]["wpm"] for r in rows if r.get(tag) and r[tag]["wpm"]
             and r["words"] >= a.min_words]
        return v

    dn, do = dist("new"), dist("old")
    print("句数 %d（参与语速判定 %d，>=%d 词）" % (len(rows), len(dn), a.min_words))
    print()
    print("%-6s %6s %6s %6s %6s %6s %6s" % ("版本", "n", "p10", "p25", "p50", "p75", "p90"))
    for tag, v in (("new", dn), ("old", do)):
        print("%-6s %6d %6.0f %6.0f %6.0f %6.0f %6.0f"
              % (tag, len(v), pct(v, 10), pct(v, 25), pct(v, 50),
                 pct(v, 75), pct(v, 90)))

    # 语音占比（决定「成品 155 wpm」对应多少句中语速）
    sh = [r["new"]["share"] for r in rows if r.get("new") and r["new"]["share"]]
    so = [r["old"]["share"] for r in rows if r.get("old") and r["old"]["share"]]
    print()
    print("语音占比（speech/dur）：new 中位 %.3f  old 中位 %.3f"
          % (float(np.median(sh)), float(np.median(so))))

    # 目标锚点：真人母带 159 条（E:/ttsds/data/ref_human）用同一把尺子量出的 p50 = 175
    # ACX 成品 155 wpm 只能做交叉校验，不能直接反推句中语速：
    #   它假设静音占比 ~12%，而我们这版是 27%（三档停顿 + 模型自带句内停顿），
    #   反推会得出 212，比真人还快 —— 那是把「我们停顿多」错算成「该说得更快」。
    HUMAN_P50 = 175.0
    FINISHED = 155.0
    target = a.target or HUMAN_P50
    lo, hi = target * (1 - a.band), target * (1 + a.band)
    print()
    print("目标锚点：真人母带 p50 = %.0f wpm（同一把尺子，159 条）" % HUMAN_P50)
    print("交叉校验：ACX 成品 %d wpm ÷ 我们的语音占比 %.3f = %.0f wpm（仅供参考，不采用）"
          % (FINISHED, float(np.median(sh)), FINISHED / float(np.median(sh))))
    print("采用目标 %.0f wpm，带宽 ±%.0f%% = [%.0f, %.0f]"
          % (target, a.band * 100, lo, hi))

    for tag in ("old", "new"):
        v = [r for r in rows if r.get(tag) and r[tag]["wpm"] and r["words"] >= a.min_words]
        fast = [r for r in v if r[tag]["wpm"] > hi]
        slow = [r for r in v if r[tag]["wpm"] < lo]
        print()
        print("%s：%d 句里 偏快 %d（%.0f%%） 偏慢 %d（%.0f%%） 在带内 %d（%.0f%%）"
              % (tag, len(v), len(fast), 100 * len(fast) / max(1, len(v)),
                 len(slow), 100 * len(slow) / max(1, len(v)),
                 len(v) - len(fast) - len(slow),
                 100 * (len(v) - len(fast) - len(slow)) / max(1, len(v))))
        if tag == "new" and fast:
            fast.sort(key=lambda r: -r["new"]["wpm"])
            print("   最偏快 10 条：")
            for r in fast[:10]:
                print("     %-9s %2d词 %.0f wpm  speech %.2fs  rate %.2f"
                      % (r["id"], r["words"], r["new"]["wpm"], r["new"]["speech"], r["rate"]))

    # 新旧同句对比：旧在带内、新偏快
    both = [r for r in rows if r.get("new") and r.get("old")
            and r["new"]["wpm"] and r["old"]["wpm"] and r["words"] >= a.min_words]
    flip = [r for r in both if r["old"]["wpm"] <= hi and r["new"]["wpm"] > hi]
    print()
    print("同句对比 %d 条：旧在带内但新偏快 %d 条（%.0f%%）"
          % (len(both), len(flip), 100 * len(flip) / max(1, len(both))))
    flip.sort(key=lambda r: -(r["new"]["wpm"] / max(1e-6, r["old"]["wpm"])))
    for r in flip[:10]:
        print("   %-9s 旧 %.0f → 新 %.0f wpm（×%.2f）"
              % (r["id"], r["old"]["wpm"], r["new"]["wpm"],
                 r["new"]["wpm"] / max(1e-6, r["old"]["wpm"])))

    print()
    print("明细 → %s" % a.out)


if __name__ == "__main__":
    main()
