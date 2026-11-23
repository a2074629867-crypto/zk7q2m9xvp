# -*- coding: utf-8 -*-
"""试算 v3：慢段允许 1 句；段内短快插段(<=2 句)桥接；不再强制补到 3 句。"""
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
order = [i for b in B for i in b['ids']]
pos = {s: k for k, s in enumerate(order)}
cur = json.load(open(r'G:/_setup/rate_llm_narr.json', encoding='utf-8'))['sentences']
# 现表的 28 段就是"查尔斯的戏"白名单
white = set()
for sid, v in cur.items():
    if v.get('run'):
        white.add(sid)
# 白名单按段首补回被裁掉的头尾（白名单本来自上版 run，含 padding）
ann = {json.loads(l)['sid'] for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8') if l.strip()}

# 白名单区间（连续 id 段）
wl = sorted(white, key=lambda s: pos[s])
regions, a, b = [], wl[0], wl[0]
for s in wl[1:]:
    if pos[s] == pos[b] + 1 or (pos[s] - pos[b] <= 2 and pos[b] + 1 == pos[s] - 0):
        b = s
    else:
        regions.append((pos[a], pos[b]))
        a = b = s
regions.append((pos[a], pos[b]))

for BRIDGE in (1, 2, 3):
    f = [0] * len(order)
    for a, b in regions:
        seg = [1 if (order[k] in ann) else 0 for k in range(a, b + 1)]
        # 桥接：两段慢之间夹 <=BRIDGE 句
        for k in range(len(seg)):
            if seg[k]:
                continue
            l = k - 1
            while l >= 0 and not seg[l] and k - l <= BRIDGE:
                l -= 1
            r = k + 1
            while r < len(seg) and not seg[r] and r - k <= BRIDGE:
                r += 1
            if l >= 0 and r < len(seg) and seg[l] and seg[r] and (r - l - 1) <= BRIDGE:
                seg[k] = 1
        for k in range(a, b + 1):
            f[k] = seg[k - a]
    # runs
    runs, c = [], None
    for k, v in enumerate(f):
        if v:
            if c and k - c[1] <= 1:
                c[1] = k
            else:
                if c:
                    runs.append(c)
                c = [k, k]
    if c:
        runs.append(c)
    from collections import Counter
    print('BRIDGE<=%d: 慢句 %d  段 %d  段长分布 %s'
          % (BRIDGE, sum(f), len(runs), dict(sorted(Counter(b - a + 1 for a, b in runs).items()))))
