# -*- coding: utf-8 -*-
"""按 SceneTTS-Bench（arXiv 2609.26255）的口径做「角色级音色一致性」体检。

社区做法（论文 3.3 节）与我们之前的差别：
  1. 不是「每条 vs 一个参考音频」，而是**角色级**：把一个角色所有话语的 embedding 聚在一起，
     找主导簇的中心，再看每条离中心多远。
  2. 质量门控：<0.5s 或音质差的先剔除，避免静音/噪声把中心拉偏。
  3. 惩罚用 **z-score**（超过 2σ 才算偏离），而不是绝对余弦阈值 —— 因为同一角色的
     正常波动本身就有分布，固定阈值会误杀。
  4. SCS = exp(-α · mean(max(0, z-κ)))，κ=2、α=5。

我们用 WeSpeaker CAM++(VoxCeleb en) 512 维，稳健中心用「迭代剔除最低 10%」代替 HDBSCAN
（本机没装 hdbscan；论文也给了 robust core 的替代路径）。

另外附带两个社区指标：
  - 冷启动漂移（Lex 的 audiobook 做法）：同角色各条 median F0 的 (max-min)/median。
    <3% 锁定 / 3-5% 可用 / >10% 每条接缝都能听出来。6% = 一个半音。
  - 语速不连续率 RDR（论文 3.5）：相邻同角色话语的语速比 max(r_i/r_j, r_j/r_i) > τ 记一次跳。
"""
import argparse
import glob
import importlib.util
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import ch123_rebuild as RB

SPK_PATH = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/spk_embed.py"


def load_spk():
    spec = importlib.util.spec_from_file_location("spk_embed", SPK_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def f0_median(path):
    import parselmouth
    a, sr = sf.read(path, dtype="float32", always_2d=True)
    a = a.mean(1)
    s = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    p = s.to_pitch_ac(time_step=0.01, pitch_floor=70, pitch_ceiling=450,
                      octave_cost=0.01, octave_jump_cost=0.35, voiced_unvoiced_cost=0.14)
    f = p.selected_array["frequency"]
    f = f[f > 0]
    return float(np.median(f)) if len(f) else 0.0


def robust_centroid(E, drop_frac=0.10, iters=6):
    """迭代剔除离中心最远的一部分，重建中心（替代 HDBSCAN 主导簇）。"""
    # 注意：不能用「逐维中位数」当中心 —— 512 维单位向量各维中位数接近 0，
    # 归一化后与所有样本近似正交（实测余弦只有 0.03）。必须用均值。
    idx = np.ones(len(E), dtype=bool)
    for _ in range(iters):
        C = E[idx].mean(axis=0)
        C = C / (np.linalg.norm(C) + 1e-12)
        s = E @ C
        if idx.sum() <= max(3, int(len(E) * 0.6)):
            break
        thr = np.quantile(s[idx], drop_frac)
        new = idx & (s >= thr)
        if new.sum() == idx.sum():
            break
        idx = new
    C = E[idx].mean(axis=0)
    return C / (np.linalg.norm(C) + 1e-12), idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default="ch123_clean")
    ap.add_argument("--kappa", type=float, default=2.0)
    ap.add_argument("--alpha", type=float, default=5.0)
    ap.add_argument("--min-dur", type=float, default=0.5)
    ap.add_argument("--tau-rate", type=float, default=1.5)
    args = ap.parse_args()

    from ch123_plan import PLAN, INNER
    who = {"L%03d" % i: w for i, w, _, _ in PLAN}
    who.update({"I%02d" % i: w for i, (_, w, _, _) in enumerate(INNER)})
    words = {"L%03d" % i: len(t.split()) for i, _, _, t in PLAN}
    words.update({"I%02d" % i: len(t.split()) for i, (_, _, _, t) in enumerate(INNER)})

    spk = load_spk()
    files = []
    for f in sorted(glob.glob(os.path.join(args.dir, "*.wav"))):
        k = os.path.basename(f)[:-4]
        if k not in who:
            continue
        a, sr = sf.read(f, dtype="float32", always_2d=True)
        a = a.mean(1)
        dur = len(a) / sr
        if dur < args.min_dur:
            print("  [门控剔除] %s %.2fs < %.1fs" % (k, dur, args.min_dur))
            continue
        files.append((k, f, dur))

    rows = []
    for k, f, dur in files:
        try:
            e = spk.embed(f)
        except Exception as ex:
            print("  [embed 失败] %s %s" % (k, ex))
            continue
        segs = RB.split_at_silence(
            sf.read(f, dtype="float32", always_2d=True)[0].mean(1), 48000, min_gap=0.22)
        v = sum(b - c for c, b in segs)
        rows.append({"k": k, "who": who[k], "e": e, "dur": dur,
                     "f0": f0_median(f),
                     "wpm": words[k] / v * 60 if v > 0 else 0.0})

    print("\n=== 角色级 SCS（Speaker Consistency Score，1.0 = 完全一致）===")
    for role, name in (("C", "Charles"), ("E", "Hooper")):
        sub = [r for r in rows if r["who"] == role]
        if len(sub) < 4:
            continue
        E = np.stack([r["e"] for r in sub])
        C, core = robust_centroid(E)
        s = E @ C
        mu, sd = float(s[core].mean()), float(s[core].std() + 1e-9)
        z = (mu - s) / sd
        loss = np.maximum(0.0, z - args.kappa)
        scs = float(np.exp(-args.alpha * loss.mean()))

        f0s = np.array([r["f0"] for r in sub])
        drift = (f0s.max() - f0s.min()) / max(np.median(f0s), 1e-6) * 100

        print("\n%s  n=%d（核心簇 %d）" % (name, len(sub), core.sum()))
        print("  SCS %.3f   cos 均值 %.3f  最低 %.3f  σ %.3f"
              % (scs, mu, s.min(), sd))
        print("  冷启动漂移 %.1f%%（%.0f–%.0fHz，中位 %.0f）%s"
              % (drift, f0s.min(), f0s.max(), np.median(f0s),
                 "  <3% 锁定" if drift < 3 else ("  3-5% 可用" if drift < 5 else
                                                ("  >5% 接缝可闻" if drift < 10 else "  >10% 像换人"))))
        print("  离中心最远的 5 条：")
        for i in np.argsort(s)[:5]:
            r = sub[i]
            print("    %-5s cos %.3f  z %+5.2f  F0 %3.0f  %.2fs  %s"
                  % (r["k"], s[i], (mu - s[i]) / sd, r["f0"], r["dur"],
                     "⚠ 超 2σ" if z[i] > args.kappa else ""))

        # 语速不连续率：同角色相邻话语
        sub2 = sorted(sub, key=lambda x: x["k"])
        jumps, groups = 0, 0
        for i in range(len(sub2) - 1):
            a, b = sub2[i]["wpm"], sub2[i + 1]["wpm"]
            if a <= 0 or b <= 0:
                continue
            groups += 1
            ratio = max(a / b, b / a)
            if ratio > args.tau_rate:
                jumps += 1
                print("    [语速跳 %.2fx] %s %.0f → %s %.0f"
                      % (ratio, sub2[i]["k"], a, sub2[i + 1]["k"], b))
        print("  RDR %.0f%%（%d/%d 对，阈值 %.1fx）"
              % (100.0 * jumps / max(groups, 1), jumps, groups, args.tau_rate))


if __name__ == "__main__":
    main()
