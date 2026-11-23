# -*- coding: utf-8 -*-
"""用 wpt 的 prominence/boundary 判据，检验能否预测 60 条人工偏好。

对照基线：centroid 最低 = 74%（58 条上的现有最优规则）

判据：
  sep      = 内容词分位 − 功能词分位（大 = 重音落位对）
  focus_q  = 预测标 2 的词的分位（大 = 核心重音落在该落的词上）
  bnd      = 预测停顿处的实测 boundary（大 = 停顿位置对）
  combo    = sep + 0.5*focus_q

同时看：sep 作为"门禁"的效果（低于阈值的候选占比）。
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, "G:/_setup")
from _verify_accent import read_prom, score_one, align, PUNCT
import _predict as P

LAB = "G:/_setup/_mt_labels_live.json"
SC = "G:/_setup/_mt_score_ch%d.json"
STRESS = "G:/_setup/_stress_words.json"
OUT = "G:/_setup/_wpt_out"


def main():
    lab = json.load(open(LAB, encoding="utf-8"))
    sc = {}
    for ch in (1, 2, 3):
        for r in json.load(open(SC % ch, encoding="utf-8")):
            sc[r["id"]] = r
    texts = {}
    for k, v in json.load(open(STRESS, encoding="utf-8")).items():
        texts.setdefault(v["uid"], v["text"])

    # 加载所有已分析的候选
    obs_by = {}
    for f in os.listdir(OUT):
        if not f.endswith(".prom"):
            continue
        base = f[:-5]
        if "__" not in base:
            continue
        seed_dir, uid = base.split("__", 1)
        obs_by[(uid, seed_dir)] = read_prom(os.path.join(OUT, f))

    rows = []
    for uid, v in lab.items():
        pick = str(v.get("pick"))
        if pick in ("None", "none"):
            continue
        r = sc.get(uid)
        text = texts.get(uid)
        if not r or not text:
            continue
        pred = P.predict(text)
        cm = {str(c["seed"]): c for c in r["cands"]}
        cand_scores = {}
        for seed, c in cm.items():
            # 候选的 path 字段是 None，seed 直接映射到原始目录名
            sd = "_mt_raw_s" + seed
            obs = obs_by.get((uid, sd))
            if not obs:
                continue
            s = score_one(pred, obs)
            if s:
                cand_scores[seed] = (s, c)
        if len(cand_scores) < 2:
            continue
        if pick not in cand_scores:
            continue
        rows.append(dict(uid=uid, pick=pick, cs=cand_scores))

    print("可用标注 %d 条（有 wpt 数据且 ≥2 候选）" % len(rows))
    if not rows:
        return

    # 逐判据准确率
    KEYS = [("sep", 1), ("focus_q", 1), ("bnd_hit", 1), ("sep", -1)]
    print()
    print("%-16s %6s %6s" % ("判据", "命中", "比例"))
    print("-" * 32)
    for key, sign in KEYS:
        ok = t = 0
        for r in rows:
            vals = [(seed, s[key]) for seed, (s, c) in r["cs"].items()
                    if s.get(key) is not None]
            if len(vals) < 2:
                continue
            t += 1
            best = max(vals, key=lambda z: sign * z[1])[0]
            if best == r["pick"]:
                ok += 1
        if t:
            print("%-16s %5d %5.0f%%  (n=%d)" % (key + ("(低)" if sign < 0 else ""),
                                                 ok, 100 * ok / t, t))

    # centroid 基线
    ok = t = 0
    for r in rows:
        vals = [(seed, c["centroid"]) for seed, (s, c) in r["cs"].items()]
        t += 1
        if min(vals, key=lambda z: z[1])[0] == r["pick"]:
            ok += 1
    print("%-16s %5d %5.0f%%  (n=%d)" % ("centroid 低", ok, 100 * ok / t, t))

    # 组合
    for w in (0.3, 0.5, 1.0):
        ok = t = 0
        for r in rows:
            vals = []
            for seed, (s, c) in r["cs"].items():
                fq = s.get("focus_q")
                if fq is None:
                    continue
                vals.append((seed, s["sep"] + w * fq))
            if len(vals) < 2:
                continue
            t += 1
            if max(vals, key=lambda z: z[1])[0] == r["pick"]:
                ok += 1
        if t:
            print("%-16s %5d %5.0f%%  (n=%d)" % ("sep+%.1f*focus_q" % w, ok, 100 * ok / t, t))

    # sep 分布：作为门禁
    allsep = [s["sep"] for r in rows for s, _c in r["cs"].values()]
    allsep.sort()
    q = lambda f: allsep[min(len(allsep) - 1, int(f * (len(allsep) - 1)))]
    print()
    print("=== sep 分布（%d 个候选）===" % len(allsep))
    print("  中位 %.3f  p10 %.3f  p25 %.3f  p90 %.3f"
          % (q(.5), q(.1), q(.25), q(.9)))
    for thr in (0.0, 0.1, 0.2, 0.3):
        n = sum(1 for x in allsep if x < thr)
        print("  sep < %.1f（判为重音落位失败）: %d 个 = %.0f%%"
              % (thr, n, 100 * n / len(allsep)))

    # 冲突：人工选择 vs centroid / sep
    print()
    print("=== 冲突分析 ===")
    agree = disagree = 0
    for r in rows:
        cen = min([(seed, c["centroid"]) for seed, (s, c) in r["cs"].items()],
                  key=lambda z: z[1])[0]
        sep = max([(seed, s["sep"]) for seed, (s, c) in r["cs"].items()],
                  key=lambda z: z[1])[0]
        if cen == sep:
            agree += 1
        else:
            disagree += 1
    print("  centroid 与 sep 给出同一答案: %d 条；冲突: %d 条" % (agree, disagree))


if __name__ == "__main__":
    main()
