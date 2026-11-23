# -*- coding: utf-8 -*-
"""生成矩阵的情绪判定分析。

核心方法：效应量归一化
    同一个 ref、同一句话、同一个 seed，只改 emo 标签 ⇒ 差值可归因于标签。
    但原始 A/V/D 差值没有尺度感（0.03 算大还是小？）⇒ 除以**真人在该情绪上的组内 SD**，
    得到「相当于真人的几个标准差」。这比对绝对分数设阈值可靠得多：
    阈值会随模型、素材、语言漂移，效应量不会。
"""
import json, os, sys, collections, itertools
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

CONDS = ["base", "happy", "sad", "angry", "afraid", "calm"]
# 期望方向：标签 → (arousal 方向, valence 方向)
EXPECT = {
    "happy": (+1, +1), "sad": (-1, -1), "angry": (+1, -1),
    "afraid": (+1, -1), "calm": (-1, +0.3),
}
# 真人 style → 对应的 emo 标签（用来取组内 SD 与参考效应量）
REF_STYLE = {
    "happy": "happy", "sad": "sad", "angry": None,
    "afraid": "whisper", "calm": "default",
}
E2V_MAP = {
    "开心/happy": "happy", "难过/sad": "sad", "生气/angry": "angry",
    "中立/neutral": "neutral", "吃惊/surprised": "surprised",
    "恐惧/fearful": "afraid", "厌恶/disgusted": "disgusted",
    "其他/other": "other", "<unk>": "unk",
}
E2V_KEY = {"happy": "happy", "sad": "sad", "angry": "angry",
           "afraid": "fearful", "calm": "neutral"}


def load(name):
    p = os.path.join(OUT, name)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def real_sd():
    """真人在各 style 上的组内 SD（维度轴）。"""
    rows = load("real_vox_dim.jsonl")
    by = collections.defaultdict(list)
    for r in rows:
        by[r["style"]].append([r["score"]["arousal"], r["score"]["valence"], r["score"]["dominance"]])
    sd = {}
    for st, v in by.items():
        a = np.array(v)
        if len(a) >= 10:
            sd[st] = a.std(axis=0, ddof=1)
    return sd


def real_ref_effect():
    """真人 happy vs default 的 A/V 差（作为「真实情绪差」的标尺）。"""
    rows = load("real_vox_dim.jsonl")
    by = collections.defaultdict(list)
    for r in rows:
        by[r["style"]].append([r["score"]["arousal"], r["score"]["valence"], r["score"]["dominance"]])
    def med(st):
        a = np.array(by.get(st, []))
        return np.median(a, axis=0) if len(a) else np.zeros(3)
    return {st: med(st) for st in by}


