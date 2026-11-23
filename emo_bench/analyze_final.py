# -*- coding: utf-8 -*-
"""情绪矩阵最终分析 —— 回答三个问题：

  Q1  emo 标签到底改变了什么？（同 ref、同文本、同 seed，只差标签 ⇒ 配对可归因）
  Q2  哪个 ref 天生适合哪个情绪？（换 ref 的效应 vs 加标签的效应，谁大）
  Q3  "主音色为主 + 不同情绪换 ref" 这条策略，实测该怎么做？

方法学（这是本文件唯一的立场）：
  · 差值一律除以**真人合并组内 SD**换算成 σ，不设绝对阈值 —— 阈值会随模型/素材/语言漂移
  · 方向一致性必须跨 8 个 ref 看，单条比较会被采样噪声吃掉（见 repeat_test.py）
  · valence 只在 arousal 足够高时才当判据：真人 happy vs default 的 V 只差 0.06σ，
    V 轴在「中性→开心」这条路上几乎没有信号，拿它做阈值就是自欺
"""
import json, os, collections, itertools
from math import comb
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CONDS = ["base", "happy", "sad", "angry", "afraid", "calm"]

# 标签 → 期望方向（arousal, valence）。valence 权重单独控制，见 V_GATE
EXPECT = {"happy": (+1, +1), "sad": (-1, -1), "angry": (+1, -1),
          "afraid": (+1, -1), "calm": (-1, +0.3)}
# 真人里 valence 真正分得开的组合才有判据资格（见 analyze_real 的 pairwise AUC）
V_GATE = {"happy": False, "sad": True, "angry": True, "afraid": True, "calm": True}

E2V_MAP = {"开心/happy": "happy", "难过/sad": "sad", "生气/angry": "angry",
           "中立/neutral": "neutral", "吃惊/surprised": "surprised",
           "恐惧/fearful": "afraid", "厌恶/disgusted": "disgusted",
           "其他/other": "other", "<unk>": "unk"}
E2V_KEY = {"happy": "happy", "sad": "sad", "angry": "angry",
           "afraid": "fearful", "calm": "neutral"}

EFF_WEAK, EFF_OK, EFF_STRONG = 0.5, 1.0, 2.0


def load(name, out=OUT):
    p = os.path.join(out, name)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def pooled_sd():
    """真人 A/V/D 的合并组内 SD（8 style 按自由度加权）。"""
    by = collections.defaultdict(list)
    for r in load("real_vox_dim.jsonl"):
        by[r["style"]].append([r["score"]["arousal"], r["score"]["valence"], r["score"]["dominance"]])
    num = np.zeros(3); den = 0
    for st, v in by.items():
        a = np.array(v)
        num += ((a - a.mean(0)) ** 2).sum(0); den += len(a) - 1
    return np.sqrt(num / den)


def real_med():
    by = collections.defaultdict(list)
    for r in load("real_vox_dim.jsonl"):
        by[r["style"]].append([r["score"]["arousal"], r["score"]["valence"], r["score"]["dominance"]])
    return {st: np.median(np.array(v), 0) for st, v in by.items()}


def sign_test(k, n, direction=+1):
    """单侧符号检验：至少 k/n 与期望方向同号。"""
    if n == 0:
        return 1.0
    kk = k if direction > 0 else n - k
    return sum(comb(n, i) for i in range(kk, n + 1)) / 2 ** n


def e2v_prob(score, key):
    if not score:
        return None
    for k, v in score.items():
        if k.startswith("_"):
            continue
        if E2V_MAP.get(k) == key:
            return float(v)
    return 0.0


