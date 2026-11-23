# -*- coding: utf-8 -*-
"""本轮交付的最终对照数字：改前（旧 live）vs 改后（交付版）。"""
import collections
import io
import json
import statistics

live = {r["id"]: (r.get("w2v_cov") or 0.0)
        for r in json.load(io.open("_align_live.json", encoding="utf-8"))}
new = {r["id"]: (r.get("w2v_cov") or 0.0)
       for r in json.load(io.open("_align_deliver.json", encoding="utf-8"))}
rep = json.load(io.open("_deliver_report.json", encoding="utf-8"))
ks = sorted(set(live) & set(new))


def bucket(c):
    if c >= 0.95:
        return "A 0.95-1.00"
    if c >= 0.85:
        return "B 0.85-0.95"
    if c >= 0.70:
        return "C 0.70-0.85"
    return "D <0.70"


for name, d in (("改前", live), ("改后", new)):
    c = collections.Counter(bucket(d[k]) for k in ks)
    print("%-4s " % name + "  ".join("%s:%3d" % (b, c.get(b, 0)) for b in
                                     ["A 0.95-1.00", "B 0.85-0.95", "C 0.70-0.85", "D <0.70"]))
print()
print("中位覆盖率 %.3f → %.3f" % (statistics.median(live[k] for k in ks),
                              statistics.median(new[k] for k in ks)))
up = [k for k in ks if new[k] - live[k] > 0.05]
dn = [k for k in ks if live[k] - new[k] > 0.05]
print("提升 %d 条 / 变差 %d 条 / 持平 %d 条" % (len(up), len(dn), len(ks) - len(up) - len(dn)))
print("替换为新候选 %d 条" % sum(1 for v in rep.values() if v.get("src") == "post"))
