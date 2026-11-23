# -*- coding: utf-8 -*-
"""用 voiced wpm（只算发声帧，剔除内部停顿）重算接缝连续性。

RDR 原口径「去首尾、保留中间停顿」是为「长句切分后接缝」设计的，
默认切分段内不含标点停顿。我们的单元 77% 含内部停顿，且停顿是我们按
三档（inner/bound/clause）自己插的 ⇒ 停顿多少会污染语速测量。
"""
import sys, json
sys.path.insert(0, "D:/py_libs")
import numpy as np

g = json.load(open("_rdr_gate_ch1.json", encoding="utf-8"))
rows = {r["uid"]: r for r in g["rows"]}
by = {}
for r in g["rows"]:
    if r["pid"] is not None:
        by.setdefault(r["pid"], []).append(r)
for k in by:
    by[k].sort(key=lambda r: r["uid"])

def seams(key, thr=1.5):
    out = []
    for pid, grp in by.items():
        for a, b in zip(grp, grp[1:]):
            ra, rb = a[key], b[key]
            if not ra or not rb:
                continue
            out.append((pid, a["uid"], b["uid"], max(ra, rb)/min(ra, rb), ra, rb))
    return out

def rdr(ss):
    tot = len({x[0] for x in ss})
    bad = {x[0] for x in ss if x[3] > 1.5}
    return len(bad)/max(1, tot), bad, tot

print("两种口径对比（阈值 1.5×，马修同口径 13%）\n")
print("%-30s %6s %8s %8s %8s %8s" % ("口径", "接缝", "超1.5", "占比", "p90", "RDR"))
for key, tag in (("rate_B", "B 去首尾·含内部停顿（RDR原文）"),
                 ("rate_C", "C voiced 总和（只算发声）")):
    ss = seams(key)
    r = np.array([x[3] for x in ss])
    m, bad, tot = rdr(ss)
    print("%-30s %6d %8d %7.0f%% %8.2f %8.3f"
          % (tag, len(r), int((r > 1.5).sum()), 100*(r > 1.5).mean(),
             np.percentile(r, 90), m))
    if key == "rate_C":
        print("   超标接缝：")
        for pid, a, b, ra, x, y in sorted(ss, key=lambda s: -s[3]):
            if ra > 1.5:
                print("     段%-3d %s(%.0f)→%s(%.0f)  %.2f×" % (pid, a, x, b, y, ra))

# 逐 culprit 对比：B 判离群 vs C 是否也离群
print("\n25 条 culprit 在两口径下的位置：")
print("%-7s %5s %6s %6s %-6s %6s %6s" % ("uid","词","B wpm","C wpm","B/C","B离群","C离群"))
diff = []
for uid in g["culprits"]:
    r = rows[uid]
    b, c = r["rate_B"], r["rate_C"]
    if not b or not c:
        continue
    grp = by[r["pid"]]
    ids = [x["uid"] for x in grp]
    i = ids.index(uid)
    nb = ([grp[i-1]["rate_C"]] if i > 0 else []) + ([grp[i+1]["rate_C"]] if i+1 < len(grp) else [])
    tgt = np.median(nb) if nb else c
    cb = max(b, np.median([grp[i-1]["rate_B"]] if i > 0 else [b]) if i == 0 else
             np.median([grp[i+1]["rate_B"]] if i+1 < len(grp) else [b])) / min(b, b)
    off_c = abs(np.log(c/tgt))
    flag_c = "离群" if off_c > np.log(1.5)/2 else "-"
    if flag_c == "-":
        diff.append(uid)
    print("%-7s %5d %6.0f %6.0f %6.2f %6s %6s"
          % (uid, r["w"], b, c, b/c, "离群", flag_c))
print("\nB 判离群但 C 正常（测量假象）：%d 条 → %s" % (len(diff), diff))