def main():
    gen = load("gen_index.jsonl")
    vox = {r["path"]: r["score"] for r in load("gen_vox_dim.jsonl")}
    e2v = {r["path"]: r["score"] for r in load("gen_e2v.jsonl")}
    phy = {r["path"]: r["score"] for r in load("gen_phys.jsonl")}
    print("生成 %d 条；已判 vox=%d e2v=%d phys=%d" % (len(gen), len(vox), len(e2v), len(phy)))

    sd = real_sd()
    refeff = real_ref_effect()
    print("\n真人组内 SD（arousal/valence/dominance）：")
    for st in ("default", "happy", "sad", "whisper", "laughing", "confused"):
        if st in sd:
            print("  %-10s %.3f %.3f %.3f" % (st, *sd[st]))
    print("\n真人中位（base 参照）：")
    for st in ("default", "happy", "sad", "whisper"):
        if st in refeff:
            print("  %-10s A=%.3f V=%.3f D=%.3f" % (st, *refeff[st]))
    if "happy" in refeff and "default" in refeff:
        d = refeff["happy"] - refeff["default"]
        print("  真人 happy-default: ΔA=%+.3f ΔV=%+.3f ΔD=%+.3f" % tuple(d))

    # 按 (pid, cond) 汇总
    cell = collections.defaultdict(dict)
    for it in gen:
        cell[(it["pid"], it["cond"])] = it

    rows = []
    print("\n" + "=" * 96)
    print("%-11s %-7s %-6s %-9s %-9s %-9s %-28s" %
          ("ref", "cond", "dur", "A", "V", "D", "ΔA/SD (效应量)"))
    print("=" * 96)
    for pid in sorted(set(it["pid"] for it in gen)):
        b = cell.get((pid, "base"))
        bs = vox.get(b["path"]) if b else None
        for cond in CONDS:
            it = cell.get((pid, cond))
            if not it:
                continue
            s = vox.get(it["path"])
            if not s:
                continue
            if bs and cond != "base":
                da = s["arousal"] - bs["arousal"]
                dv = s["valence"] - bs["valence"]
                dd = s["dominance"] - bs["dominance"]
                base_sd = np.mean([sd[k][0] for k in ("default",) if k in sd]) if "default" in sd else 0.08
                ea = da / base_sd
                print("%-11s %-7s %-6.2f %-9.3f %-9.3f %-9.3f %+.2f (%+.3f)"
                      % (pid, cond, it["dur"], s["arousal"], s["valence"], s["dominance"], ea, da))
            else:
                print("%-11s %-7s %-6.2f %-9.3f %-9.3f %-9.3f —"
                      % (pid, cond, it["dur"], s["arousal"], s["valence"], s["dominance"]))
            rows.append(dict(pid=pid, cond=cond, dur=it["dur"], **s,
                             delta=None if (cond == "base" or not bs) else
                             dict(A=s["arousal"] - bs["arousal"], V=s["valence"] - bs["valence"],
                                  D=s["dominance"] - bs["dominance"]),
                             e2v=e2v.get(it["path"]), phys=phy.get(it["path"])))
        print("-" * 96)

    # 跨 ref 一致性：标签方向对不对
    print("\n" + "=" * 96)
    print("跨 8 个音色档的一致性（方向正确 = 与真人情绪方向同号）")
    print("=" * 96)
    base_sd = np.array(sd.get("default", [0.08, 0.09, 0.07]))
    summary = {}
    for cond in CONDS:
        if cond == "base":
            continue
        da, dv, dd = [], [], []
        for pid in sorted(set(it["pid"] for it in gen)):
            b = cell.get((pid, "base"))
            c = cell.get((pid, cond))
            if not (b and c and b["path"] in vox and c["path"] in vox):
                continue
            da.append(vox[c["path"]]["arousal"] - vox[b["path"]]["arousal"])
            dv.append(vox[c["path"]]["valence"] - vox[b["path"]]["valence"])
            dd.append(vox[c["path"]]["dominance"] - vox[b["path"]]["dominance"])
        if not da:
            continue
        da, dv, dd = np.array(da), np.array(dv), np.array(dd)
        exp_a, exp_v = EXPECT[cond]
        pos_a = float((np.sign(da) == exp_a).mean())
        pos_v = float((np.sign(dv) == exp_v).mean())
        # 单侧符号检验的 p 值（binomial n=8, 全对 p=1/256*2）
        from math import comb
        k = int((np.sign(da) == exp_a).sum()); n = len(da)
        p = sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n
        summary[cond] = dict(dA=float(da.mean()), dV=float(dv.mean()), dD=float(dd.mean()),
                             effA=float(da.mean() / base_sd[0]), effV=float(dv.mean() / base_sd[1]),
                             n=n, agree_a=pos_a, agree_v=pos_v, p=p)
        print("%-8s n=%d  平均 ΔA=%+.3f (效应 %.2fσ, 同向 %.0f%%, p=%.4f)  ΔV=%+.3f (%.2fσ, 同向 %.0f%%)  ΔD=%+.3f"
              % (cond, n, da.mean(), da.mean() / base_sd[0], 100 * pos_a, p,
                 dv.mean(), dv.mean() / base_sd[1], 100 * pos_v, dd.mean()))

    # e2v 目标类概率变化
    if e2v:
        print("\n" + "=" * 96)
        print("emotion2vec 的目标类概率变化（同 ref：标签 vs base）")
        print("=" * 96)
        for cond in CONDS:
            if cond == "base":
                continue
            key = E2V_KEY.get(cond)
            ups = []
            for pid in sorted(set(it["pid"] for it in gen)):
                b = cell.get((pid, "base")); c = cell.get((pid, cond))
                if not (b and c and b["path"] in e2v and c["path"] in e2v):
                    continue
                def g(sc):
                    for k, v in sc.items():
                        if k == "_top" or k.startswith("_"):
                            continue
                        if E2V_MAP.get(k) == key:
                            return v
                    return 0.0
                ups.append(g(e2v[c["path"]]) - g(e2v[b["path"]]))
            if ups:
                ups = np.array(ups)
                print("%-8s 目标类 '%s' 概率 Δ 平均 %+.3f，上升 %d/%d"
                      % (cond, key, ups.mean(), int((ups > 0).sum()), len(ups)))

    json.dump(dict(rows=rows, summary=summary,
                   real_sd={k: v.tolist() for k, v in sd.items()},
                   real_med={k: v.tolist() for k, v in refeff.items()}),
              open(os.path.join(OUT, "gen_analysis.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n已写 out/gen_analysis.json")


if __name__ == "__main__":
    main()
