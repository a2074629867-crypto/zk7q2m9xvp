# -*- coding: utf-8 -*-
"""_pick_tier48.py —— 给「16k 老参考的语气档」从本片 48k 池里挑替换参考（零模型计算版）。

为什么（2026-11-13 19:50 实测）：
  对交付音频做档内 pair-cos，规律极干净 ——
  | 档 | 条数 | 档内中位 | 参考 |
  | Thomas_defiant_1   |  5 | 0.763 | 48k |
  | Thomas_excited_1   |  3 | 0.727 | 48k |
  | Charles_nervous_2  | 13 | 0.747 | 48k |
  | Charles_angry_2    | 11 | 0.683 | 48k |
  | Thomas_loud_1      | 62 | 0.582 | 16k |
  | Thomas_calm_1      | 23 | 0.495 | 16k |
  | Charles_excited_1  |  6 | 0.403 | 16k |
  | Charles_neutral_1  | 12 | 0.373 | 16k |
  | Charles_soft_1     | 23 | 0.342 | 16k |
  ⇒ 参考是 16k 还是 48k，直接决定档内音色一致性。126 条受影响。

★ 第一版试图算 vox 五维做「分布匹配」，但 386 段全量算太慢（几分钟不出结果）。
  改为纯查表：`meas.json` 已有 e2v / f0 / MOS / dur，`thin_emb.npz` 已有声纹向量。
  零模型计算，秒出。最终仍要 A/B 验证，所以先粗筛比精算更划算。

档目标（e2v 偏好 + 声学倾向）：
  soft    柔和：中立/难过，f0 偏低，MOS 高
  neutral 平述：中立，MOS 高
  excited 兴奋：开心/吃惊，f0 偏高
  calm    平静：中立，f0 中低
  loud    大声：生气，f0 高（要「响」不要「虚」）

硬闸：声纹 cos ≥ 0.45（与角色 48k 核心质心）、MOS ≥ 2.0、时长 ≥ 1.2s。

用法：python _pick_tier48.py Charles soft neutral excited
"""
import json, os, sys
import numpy as np

HERE = "G:/_setup"
CAND = os.path.join(HERE, "_refs_new/cand")
MEAS = os.path.join(HERE, "_refs_new/meas.json")
EMB = os.path.join(HERE, "_refs_new/thin_emb.npz")
MIN_COS, MIN_MOS, MIN_DUR = 0.45, 2.0, 1.2
TOP = 6

PREF = {
    "soft":    ({"中立/neutral", "难过/sad", "平静/calm"}, "f0lo"),
    "neutral": ({"中立/neutral", "平静/calm"}, None),
    "excited": ({"开心/happy", "吃惊/surprised"}, "f0hi"),
    "calm":    ({"中立/neutral", "平静/calm"}, "f0lo"),
    "loud":    ({"生气/angry", "厌恶/disgusted"}, "f0hi"),
}


def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法：_pick_tier48.py <角色> <档> [档...]")
    role, tiers = sys.argv[1], sys.argv[2:]

    rows = json.load(open(MEAS, encoding="utf-8"))
    z = np.load(EMB, allow_pickle=True)
    cids_all, vecs = z["cids"].tolist(), z["vecs"]
    idx = {c: k for k, c in enumerate(cids_all)}

    cand = [r for r in rows if r.get("role") == role and r["cid"] in idx]
    if not cand:
        raise SystemExit("48k 池里没有 %s 的段" % role)
    Vs = np.stack([vecs[idx[r["cid"]]] for r in cand])
    Vs = Vs / (np.linalg.norm(Vs, axis=1, keepdims=True) + 1e-9)
    c0 = Vs.mean(0); c0 /= np.linalg.norm(c0)
    core = Vs[Vs @ c0 >= 0.5]
    cent = core.mean(0); cent /= np.linalg.norm(cent)
    sc = Vs @ cent
    for r, s in zip(cand, sc):
        r["cos"] = float(s)
    f0s = [r.get("f0") or 0 for r in cand]
    print("%s：48k 池 %d 段，核心 %d 段（cos≥0.5），cos 中位 %.3f，f0 中位 %.0f"
          % (role, len(Vs), len(core), float(np.median(sc)), float(np.median(f0s))), flush=True)

    for tier in tiers:
        pref, tilt = PREF.get(tier, (set(), None))
        pool = [r for r in cand
                if r["cos"] >= MIN_COS and (r.get("mos") or 0) >= MIN_MOS
                and (r.get("dur") or 0) >= MIN_DUR]
        print("\n== %s/%s  可用 %d 段（cos≥%.2f, MOS≥%.1f, ≥%.1fs）"
              % (role, tier, len(pool), MIN_COS, MIN_MOS, MIN_DUR), flush=True)
        if not pool:
            continue

        def rank(r):
            hit = 1.0 if (r.get("e2v") in pref) else 0.0
            f0 = r.get("f0") or 0
            t = 0.0
            if tilt == "f0lo":
                t = -f0 / 300.0
            elif tilt == "f0hi":
                t = f0 / 300.0
            return hit * 2.0 + t + 0.9 * (r["cos"] - 0.45) * 4 + 0.4 * ((r.get("mos") or 0) - 2.0)

        for r in sorted(pool, key=rank, reverse=True)[:TOP]:
            print("  %-10s 分 %+5.2f  cos %.3f  MOS %.2f  %4.2fs  f0 %5.1f  %-14s %s"
                  % (r["cid"], rank(r), r["cos"], r.get("mos") or 0, r.get("dur") or 0,
                     r.get("f0") or 0, r.get("e2v"), (r.get("text") or "")[:44]))


if __name__ == "__main__":
    main()
