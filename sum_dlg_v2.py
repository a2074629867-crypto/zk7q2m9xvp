# -*- coding: utf-8 -*-
"""对白链路 v2（centroid 标定后）结果汇总，并与 v1 对比。"""
import collections
import json

V1 = "G:/_setup/_gate_dlg.json"
V2 = "G:/_setup/_gate_dlg_v2.json"


def load(p):
    d = json.load(open(p, encoding="utf-8"))
    return d if isinstance(d, list) else (d.get("rows") or d.get("results") or [])


v1, v2 = load(V1), load(V2)
print("v1 %d 条 / v2 %d 条" % (len(v1), len(v2)))


def summ(rows, tag):
    c = collections.Counter(str(r.get("verdict") or r.get("decision")) for r in rows)
    print("\n== %s ==" % tag)
    n = len(rows)
    for k in ("PASS", "MANUAL", "REGEN"):
        print("  %-7s %3d  (%.1f%%)" % (k, c.get(k, 0), 100.0 * c.get(k, 0) / n))
    rc = collections.Counter()
    for r in rows:
        for x in (r.get("reasons") or []):
            code = x.get("code") if isinstance(x, dict) else str(x)
            rc[code] += 1
    print("  原因:", dict(rc.most_common(14)))
    return c, rc


c1, r1 = summ(v1, "v1 旧判据 (1:53)")
c2, r2 = summ(v2, "v2 新判据 (2:54 标定后)")

print("\n== 逐条对比 ==")
m1 = {r["id"]: r for r in v1}
m2 = {r["id"]: r for r in v2}
both = [i for i in m2 if i in m1]
trans = collections.Counter((str(m1[i].get("verdict")), str(m2[i].get("verdict"))) for i in both)
print("  v1 -> v2 转移:")
for (a, b), n in trans.most_common():
    if a != b:
        print("    %-7s -> %-7s %3d" % (a, b, n))

# 按角色看 v2
print("\n== v2 按角色 ==")
for who in ("Joseph", "Thomas", "Charles", "Helena"):
    sub = [r for r in v2 if r.get("who") == who]
    if not sub:
        continue
    cc = collections.Counter(str(r.get("verdict")) for r in sub)
    print("  %-8s n=%3d  PASS %3d / MANUAL %3d / REGEN %3d"
          % (who, len(sub), cc.get("PASS", 0), cc.get("MANUAL", 0), cc.get("REGEN", 0)))

# 按情绪看 v2（这个最重要：情绪档是否影响判定）
print("\n== v2 按情绪档 ==")
for emo in ("平静", "紧张", "激动反抗", "委屈", "兴奋", "警惕"):
    sub = [r for r in v2 if r.get("emo") == emo]
    if not sub:
        continue
    cc = collections.Counter(str(r.get("verdict")) for r in sub)
    print("  %-6s n=%3d  PASS %3d / MANUAL %3d / REGEN %3d"
          % (emo, len(sub), cc.get("PASS", 0), cc.get("MANUAL", 0), cc.get("REGEN", 0)))

# 时长分档
print("\n== v2 按时长 ==")
for lo, hi in ((0, 0.9), (0.9, 1.5), (1.5, 3.0), (3.0, 999)):
    sub = [r for r in v2 if lo <= float(r.get("dur") or 0) < hi]
    if not sub:
        continue
    cc = collections.Counter(str(r.get("verdict")) for r in sub)
    print("  %4.1f-%5.1fs n=%3d  PASS %3d / MANUAL %3d / REGEN %3d"
          % (lo, hi, len(sub), cc.get("PASS", 0), cc.get("MANUAL", 0), cc.get("REGEN", 0)))
