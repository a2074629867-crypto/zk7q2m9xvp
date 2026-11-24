# -*- coding: utf-8 -*-
"""逐句语速归一到行业标准（目标 = 真人母带 p50 = 175 句中 wpm）。

为什么用逐句 tempo 而不是重生成：
  `regen_narr.py` 里的 rate 本来就是 ffmpeg rubberband 的后处理系数
  （rate<0.98 才走 tempo），与「事后对同一段音频做 tempo」在数学上等价。
  ⇒ 逐句 tempo 是同一个手段，但只吃 CPU、秒级、可重入，不用再烧 16 小时 GPU。

不动的东西：
  · rate=0.84 的慢读句 —— 那是标注决定的表演意图，不算「语速错」
  · rel_z —— tempo 是句内等比拉伸，比值不变，重音结论继续有效
  · 停顿三档 —— 只改干声，改完重新插停顿，档位仍是 0.51/1.135/1.695

用法：
  G:/Python310/python.exe -u _speed_norm.py                # 只出计划，不动文件
  G:/Python310/python.exe -u _speed_norm.py --apply        # 落地到 _regen_1123_norm
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys

import numpy as np

ROOT = "G:/_setup"
FF = "E:/tool/oopz/ffmpeg.exe"                   # 与 regen_narr.py 用同一个
SRC = os.path.join(ROOT, "_regen_1123")          # 干声（已过闸、已择优）
DST = os.path.join(ROOT, "_regen_1123_norm")     # 归一后干声
AUDIT = os.path.join(ROOT, "_speed_audit.json")
PLAN_OUT = os.path.join(ROOT, "_speed_norm_plan.json")

TARGET = 175.0        # 真人母带句中语速 p50（159 条，同一把尺子）
BAND = 0.15           # 仅用于统计「改前有多少句越界」
TEMPO_MIN = 0.72      # 红线：慢读档下限 0.72（0.70 是断崖），见 REQUIREMENTS
TEMPO_MAX = 1.10      # 最多加快 10%
MIN_WORDS = 4         # 少于 4 词不判（4 词以下 wpm 完全被量化噪声支配）
MIN_SPEECH = 0.7      # 发声不足 0.7s 不判（5 词短句常落在 1.0s，1.2 会把最急的漏掉）
SLOW_TIER = 0.98      # rate < 此值 = 故意慢读档，目标改为 175×rate（保留对比度）


def ffmpeg_tempo(src, dst, tempo):
    tmp = dst + ".tmp.wav"
    cmd = [FF, "-y", "-v", "error", "-i", src,
           "-af", "rubberband=tempo=%.5f:pitchq=quality" % tempo,
           "-ac", "1", "-c:a", "pcm_s16le", tmp]   # 保持源采样率 48k，不额外重采样
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "ignore")[:300])
    os.replace(tmp, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--target", type=float, default=TARGET)
    ap.add_argument("--band", type=float, default=BAND)
    ap.add_argument("--strength", type=float, default=0.85,
                    help="向目标压缩的强度；1.0=全部落在目标（会发死），0.85 保留约 ±10%% 自然起伏")
    a = ap.parse_args()

    rows = json.load(io.open(AUDIT, encoding="utf-8"))
    lo, hi = a.target * (1 - a.band), a.target * (1 + a.band)

    plan, skipped = [], []
    for r in rows:
        n = r.get("new") or {}
        wpm = n.get("wpm")
        if not wpm or r["words"] < MIN_WORDS or (n.get("speech") or 0) < MIN_SPEECH:
            skipped.append(dict(id=r["id"], why="太短不判"))
            continue
        # 每句的目标 = 基准 175 × 该句 rate 档位
        #   rate 1.00 → 175；rate 0.84 → 147（慢读档保留 16% 对比度）
        tgt = a.target * (r["rate"] if r["rate"] < SLOW_TIER else 1.0)
        want = wpm + a.strength * (tgt - wpm)   # 压缩而非归零，保留自然起伏
        tempo = want / wpm
        if abs(tempo - 1.0) < 0.02:          # 已经在目标附近，不动（避免无谓重编码）
            continue
        clipped = min(TEMPO_MAX, max(TEMPO_MIN, tempo))
        plan.append(dict(id=r["id"], words=r["words"], wpm=wpm, rate=r["rate"],
                         tgt=round(tgt, 1), want=round(want, 1), tempo=round(clipped, 4),
                         raw_tempo=round(tempo, 4),
                         clipped=abs(clipped - tempo) > 1e-3,
                         speech=n["speech"]))

    fast = [p for p in plan if p["wpm"] > hi]
    slow = [p for p in plan if p["wpm"] < lo]
    print("目标 %.0f wpm（慢读档 ×0.84 = %.0f），带 [%.0f, %.0f]"
          % (a.target, a.target * 0.84, lo, hi))
    print("参与判定 %d 句，需调整 %d 句（偏快 %d / 偏慢 %d），跳过 %d 句"
          % (len(rows) - len(skipped), len(plan), len(fast), len(slow), len(skipped)))
    if plan:
        t = [p["tempo"] for p in plan]
        print("tempo 范围 %.3f ~ %.3f（中位 %.3f），被下限/上限截断 %d 句"
              % (min(t), max(t), float(np.median(t)),
                 sum(1 for p in plan if p["clipped"])))
    print()
    print("偏快 Top 12：")
    for p in sorted(fast, key=lambda x: -x["wpm"])[:12]:
        print("   %-9s %2d词 rate %.2f  %3.0f → %.0f wpm  tempo %.3f%s"
              % (p["id"], p["words"], p["rate"], p["wpm"], p["tgt"], p["tempo"],
                 "  [截断]" if p["clipped"] else ""))
    if slow:
        print("偏慢 Top 8：")
        for p in sorted(slow, key=lambda x: x["wpm"])[:8]:
            print("   %-9s %2d词 rate %.2f  %3.0f → %.0f wpm  tempo %.3f%s"
                  % (p["id"], p["words"], p["rate"], p["wpm"], p["tgt"], p["tempo"],
                     "  [截断]" if p["clipped"] else ""))

    json.dump(dict(target=a.target, band=a.band, lo=lo, hi=hi,
                   items=plan, skipped=skipped),
              io.open(PLAN_OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print()
    print("计划 → %s" % PLAN_OUT)

    if not a.apply:
        return

    os.makedirs(DST, exist_ok=True)
    ok = fail = 0
    for i, p in enumerate(plan, 1):
        src = os.path.join(SRC, p["id"] + ".wav")
        dst = os.path.join(DST, p["id"] + ".wav")
        if not os.path.exists(src):
            print("   !! 缺源 %s" % p["id"])
            fail += 1
            continue
        try:
            ffmpeg_tempo(src, dst, p["tempo"])
            ok += 1
        except Exception as e:  # noqa: BLE001
            print("   !! %s %s" % (p["id"], e))
            fail += 1
        if i % 25 == 0:
            print("   %d/%d" % (i, len(plan)), flush=True)
    print("落地 %d 条（失败 %d）→ %s" % (ok, fail, DST))

    # 未调整的句子直接复制，保证 DST 是完整可用的库
    changed = {p["id"] for p in plan}
    copied = 0
    for r in rows:
        sid = r["id"]
        if sid in changed:
            continue
        src = os.path.join(SRC, sid + ".wav")
        dst = os.path.join(DST, sid + ".wav")
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            copied += 1
    print("原样复制 %d 条 ⇒ %s 共 %d 个 wav"
          % (copied, DST, len(os.listdir(DST))))


if __name__ == "__main__":
    main()
