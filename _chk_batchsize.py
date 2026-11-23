# -*- coding: utf-8 -*-
"""对齐「哪批失败」与「批次体量」，判断 502 是随机还是 payload 相关。"""
import json, os, glob

root = "G:/_setup/_ann/tasks_v3t"
rows = []
for fp in sorted(glob.glob(os.path.join(root, "batch_*.json"))):
    o = json.load(open(fp, encoding="utf-8"))
    items = o.get("items") or []
    nslots = sum(len(it.get("slots") or []) for it in items)
    chars = sum(len(it.get("text") or "") for it in items)
    payload = len(json.dumps({"items": items}, ensure_ascii=False))
    rows.append((os.path.basename(fp), len(items), nslots, chars, payload))

print("%-16s %5s %6s %7s %8s" % ("batch", "items", "slots", "chars", "payloadB"))
for b, ni, ns, ch, pl in rows:
    print("%-16s %5d %6d %7d %8d" % (b, ni, ns, ch, pl))

pl = [r[4] for r in rows]
print("\npayload 中位 %d  最大 %d (%s)  最小 %d (%s)"
      % (sorted(pl)[len(pl)//2], max(pl), max(rows, key=lambda r: r[4])[0],
         min(pl), min(rows, key=lambda r: r[4])[0]))
focus = ["batch_0002.json", "batch_0004.json", "batch_0005.json", "batch_0006.json"]
print("\n失败/成功关注批的 payload 排名：")
order = sorted(rows, key=lambda r: -r[4])
for i, (b, *_r) in enumerate(order, 1):
    if b in focus:
        print("  %-16s 第 %d 大 /48  payload=%d" % (b, i, _r[3]))
