# -*- coding: utf-8 -*-
"""mt_audit.py —— 交付前全面体检（文本层 + 音频层 + 拼装层）。

不做任何修改，只出结论。用法：python mt_audit.py --ch ch1
"""
import argparse
import json
import os
import re

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
END_P = re.compile(r"[.!?\u2026][\u2019\u201d]?$")
ATTR = re.compile(r"\b(said|asked|replied|answered|continued|shouted|yelled|"
                  r"muttered|responded|cried|whispered)\b", re.I)


def h(t):
    print("\n" + "─" * 62)
    print(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--plan", default="mt_plan3.json")
    a = ap.parse_args()

    plan = [p for p in json.load(open(os.path.join(ROOT, a.plan), encoding="utf-8"))
            if p["ch"] == a.ch]
    print("章 %s：%d 单元 / %d 词" % (a.ch, len(plan), sum(len(p["text"].split()) for p in plan)))

    # ---------- 文本层 ----------
    h("① 文本完整性")
    junk = [p for p in plan if re.search(r"===|\.xhtml|第\s*\d+\s*节", p["text"])]
    print("EPUB 残留标记        : %d 条" % len(junk))
    for p in junk[:5]:
        print("   ", p["id"], p["text"][:70])
    empt = [p for p in plan if not p["text"].strip()]
    print("空单元               : %d 条" % len(empt))

    h("② 句子结构（影响语气，最关键）")
    noend = [p for p in plan if not END_P.search(p["text"].rstrip())]
    print("不以句末标点结尾      : %d 条（%.0f%%）  ← 这些会被当成完整句念，前段会落调"
          % (len(noend), 100.0 * len(noend) / len(plan)))
    comma = [p for p in noend if p["text"].rstrip().endswith((",", ";", ":"))]
    print("   其中以逗号/分号结尾 : %d 条" % len(comma))
    for p in comma[:5]:
        print("      ", p["id"], "|", p["text"][-60:])
    lower = [p for p in plan if p["text"][:1].islower()]
    print("以小写字母开头（续句）: %d 条" % len(lower))
    attr = [p for p in plan if len(p["text"].split()) <= 8 and ATTR.search(p["text"])]
    print("归属尾巴（said/asked）: %d 条" % len(attr))
    for p in attr[:5]:
        print("      ", p["id"], "|", p["text"])

    h("③ 长度分布")
    L = np.array([len(p["text"].split()) for p in plan])
    print("词数 中位 %.0f  p10 %.0f  p90 %.0f  最长 %d" % (np.median(L), np.percentile(L, 10),
                                                          np.percentile(L, 90), L.max()))
    print("≤3 词 %d 条 | 4–8 词 %d 条 | 9–20 词 %d 条 | >20 词 %d 条"
          % ((L <= 3).sum(), ((L > 3) & (L <= 8)).sum(),
             ((L > 8) & (L <= 20)).sum(), (L > 20).sum()))

    h("④ 拼装停顿")
    G = np.array([p["gap"] for p in plan])
    print("停顿 中位 %.2fs  p10 %.2f  p90 %.2f  合计 %.1f 分钟"
          % (np.median(G), np.percentile(G, 10), np.percentile(G, 90), G.sum() / 60))
    for lo, hi, nm in [(0, 0.35, "≤0.35 归属尾巴"), (0.35, 0.75, "0.35–0.75 逗号"),
                       (0.75, 1.15, "0.75–1.15 句号"), (1.15, 9, ">1.15 段落")]:
        m = (G >= lo) & (G < hi)
        print("   %-18s %d 条" % (nm, m.sum()))

    # ---------- 音频层 ----------
    pick = os.path.join(ROOT, "_mt_pick")
    rows = []
    for p in plan:
        fp = os.path.join(pick, p["id"] + ".wav")
        if not os.path.exists(fp):
            continue
        y, sr = sf.read(fp, dtype="float32", always_2d=True)
        y = y.mean(1)
        w = int(0.02 * sr)
        v = []
        for i in range(0, len(y) - w, w):
            r = np.sqrt((y[i:i + w] ** 2).mean())
            if 20 * np.log10(r + 1e-12) > -45:
                v.append(r)
        rms = 20 * np.log10(np.sqrt(np.mean(np.square(v))) + 1e-12) if v else -120
        rows.append({"id": p["id"], "dur": len(y) / sr, "rms": rms,
                     "peak": float(np.abs(y).max()),
                     "wpm": len(p["text"].split()) / (len(y) / sr) * 60})
    h("⑤ 单条音频（已择优 %d / %d）" % (len(rows), len(plan)))
    if rows:
        rms = np.array([r["rms"] for r in rows])
        wpm = np.array([r["wpm"] for r in rows])
        pk = np.array([r["peak"] for r in rows])
        print("原始电平 中位 %.1f dB  跨度 %.1f dB（%.1f–%.1f）"
              % (np.median(rms), rms.max() - rms.min(), rms.min(), rms.max()))
        print("原始语速 中位 %.0f wpm  p10–p90 %.0f–%.0f  最快 %.0f 最慢 %.0f"
              % (np.median(wpm), np.percentile(wpm, 10), np.percentile(wpm, 90),
                 wpm.max(), wpm.min()))
        print("峰值 ≥0.99（削顶） %d 条" % (pk >= 0.99).sum())
        print("语速 >180 或 <70 的异常条 %d 条" % ((wpm > 180) | (wpm < 70)).sum())
        for r in sorted(rows, key=lambda x: -x["wpm"])[:3]:
            print("   最快 %s %.0f wpm (%.2fs)" % (r["id"], r["wpm"], r["dur"]))
        for r in sorted(rows, key=lambda x: x["wpm"])[:3]:
            print("   最慢 %s %.0f wpm (%.2fs)" % (r["id"], r["wpm"], r["dur"]))

    # ---------- 成品 ----------
    wav = os.path.join(ROOT, "_mt_out", a.ch + ".wav")
    if os.path.exists(wav):
        h("⑥ 成品整章")
        y, sr = sf.read(wav, dtype="float32", always_2d=True)
        y = y.mean(1)
        print("%.2f 分钟  峰值 %.2f  真 RMS %.1f dB"
              % (len(y) / sr / 60, float(np.abs(y).max()),
                 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)))
        # 间隙分布（成品里真实存在的静音段）
        frame = int(0.02 * sr)
        env = np.array([np.sqrt((y[i:i + frame] ** 2).mean())
                        for i in range(0, len(y) - frame, frame)])
        db = 20 * np.log10(env + 1e-12)
        sil = db < -45
        runs, cur = [], 0
        for s in sil:
            if s:
                cur += 1
            else:
                if cur * 0.02 >= 0.25:
                    runs.append(cur * 0.02)
                cur = 0
        if cur:
            runs.append(cur * 0.02)
        R = np.array(runs) if runs else np.array([0])
        print("成品间隙 %d 段  中位 %.2fs  p90 %.2fs  最长 %.2fs"
              % (len(R), np.median(R), np.percentile(R, 90), R.max()))


if __name__ == "__main__":
    main()
