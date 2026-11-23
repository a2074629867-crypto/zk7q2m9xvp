"""_pref_compare.py —— 在同一批人工 A/B 偏好上，横向对比全部可用判据。

人工标注：_mt_labels_live.json（56 条可比：pick ∈ {42,1234}）
判据：
  1. audiobox CE / CU / PC / PQ（_aes_pref.json）
  2. sep（韵律分位分离度，来自 _mt_gate.json）
  3. verdict（PASS 优先）
  4. top1 是否内容词
  5. gap（top1 与最强内容词的落差）

对每个判据做二项检验 + 置换检验，避免「4 维 × 2 方向 = 8 个假设里挑最好」的过拟合。
"""
import json
import os
import random
import statistics

ROOT = "G:/_setup"
AES = os.path.join(ROOT, "_aes_pref.json")
GATE = os.path.join(ROOT, "_mt_gate.json")
LAB = os.path.join(ROOT, "_mt_labels_live.json")
SEEDS = ["42", "1234"]


def binom_p(k, n):
    """双侧二项检验（p=0.5），正态近似 + 连续性校正。"""
    if n == 0:
        return 1.0
    z = abs(k - n / 2) - 0.5
    z = z / (0.5 * n ** 0.5)
    # 正态尾
    import math
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def perm_test(hits, n, n_iter=5000, seed=7):
    """零分布：随机猜。返回 p 与零分布 p95。"""
    rng = random.Random(seed)
    accs = []
    for _ in range(n_iter):
        accs.append(sum(rng.random() < 0.5 for _ in range(n)) / n)
    accs.sort()
    acc = hits / n
    p = sum(1 for a in accs if a >= acc) / n_iter
    return p, accs[int(0.95 * (len(accs) - 1))]


def main():
    lab = json.load(open(LAB, encoding="utf-8"))
    gate = json.load(open(GATE, encoding="utf-8"))
    aes = json.load(open(AES, encoding="utf-8"))

    # gate: (uid, seed) -> row
    g = {}
    for r in gate:
        g[(str(r["uid"]), str(r["seed"]))] = r

    # aes: uid -> {seed: {dim: val}}
    a = {}
    for r in aes["rows"]:
        a[r["uid"]] = {s: r[s] for s in SEEDS if s in r}

    # 取交集
    uids = []
    for uid, v in lab.items():
        p = str(v.get("pick"))
        if p not in SEEDS:
            continue
        if uid in a and all(s in a[uid] for s in SEEDS):
            uids.append(uid)

    print("可比单元 %d" % len(uids))

    def hit_rate(fn, name):
        hits, valid = 0, 0
        for uid in uids:
            pick = str(lab[uid]["pick"])
            other = [s for s in SEEDS if s != pick][0]
            try:
                hp, ho = fn(uid, pick), fn(uid, other)
            except (KeyError, TypeError):
                continue
            if hp is None or ho is None or hp == ho:
                continue
            valid += 1
            if hp > ho:
                hits += 1
            elif hp < ho:
                hits += 0
            else:
                hits += 0.5
        if not valid:
            print("  %-22s 无有效样本" % name)
            return None
        acc = hits / valid
        best = max(acc, 1 - acc)
        p_bin = binom_p(round(hits), valid)
        p_perm, q95 = perm_test(round(hits), valid)
        print("  %-22s n=%2d  acc=%.3f  best=%.3f  二项p=%.3f  置换p=%.3f  零分布p95=%.3f"
              % (name, valid, acc, best, p_bin, p_perm, q95))
        return dict(n=valid, acc=acc, best=best, p_binom=p_bin, p_perm=p_perm, q95=q95)

    print("\n=== 各判据命中率（acc = 选中者分数更高的比例）===")
    res = {}
    for dim in ["CE", "CU", "PC", "PQ"]:
        res["aes_" + dim] = hit_rate(lambda u, s, d=dim: a[u][s][d], "audiobox " + dim)

    def sep_fn(u, s):
        r = g.get((u, s))
        if r is None or r.get("sep") is None:
            return None
        return r["sep"]
    res["sep"] = hit_rate(sep_fn, "sep（韵律分离度）")

    def cs_fn(u, s):
        r = g.get((u, s))
        if r is None:
            return None
        return {"PASS": 3, "SKIP": 2, "MANUAL": 1, "ARTIFACT": 0}[r["verdict"]]
    res["verdict"] = hit_rate(cs_fn, "门禁 verdict")

    def kind_fn(u, s):
        r = g.get((u, s))
        if r is None:
            return None
        return 1 if r.get("kind") in ("content", "focus") else 0
    res["content_top1"] = hit_rate(kind_fn, "top1 是内容词")

    def gap_fn(u, s):
        r = g.get((u, s))
        if r is None or r.get("gap") is None:
            return None
        return r["gap"]
    res["gap"] = hit_rate(gap_fn, "gap（top1 领先度）")

    def cov_fn(u, s):
        r = g.get((u, s))
        if r is None or r.get("cov") is None:
            return None
        return r["cov"]
    res["cov"] = hit_rate(cov_fn, "cov（对齐覆盖率）")

    print("\n=== 汇总（按 best 排序，best 已含方向翻转）===")
    rows = [(k, v) for k, v in res.items() if v]
    rows.sort(key=lambda kv: -kv[1]["best"])
    for k, v in rows:
        flag = "  << 显著" if v["p_perm"] < 0.05 else ""
        print("  %-16s best=%.3f  二项p=%.3f  置换p=%.3f%s" % (k, v["best"], v["p_binom"], v["p_perm"], flag))

    n_sig = sum(1 for _k, v in rows if v["p_perm"] < 0.05)
    print("\n%d 个判据中 %d 个达到 p<0.05；期望假阳性 %.1f 个（8 判据 × 0.05）"
          % (len(rows), n_sig, len(rows) * 0.05))

    json.dump(res, open(os.path.join(ROOT, "_pref_compare.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