def main():
    gen = load("gen_index.jsonl")
    vox = {r["path"]: r["score"] for r in load("gen_vox_dim.jsonl") if r.get("score")}
    phy = {r["path"]: r["score"] for r in load("gen_phys.jsonl") if r.get("score")}
    e2v = {r["path"]: r["score"] for r in load("gen_e2v.jsonl") if r.get("score")}
    SD = pooled_sd()
    RM = real_med()
    sA, sV, sD = SD

    print("=" * 100)
    print("生成 %d 条  |  已判 vox=%d phys=%d e2v=%d" % (len(gen), len(vox), len(phy), len(e2v)))
    print("=" * 100)
    print("真人合并组内 SD（效应量分母）：A=%.4f  V=%.4f  D=%.4f" % (sA, sV, sD))
    if "default" in RM and "happy" in RM:
        d = (RM["happy"] - RM["default"]) / SD
        print("真人 happy vs default 的效应量：ΔA=%+.2fσ  ΔV=%+.2fσ  ΔD=%+.2fσ" % tuple(d))
        print("  ⇒ 真人自己「开心」比「中性」也只在 arousal 上拉 1σ 出头，valence 几乎不动")
    if "sad" in RM and "default" in RM:
        d = (RM["sad"] - RM["default"]) / SD
        print("真人 sad   vs default 的效应量：ΔA=%+.2fσ  ΔV=%+.2fσ  ΔD=%+.2fσ" % tuple(d))

    cell = {(it["pid"], it["cond"]): it for it in gen}
    pids = sorted({it["pid"] for it in gen})

    # ───────── Q1 标签效应（同 ref 配对）─────────
    print("\n" + "=" * 100)
    print("Q1  标签效应（每个 ref 内，带标签版 vs 无标签 base 版）")
    print("=" * 100)
    print("%-8s %-3s %-8s %-8s %-8s %-7s %-7s %-6s %-6s %s"
          % ("标签", "n", "ΔA", "ΔV", "ΔD", "ΔA/σ", "ΔV/σ", "A同向", "V同向", "p(A)"))
    summary = {}
    for cond in CONDS:
        if cond == "base":
            continue
        ea, ev = EXPECT[cond]
        da, dv, dd = [], [], []
        for pid in pids:
            b, c = cell.get((pid, "base")), cell.get((pid, cond))
            if not (b and c and b["path"] in vox and c["path"] in vox):
                continue
            da.append(vox[c["path"]]["arousal"] - vox[b["path"]]["arousal"])
            dv.append(vox[c["path"]]["valence"] - vox[b["path"]]["valence"])
            dd.append(vox[c["path"]]["dominance"] - vox[b["path"]]["dominance"])
        if not da:
            continue
        da, dv, dd = np.array(da), np.array(dv), np.array(dd)
        n = len(da)
        kA = int((np.sign(da) == ea).sum())
        kV = int((np.sign(dv) == ev).sum())
        pA = sign_test(kA, n, +1)
        summary[cond] = dict(n=n, dA=da.mean(), dV=dv.mean(), dD=dd.mean(),
                             effA=da.mean() / sA, effV=dv.mean() / sV, effD=dd.mean() / sD,
                             agreeA=kA / n, agreeV=kV / n, pA=pA,
                             medianA=float(np.median(da)))
        print("%-8s %-3d %+8.3f %+8.3f %+8.3f %+7.2f %+7.2f %4d/%-3d %4d/%-3d %.4f"
              % (cond, n, da.mean(), dv.mean(), dd.mean(), da.mean() / sA, dv.mean() / sV,
                 kA, n, kV, n, pA))

    # ───────── Q2 ref 天生适合度 ─────────
    print("\n" + "=" * 100)
    print("Q2  每个 ref 在「无标签」状态下的天然位置（相对全体 base 均值，单位 σ）")
    print("=" * 100)
    bases = [(pid, vox[cell[(pid, "base")]["path"]]) for pid in pids
             if (pid, "base") in cell and cell[(pid, "base")]["path"] in vox]
    if bases:
        mA = np.mean([v["arousal"] for _, v in bases])
        mV = np.mean([v["valence"] for _, v in bases])
        print("%-11s %-7s %-8s %-8s %-8s" % ("ref", "dur", "A(σ)", "V(σ)", "D"))
        for pid, v in sorted(bases, key=lambda x: -(x[1]["arousal"] - mA)):
            print("%-11s %-7.2f %+8.2f %+8.2f %8.3f"
                  % (pid, cell[(pid, "base")]["dur"], (v["arousal"] - mA) / sA,
                     (v["valence"] - mV) / sV, v["dominance"]))
        print("  ⇒ 这就是「换 ref」能直接拿到的偏移量；和 Q1 的标签效应比大小即知该换 ref 还是打标签")

    # ───────── Q3 目标情绪 × 全部组合 ─────────
    print("\n" + "=" * 100)
    print("Q3  每个目标情绪的最佳组合（按「离目标方向的距离」排序，含三通道佐证）")
    print("=" * 100)
    # 目标锚点：happy/sad 用真人中位；angry/afraid/calm 真人没有对应 style，
    # 用「方向 + 幅度」定义：angry 取 happy 的 A 但 V 压低，afraid 取 whisper，calm 取 default 的 A 再低
    anchor = {}
    if "happy" in RM:
        anchor["happy"] = RM["happy"]
    if "sad" in RM:
        anchor["sad"] = RM["sad"]
    if "whisper" in RM:
        anchor["afraid"] = np.array([RM["whisper"][0], RM["whisper"][1], RM["whisper"][2]])
        anchor["calm"] = np.array([RM["whisper"][0] + 0.05, RM["default"][1], RM["default"][2]])
    if "happy" in RM:
        anchor["angry"] = np.array([RM["laughing"][0], RM["sad"][1] + 0.05, RM["happy"][2]])

    best = {}
    for tgt, anc in anchor.items():
        ea, ev = EXPECT[tgt]
        cand = []
        for (pid, cond), it in cell.items():
            s = vox.get(it["path"])
            if not s:
                continue
            v = np.array([s["arousal"], s["valence"], s["dominance"]])
            # 只沿该情绪有判据的轴算距离
            w = np.array([1.0, 1.0 if V_GATE.get(tgt) else 0.0, 0.0])
            dist = float(np.linalg.norm((v - anc) * w / SD))
            cand.append((dist, pid, cond, s, it))
        cand.sort(key=lambda x: x[0])
        best[tgt] = cand[:3]
        print("\n【%s】目标锚点 A=%.2f V=%.2f（真人 %s）" % (tgt, anc[0], anc[1],
              "happy" if tgt == "happy" else ("sad" if tgt == "sad" else
              ("whisper" if tgt == "afraid" else ("default" if tgt == "calm" else "构造")))))
        for dist, pid, cond, s, it in cand[:5]:
            mark = ""
            if cond == "base":
                mark = "（无标签）"
            ep = e2v_prob(e2v.get(it["path"]), E2V_KEY[tgt])
            print("  %-11s %-7s 距离%.2fσ  A=%.3f V=%.3f D=%.3f%s%s"
                  % (pid, cond, dist, s["arousal"], s["valence"], s["dominance"], mark,
                     "" if ep is None else "  e2v目标类=%.2f" % ep))

    # ───────── Q3b 主音色 vs 专用 ref ─────────
    print("\n" + "=" * 100)
    print("Q3b 「主音色 + 标签」vs「专用 ref + 标签」vs「专用 ref 无标签」")
    print("=" * 100)
    MAIN = {"C": "C_normal", "E": "E_calm"}
    for tgt in CONDS[1:]:
        ea, ev = EXPECT[tgt]
        print("\n【%s】期望 ΔA %+dσ 方向" % (tgt, ea))
        for pre, main in MAIN.items():
            rows = []
            for pid in pids:
                if pid[0] != pre:
                    continue
                b, c = cell.get((pid, "base")), cell.get((pid, tgt))
                if not (b and c and b["path"] in vox and c["path"] in vox):
                    continue
                dA = (vox[c["path"]]["arousal"] - vox[b["path"]]["arousal"]) / sA
                dV = (vox[c["path"]]["valence"] - vox[b["path"]]["valence"]) / sV
                offset = (vox[b["path"]]["arousal"] - np.mean([v["arousal"] for _, v in bases])) / sA
                rows.append((pid, dA, dV, offset))
            if not rows:
                continue
            print("  %s 系：" % pre)
            for pid, dA, dV, off in sorted(rows, key=lambda x: -x[1]):
                tag = " ★主音色" if pid == main else ""
                print("    %-11s 标签效应 ΔA=%+.2fσ ΔV=%+.2fσ   |  ref 本身 A 偏移 %+.2fσ%s"
                      % (pid, dA, dV, off, tag))

    # ───────── 落盘 ─────────
    def conv(o):
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        raise TypeError(type(o))

    json.dump(dict(sd=dict(A=float(sA), V=float(sV), D=float(sD)),
                   label_effect={k: {kk: float(vv) for kk, vv in v.items()}
                                 for k, v in summary.items()},
                   best={k: [dict(pid=p, cond=c, dist=d, **{kk: float(vv) for kk, vv in s.items()})
                             for d, p, c, s, _ in v] for k, v in best.items()}),
              open(os.path.join(OUT, "gen_final.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n已写 out/gen_final.json")


if __name__ == "__main__":
    main()
