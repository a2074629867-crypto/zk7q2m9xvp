# -*- coding: utf-8 -*-
"""按 SceneTTS-Bench 的 RDR（Rate Discontinuity Ratio）测我们自己的接缝。

RDR 定义（arXiv 2609.26255）：
  1. 同一原始长句的全部切分段链成一组
  2. 每段：词数 / VAD 去首尾静音的有效时长 = 分段语速
  3. 组内做全部片段对的成对比较，速率比 max > 1.5 即标记跳变
  4. 组级聚合：组内存在任意 1 对跳变 → 该组不连续
  5. RDR = 不连续组数 / 有效组数

我们的分组天然存在：_ch1_unit_para.json 里同一 pid = 同一原书段落切出来的单元。
有效时长 = trim 后时长 − (head_pad 0.05 + tail_pad 0.20)。
"""
import sys, json, os, re, itertools
sys.path.insert(0, "D:/py_libs")
import numpy as np, soundfile as sf

PAD = 0.25
THR = 1.5

S = json.load(open("_mt_loop_state.json", encoding="utf-8"))["units"]
PARA = {r["uid"]: r.get("pid") for r in json.load(open("_ch1_unit_para.json", encoding="utf-8"))}

def nwords(t):
    return len(re.findall(r"[A-Za-z][A-Za-z'\-]*", t))

rows = []
for uid, pid in PARA.items():
    p = os.path.join("_mt_final_raw_trim", uid + ".wav")
    if not os.path.exists(p):
        continue
    dur = sf.info(p).frames / sf.info(p).samplerate
    eff = dur - PAD
    w = nwords(S[uid]["text"])
    if w < 3 or eff < 0.4:
        continue
    rows.append(dict(uid=uid, pid=pid, w=w, eff=round(eff, 3),
                     rate=round(w / eff * 60, 1)))

groups = {}
for r in rows:
    if r["pid"] is None:
        continue
    groups.setdefault(r["pid"], []).append(r)

bad, ok, detail = 0, 0, []
for pid, g in sorted(groups.items()):
    if len(g) < 2:
        continue
    mx, pair = 0.0, None
    for a, b in itertools.combinations(g, 2):
        r = max(a["rate"], b["rate"]) / min(a["rate"], b["rate"])
        if r > mx:
            mx, pair = r, (a["uid"], b["uid"])
    if mx > THR:
        bad += 1
        detail.append((pid, round(mx, 2), pair,
                       [x["rate"] for x in g], [x["uid"] for x in g]))
    else:
        ok += 1

tot = bad + ok
print("=== ch1 接缝语速不连续（RDR 口径）===")
print("可分组单元 %d / 有效组 %d（单条组不计）" % (len(rows), tot))
print("不连续组 %d / %d  →  RDR = %.3f" % (bad, tot, bad / tot if tot else 0))
print()
print("跳变最严重的 12 组（阈值 1.5）:")
for pid, mx, pair, rates, uids in sorted(detail, key=lambda t: -t[1])[:12]:
    print("  段%-3d 比 %.2f  %s→%s   语速 %s" % (pid, mx, pair[0], pair[1], rates))

allr = [r["rate"] for r in rows]
print()
print("单元语速分布 p10/p50/p90 = %.0f / %.0f / %.0f  wpm  跨度 %.0f" %
      (np.percentile(allr, 10), np.median(allr), np.percentile(allr, 90),
       max(allr) - min(allr)))
json.dump(dict(rdr=bad / tot if tot else None, bad=bad, tot=tot,
               rows=rows, detail=[d[0:4] for d in detail]),
          open("_rdr_ch1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
