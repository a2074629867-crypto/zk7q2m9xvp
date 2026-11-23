# -*- coding: utf-8 -*-
"""书级评分：书内相对归一 + 按角色/按章聚合

回答的问题：**SER 逐条绝对打分能不能给有声书用？**
做法：拿生产链已交付的 60 条真实对白（ch123_final，带说话人与预期情绪），
分别用三种归一化去区分「预期 sad」和「预期 calm」，看哪一种能分开。

三种口径：
  raw      —— 绝对分（模型原值，跨库可比，但受域偏移与音色差异污染）
  book     —— 全书 z（同一本书内归一）
  character—— 同角色 z（先按说话人分组再归一，消除音色基线差异）

另外算两项有声书专属指标：
  dynamics  —— 同一角色内的动态范围（p10~p90），太窄=念得平
  monotony  —— 相邻句 |Δz| 中位数，太小=没有句间起伏（有声书靠对比，不靠绝对值）
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")


def auc(pos, neg):
    """正类(pos)得分高于负类(neg)的概率，0.5=无区分力。"""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan")
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    return (gt + 0.5 * eq) / (len(pos) * len(neg))


def zscores(vals, keys):
    """按 keys 分组做 z；返回与原数组等长的 z。"""
    out = np.zeros(len(vals), float)
    g = collections.defaultdict(list)
    for i, k in enumerate(keys):
        g[k].append(i)
    for k, idx in g.items():
        v = np.array([vals[i] for i in idx], float)
        m, s = v.mean(), v.std(ddof=1) if len(v) > 1 else 0.0
        for i in idx:
            out[i] = 0.0 if s < 1e-9 else (vals[i] - m) / s
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav-dir", default="G:/_setup/ch123_final")
    ap.add_argument("--labels", default="G:/_setup/_ch123_check.json")
    ap.add_argument("--out", default="G:/_setup/emo_bench/out/book_judge.json")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    import ser as S

    raw = json.load(open(a.labels, encoding="utf-8"))
    meta = {k: v for k, v in raw.items()
            if isinstance(v, dict) and v.get("who")}
    ids = sorted(meta)
    if a.limit:
        ids = ids[:a.limit]

    V = S.get("vox_dim")
    rows = []
    for i, k in enumerate(ids, 1):
        p = os.path.join(a.wav_dir, k + ".wav")
        if not os.path.exists(p):
            continue
        ph = S.phys(p)
        dm = V.score(p)
        m = meta[k]
        rows.append(dict(id=k, who=m.get("who"), emo=m.get("emo"),
                         text=(m.get("text") or "")[:60],
                         dur=ph["dur"], span=ph["f0_p90"] - ph["f0_p10"],
                         f0=ph["f0_med"], db=ph["speech_db"], hnr=ph["hnr"],
                         A=dm["arousal"], D=dm["dominance"], V=dm["valence"]))
        print("  [%d/%d] %-6s %-6s %-11s A=%.2f 跨度%3.0f dur%.2fs"
              % (i, len(ids), k, m.get("who"), m.get("emo") or "-",
                 dm["arousal"], ph["f0_p90"] - ph["f0_p10"], ph["dur"]))

    n = len(rows)
    print("\n已打分 %d 条" % n)

    keys_book = ["book"] * n
    keys_who = [r["who"] for r in rows]

    metrics = {}
    for f in ("A", "D", "span", "f0"):
        v = np.array([r[f] for r in rows], float)
        metrics[f] = dict(
            raw=v,
            book=zscores(v, keys_book),
            character=zscores(v, keys_who),
        )

    # ── 1. 可信度区间 ──
    dur = np.array([r["dur"] for r in rows], float)
    print("\n" + "=" * 92)
    print("一、样本可信度（vox_dim 训练时滤掉 <3s 与 >15s）")
    print("  时长 min %.2f / 中位 %.2f / max %.2f" % (dur.min(), np.median(dur), dur.max()))
    print("  <3s  %d 条（%.0f%%）⇒ 模型自标不可靠" % ((dur < 3).sum(), 100 * (dur < 3).mean()))
    print("  >15s %d 条" % (dur > 15).sum())
    print("  A 落点 min %.2f / 中位 %.2f / max %.2f（模型输出上限 0.82）"
          % (metrics["A"]["raw"].min(), np.median(metrics["A"]["raw"]), metrics["A"]["raw"].max()))

    # ── 2. 生产链电平归一的副作用 ──
    db = np.array([r["db"] for r in rows], float)
    print("\n二、生产链已做 −24dBFS 电平归一 ⇒ 音量轴被抹平")
    print("  speech_db  p10 %.1f / 中位 %.1f / p90 %.1f  跨度仅 %.1f dB"
          % (np.percentile(db, 10), np.median(db), np.percentile(db, 90),
             np.percentile(db, 90) - np.percentile(db, 10)))
    print("  ⇒ 「喊 vs 演」的判据（ΔdB）在成品上不成立；强度只能看 F0 跨度与 A")

    # ── 3. 核心检验：三种归一化能否分开预期情绪 ──
    lab = np.array([r["emo"] or "-" for r in rows])
    print("\n" + "=" * 92)
    print("三、核心检验：预期 sad(%d) vs calm(%d)，三种归一化谁分得开"
          % ((lab == "sad").sum(), (lab == "calm").sum()))
    print("  （AUC 越高越好；0.5 = 完全分不开）")
    print("  %-10s %-9s %-9s %-9s %-9s" % ("口径", "A", "F0跨度", "D", "最佳"))

    for f in ("A", "span", "D"):
        line = []
        for scope in ("raw", "book", "character"):
            v = metrics[f][scope]
            s = auc(v[lab == "sad"], v[lab == "calm"])
            # 方向不对就翻过来（只看区分力）
            line.append(max(s, 1 - s))
        print("  %-10s %-9.3f %-9.3f %-9.3f %-9.3f"
              % (f, line[0], line[1], line[2], max(line)))

    # 两两组合（A + 跨度）线性可分性：用简单标准化后相加
    for scope in ("raw", "book", "character"):
        v = metrics["A"][scope] + 0.5 * metrics["span"][scope]
        s = auc(v[lab == "sad"], v[lab == "calm"])
        print("  %-10s A+0.5·跨度 → AUC %.3f" % (scope, max(s, 1 - s)))

    # ── 4. 有序性检查 ──
    print("\n四、有序性：预期情绪的平均落点（同一角色内归一后应单调）")
    order = ["sad", "calm", "happy"]
    for scope in ("raw", "character"):
        vals = []
        for e in order:
            m = lab == e
            if m.sum() == 0:
                vals.append("%s n/a" % e)
                continue
            vals.append("%s %+.2f" % (e, metrics["A"][scope][m].mean()))
        print("  %-10s %s" % (scope, "   ".join(vals)))
    print("  说明：预期标签来自生产脚本，happy 只有 %d 条，只能看方向" % (lab == "happy").sum())

    # ── 5. 有声书专属：动态范围与句间对比 ──
    print("\n" + "=" * 92)
    print("五、书内动态范围与句间对比（有声书的表达力在「相对相邻句」，不在绝对分）")
    for who in sorted(set(keys_who)):
        m = np.array([r["who"] == who for r in rows])
        A = metrics["A"]["raw"][m]
        sp = metrics["span"]["raw"][m]
        print("  角色 %s（%d 条）: A  p10 %.2f / p90 %.2f → 动态范围 %.2f（%.2fσ）"
              % (who, m.sum(), np.percentile(A, 10), np.percentile(A, 90),
                 np.percentile(A, 90) - np.percentile(A, 10),
                 (np.percentile(A, 90) - np.percentile(A, 10)) / max(A.std(ddof=1), 1e-9)))
        print("                  跨度 p10 %.0f / p90 %.0f Hz" % (np.percentile(sp, 10), np.percentile(sp, 90)))

    # 相邻句对比：按谁分组、保持文件顺序
    for scope in ("raw", "character"):
        dz = []
        for who in set(keys_who):
            idx = [i for i, r in enumerate(rows) if r["who"] == who]
            v = metrics["A"][scope]
            dz += [abs(v[idx[j + 1]] - v[idx[j]]) for j in range(len(idx) - 1)]
        dz = np.array(dz)
        print("  %-10s 相邻同角色句 |ΔA| 中位 %.2fσ，<0.3σ 的占 %.0f%%"
              % (scope, np.median(dz), 100 * (dz < 0.3).mean()))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(dict(rows=rows, metrics={f: {k: v.tolist() for k, v in d.items()}
                                       for f, d in metrics.items()}),
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写出 %s" % a.out)


if __name__ == "__main__":
    main()
