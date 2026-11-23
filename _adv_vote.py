# -*- coding: utf-8 -*-
"""3×DeepSeek + 2×HY3 的 5 票投票统计。

对 55 个有音频的单元：
  - 每票选 1 个词或 none
  - 统计票型分布、同源/异源一致性
  - 与声学 sps 对账
"""
import argparse
import json
import os
import re
import statistics
from collections import Counter, defaultdict

ROOT = "G:/_setup"
VDIR = os.path.join(ROOT, "_adv_vote")
RATERS = [("ds1", "DS#1"), ("ds2", "DS#2"), ("ds3", "DS#3"),
          ("hy1", "HY3#1"), ("hy2", "HY3#2")]


def load(tag):
    out = {}
    for f in sorted(os.listdir(VDIR)):
        m = re.match(r"out_%s_p\d+\.json$" % re.escape(tag), f)
        if not m:
            continue
        t = open(os.path.join(VDIR, f), encoding="utf-8").read()
        j = re.search(r"\[.*\]", t, re.S)
        if not j:
            print("  !! %s 无 JSON" % f)
            continue
        try:
            for r in json.loads(j.group(0)):
                if "id" in r:
                    p = str(r.get("pick", "")).strip()
                    out[str(r["id"])] = "none" if p.lower() == "none" else p
        except Exception as e:
            print("  !! %s 解析失败 %s" % (f, e))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--acoustic", default=os.path.join(ROOT, "_adv_now.json"))
    a = ap.parse_args()

    ids = json.load(open(os.path.join(VDIR, "ids.json"), encoding="utf-8"))
    print("=== 载入（%d 个单元）===" % len(ids))
    votes = {}
    for tag, name in RATERS:
        d = load(tag)
        votes[tag] = d
        print("  %-6s %-7s %d/%d 条" % (name, tag, len(d), len(ids)))

    complete = [i for i in ids if all(i in votes[t] for t, _ in RATERS)]
    print("\n五票齐全：%d / %d" % (len(complete), len(ids)))
    if not complete:
        raise SystemExit("没有五票齐全的条目")

    # 票型
    dist = Counter()
    full_agree = 0
    for i in complete:
        picks = {t: votes[t][i].lower() for t, _ in RATERS}
        c = Counter(picks.values())
        dist[len(c)] += 1
        if len(c) == 1:
            full_agree += 1
    print("\n=== 每条的互异选择数 ===")
    for k in sorted(dist):
        print("  %d 种不同答案：%2d 条  %5.1f%%" % (k, dist[k], 100.0 * dist[k] / len(complete)))
    print("  **五票全同：%d 条 = %.1f%%**" % (full_agree, 100.0 * full_agree / len(complete)))

    # 各组内部一致
    def agree_rate(tags):
        n = 0
        for i in complete:
            ps = {votes[t][i].lower() for t in tags}
            if len(ps) == 1:
                n += 1
        return n, 100.0 * n / len(complete)

    n3, r3 = agree_rate(["ds1", "ds2", "ds3"])
    n2, r2 = agree_rate(["hy1", "hy2"])
    print("\n=== 内部一致性 ===")
    print("  3×DS  全同 %2d 条 = %5.1f%%" % (n3, r3))
    print("  2×HY3 全同 %2d 条 = %5.1f%%" % (n2, r2))

    # 标注倾向
    print("\n=== 标注倾向 ===")
    for tag, name in RATERS:
        k = sum(1 for i in complete if votes[tag][i].lower() != "none")
        print("  %-7s 标 %2d / %d = %5.1f%%" % (name, k, len(complete), 100.0 * k / len(complete)))

    # 多数票
    maj = {}
    for i in complete:
        ps = [votes[t][i].lower() for t, _ in RATERS]
        c = Counter(ps)
        top, cnt = c.most_common(1)[0]
        maj[i] = (top, cnt, ps)
    print("\n=== 多数票分布 ===")
    for k in (5, 4, 3, 2):
        n = sum(1 for v in maj.values() if v[1] == k)
        print("  %d/5 票：%2d 条  %5.1f%%" % (k, n, 100.0 * n / len(complete)))
    n_tie = sum(1 for v in maj.values() if v[1] == 2 and len(set(v[2])) > 1)
    print("  （其中 2/5 且存在并列：%d 条）" % n_tie)

    # 与声学对账
    acc = {}
    if os.path.exists(a.acoustic):
        for r in json.load(open(a.acoustic, encoding="utf-8")):
            acc.setdefault(r["uid"], []).append(r)
    key = {r["aid"]: r["uid"] for r in json.load(open(
        os.path.join(ROOT, "_adv_final.json"), encoding="utf-8"))}

    print("\n=== 与声学对账（5/5 全票的单元）===")
    rows = []
    for i in complete:
        top, cnt, _ps = maj[i]
        if cnt < 5 or top == "none":
            continue
        uid = key.get(i)
        obs = [r for r in acc.get(uid, []) if r["adv"].lower() == top]
        cand = [r["sps"] for r in obs if r.get("sps") is not None]
        sps = max(cand) if cand else None
        rows.append((i, uid, top, sps,
                     "SLOWED" if sps and sps >= 0.28 else
                     ("WEAK" if sps and sps >= 0.18 else
                      ("FLAT" if sps else "MISSING"))))
    c = Counter(r[4] for r in rows)
    print("  全票标出且有测量：%d 个" % len(rows))
    for v in ("SLOWED", "WEAK", "FLAT", "MISSING"):
        k = c.get(v, 0)
        if k:
            print("    %-8s %2d  %5.1f%%" % (v, k, 100.0 * k / len(rows)))

    print("\n=== 全票标出但没慢（需处理）===")
    bad = [r for r in rows if r[4] in ("FLAT", "WEAK", "MISSING")]
    bad.sort(key=lambda r: r[3] if r[3] is not None else -1)
    for r in bad:
        print("  %-5s %-8s %-13s sps=%-6s %s" % (r[0], r[1], r[2], r[3], r[4]))
    print("  合计 %d 个单元" % len(bad))

    json.dump([dict(aid=r[0], uid=r[1], word=r[2], sps=r[3], verdict=r[4]) for r in rows],
              open(os.path.join(VDIR, "vote_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
