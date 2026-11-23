# -*- coding: utf-8 -*-
"""验证端：把「文本预测的方案」和「音频实测的 prominence/boundary」对齐打分。

    python _verify_accent.py --dir _wpt_out           # 全部已分析候选
    python _verify_accent.py --uid N0001              # 只看一句
    python _verify_accent.py --pick                   # 输出同句多候选的排序

判据（全部基于"排序"，对绝对尺度不敏感）：
  sep      = 内容词实测分位 − 功能词实测分位
             越大越好：说明重音落在内容词上、没落在虚词上
  focus_q  = 预测标 2 的词，实测分位（0 = 句内最轻，1 = 句内最重）→ 越大越好
  bnd_hit  = 预测有停顿的位置，实测 boundary 是否高于句中位数

分位定义：句内按 prominence 升序排名（0 = 最轻，1 = 最重）。

对同一句的 N 个候选：sep 最高的那条 = 与方案最像 = 应选的那条。
"""
import argparse
import difflib
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, "G:/_setup")
import _predict as P

PROM_DIR = "G:/_setup/_wpt_out"
STRESS = "G:/_setup/_stress_words.json"
PUNCT = set(".,;:!?-\"'()[]")


def read_prom(path):
    """返回 [(word, prominence, boundary)]，含标点。"""
    rows = []
    for line in open(path, encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        if len(f) < 6:
            continue
        try:
            rows.append((f[3], float(f[4]), float(f[5])))
        except ValueError:
            continue
    return rows


def pct_rank(vals, v):
    """v 在 vals 里的分位（0 = 最小）。用平均秩处理并列。"""
    if not vals:
        return 0.5
    less = sum(1 for x in vals if x < v)
    eq = sum(1 for x in vals if x == v)
    return (less + 0.5 * eq) / len(vals)


def align(pred_words, obs_words):
    """把预测的有效词与实测词对齐，返回 [(pred_idx, obs_idx)]。"""
    pw = [x.lower().strip(".,;:!?\"'") for x in pred_words]
    ow = [x.lower().strip(".,;:!?\"'") for x in obs_words]
    sm = difflib.SequenceMatcher(None, pw, ow, autojunk=False)
    pairs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                pairs.append((i1 + k, j1 + k))
        elif tag == "replace":
            # 长度相同才逐一对齐，否则丢弃这一段
            if (i2 - i1) == (j2 - j1):
                for k in range(i2 - i1):
                    pairs.append((i1 + k, j1 + k))
    return pairs


def score_one(pred, obs):
    """返回 dict(sep, focus_q, bnd_hit, n_aligned, detail)。"""
    obs_w = [(w, p, b) for w, p, b in obs if w not in PUNCT]
    pred_w = [x for x in pred["words"] if not x["punct"]]
    if not obs_w or not pred_w:
        return None

    pairs = align([x["w"] for x in pred_w], [w for w, _p, _b in obs_w])
    if len(pairs) < max(3, int(0.5 * len(obs_w))):
        return None

    proms = [p for _w, p, _b in obs_w]
    ct_q, fn_q, focus_q = [], [], []
    for pi, oi in pairs:
        pv = pred_w[pi]["prom"]
        q = pct_rank(proms, obs_w[oi][1])
        if pv is None:
            continue
        if pv == 0:
            fn_q.append(q)
        else:
            ct_q.append(q)
            if pv == 2:
                focus_q.append(q)
    if not ct_q or not fn_q:
        return None

    # 分位：0 = 句内最轻，1 = 句内最重
    # 内容词应该偏重（高分位），功能词应该偏轻（低分位），所以 sep 越大越好
    sep = (sum(ct_q) / len(ct_q)) - (sum(fn_q) / len(fn_q))

    # boundary：预测 b>=1 的位置（标点）对应前一个词的实测 boundary
    bnd_hi, bnd_all = [], []
    for i, x in enumerate(pred["words"]):
        if x["punct"] and x["bnd"] >= 1 and i > 0:
            # 找该标点前最近的有效词
            j = i - 1
            while j >= 0 and pred["words"][j]["punct"]:
                j -= 1
            if j < 0:
                continue
            hit = [oi for pi, oi in pairs if pi == j]
            if hit:
                bnd_hi.append(obs_w[hit[0]][2])
    bnd_all = [b for _w, _p, b in obs_w if b > 0]
    bnd_med = sorted(bnd_all)[len(bnd_all) // 2] if bnd_all else 0.0
    bnd_hit = (sum(bnd_hi) / len(bnd_hi)) if bnd_hi else 0.0

    return dict(sep=round(sep, 3),
                focus_q=round(sum(focus_q) / len(focus_q), 3) if focus_q else None,
                bnd_hit=round(bnd_hit, 3),
                bnd_med=round(bnd_med, 3),
                n=len(pairs),
                n_focus=len(focus_q))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=PROM_DIR)
    ap.add_argument("--uid", default=None)
    ap.add_argument("--pick", action="store_true")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    plan = {}
    stress = json.load(open(STRESS, encoding="utf-8"))
    for k, v in stress.items():
        uid = v["uid"]
        if uid in plan:
            continue
        plan[uid] = v["text"]

    files = sorted(f for f in os.listdir(a.dir) if f.endswith(".prom"))
    print("已分析候选 %d 个" % len(files))

    results = []
    skipped = 0
    for f in files:
        # 文件名: <seed_dir>__<uid>.prom
        base = f[:-5]
        if "__" not in base:
            continue
        seed_dir, uid = base.split("__", 1)
        if a.uid and uid != a.uid:
            continue
        text = plan.get(uid)
        if not text:
            skipped += 1
            continue
        pred = P.predict(text)
        obs = read_prom(os.path.join(a.dir, f))
        sc = score_one(pred, obs)
        if not sc:
            skipped += 1
            continue
        sc.update(uid=uid, seed=seed_dir, file=f)
        results.append(sc)

    if not results:
        print("没有可评分的候选（跳过 %d）" % skipped)
        return
    print("可评分 %d 个（跳过 %d）" % (len(results), skipped))

    seps = sorted(r["sep"] for r in results)
    q = lambda f: seps[min(len(seps) - 1, int(f * (len(seps) - 1)))]
    print("\n=== sep（功能词分位 − 内容词分位）===")
    print("  中位 %+.3f  p10 %+.3f  p90 %+.3f  >0 的占 %.0f%%"
          % (q(.5), q(.1), q(.9), 100 * sum(1 for x in seps if x > 0) / len(seps)))
    print("  （>0 = 重音落在内容词上，没落在虚词上）")

    fq = [r["focus_q"] for r in results if r["focus_q"] is not None]
    if fq:
        fq.sort()
        print("\n=== focus_q（预测标 2 的词，实测分位）===")
        print("  中位 %.3f  p10 %.3f  p90 %.3f  （0=最轻 1=最重，越大越好）"
              % (fq[len(fq) // 2], fq[int(.1 * len(fq))], fq[int(.9 * len(fq))]))

    bh = [r["bnd_hit"] for r in results if r["bnd_hit"] > 0]
    bm = [r["bnd_med"] for r in results if r["bnd_med"] > 0]
    if bh and bm:
        print("\n=== boundary ===")
        print("  预测有停顿处 实测 boundary 中位 %.3f | 句中所有非零 boundary 中位 %.3f"
              % (sorted(bh)[len(bh) // 2], sorted(bm)[len(bm) // 2]))

    # 同句多候选排序
    byuid = defaultdict(list)
    for r in results:
        byuid[r["uid"]].append(r)
    multi = {u: v for u, v in byuid.items() if len(v) >= 2}
    print("\n=== 同句多候选：按 sep 排序（应选第一条）===")
    agree = tot = 0
    for u, v in sorted(multi.items())[:10]:
        v = sorted(v, key=lambda x: -x["sep"])
        print("  %s  %s" % (u, "  ".join("%s sep%+.2f%s" %
                                          (x["seed"].replace("_mt_raw_", ""), x["sep"],
                                           "★" if i == 0 else "")
                                          for i, x in enumerate(v))))
        tot += 1
    if tot:
        print("\n  共 %d 句有 ≥2 候选" % len(multi))

    if a.json:
        json.dump(results, open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("\n写入 %s" % a.json)


if __name__ == "__main__":
    main()
