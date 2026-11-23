#!/usr/bin/env python
"""给 Charles/soft 档找补：现有 3 条只有 1.5-1.9s，导致该档吸走 10 条 Thomas。

思路（保守，不猜）：
  1. 用**新的**多人判据重筛 393 条 cue —— 旧判据把 118 条单人标成多人（法语片里
     单个 `-` 只是「对白开始」），这些是白丢的素材。
  2. 声纹判角色，只要 role=Charles 且 z1 高的。
  3. 对候选打 VAD，按委屈判据（1−A）排序。
  4. 输出候选表给人耳复核，不自动入库 —— 情绪音色方差比说话人音色方差还大，
     自动入档的风险比人工看一遍高。

用法：
  G:/Python310/python.exe find_soft.py --min-dur 2.5
"""
import argparse
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
sys.path.insert(0, "G:/voice_lib")

MID_DASH = re.compile(r"[.!?…]\s*-\s*\S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="castle_cues_index.json")
    ap.add_argument("--min-dur", type=float, default=2.5)
    ap.add_argument("--max-dur", type=float, default=9.0)
    ap.add_argument("--z1", type=float, default=1.2, help="声纹 z1 下限")
    ap.add_argument("--out", default="out/soft_cand.json")
    ap.add_argument("--no-vad", action="store_true")
    a = ap.parse_args()

    idx = json.load(open(a.index, encoding="utf-8"))
    print("总 %d 条 cue" % len(idx))

    # 新判据重算 multi：句中切换 or 行首 '-' + 另一处标记
    def is_multi(c):
        t = c["text"]
        mid = len(MID_DASH.findall(t))
        start = 1 if t.lstrip().startswith("-") else 0
        return mid >= 1 or (start + mid) >= 2

    old_multi = sum(1 for c in idx if c.get("multi"))
    new_multi = sum(1 for c in idx if is_multi(c))
    print("多人：旧判据 %d → 新判据 %d（多出 %d 条单人可用素材）" % (
        old_multi, new_multi, old_multi - new_multi))

    cand = [c for c in idx if not is_multi(c) and not c.get("sfx")
            and a.min_dur <= c["dur"] <= a.max_dur]
    print("时长 %.1f-%.1fs 的单人非音效 cue: %d 条" % (a.min_dur, a.max_dur, len(cand)))

    from chain_check import EmoVoice
    ev = EmoVoice(model="r34")
    print("声纹判定中 …", flush=True)
    rows = []
    for i, c in enumerate(cand):
        p = c["path"].replace("\\", "/")
        try:
            r = ev.check(p)
        except Exception:
            continue
        rows.append(dict(c, p=p, role=r["role"], z1=r["z1"], emo=r["emo"],
                         role_z=r["role_z"], top2=r["top2"]))
        if (i + 1) % 50 == 0:
            print("  %d/%d" % (i + 1, len(cand)), flush=True)

    import collections
    print("\n角色分布:", dict(collections.Counter(r["role"] for r in rows)))
    chal = [r for r in rows if r["role"] == "Charles" and r["z1"] >= a.z1]
    print("Charles 且 z1>=%.1f: %d 条" % (a.z1, len(chal)))

    if not a.no_vad and chal:
        import ser as S
        print("\n打 VAD（委屈判据 1−A，P25=0.4934）…", flush=True)
        vox = S.VoxDim()
        for i, r in enumerate(chal):
            sc = vox.score(r["p"]) or {}
            A = float(sc.get("arousal", 0)); V = float(sc.get("valence", 0))
            D = float(sc.get("dominance", 0))
            r.update(A=round(A, 3), V=round(V, 3), D=round(D, 3), soft=round(1 - A, 3))
            if (i + 1) % 10 == 0:
                print("  %d/%d" % (i + 1, len(chal)), flush=True)

    chal.sort(key=lambda r: -r.get("soft", 0))
    print("\n=== Charles 候选（按委屈判据 1−A 排序）P25=0.4934 ===")
    print("%-26s %5s %5s %5s %5s %6s %s" % ("file", "dur", "A", "V", "1-A", "z1", "text"))
    for r in chal:
        print("%-26s %5.2f %5.3f %5.3f %5.3f %6.2f %s" % (
            os.path.basename(r["p"]), r["dur"], r.get("A", 0), r.get("V", 0),
            r.get("soft", 0), r["z1"], r["text"][:44]))

    json.dump(chal, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写 ->", a.out)


if __name__ == "__main__":
    main()
