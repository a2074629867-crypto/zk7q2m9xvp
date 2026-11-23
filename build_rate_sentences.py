# -*- coding: utf-8 -*-
"""旁白 rate 表 —— 句子级 · v3「呼吸式慢读」（2026-11-20 02:1x 用户口径）。

用户原话：
  「慢节奏的句子情节不需要一整段都是慢的，只要两三个句子连起来即可，单个句子也可以。
    但如果中间穿插了快节奏内容，之后又回到慢节奏，那么慢节奏部分最好能连起来。」

⇒ 慢的单位不是"整段"，而是**一次呼吸：1~3 句**；如果两口气之间只隔 1 句快节奏，就并进去，
   免得读起来一顿一顿。

流程：
  1) 白名单 = 查尔斯的戏（KEEP_FROM，28 段）。Joseph 自述家史 / 老宅衰败 / 村景 / 母亲改嫁不进慢档。
  2) 白名单内取三路标注命中的句子，按连续簇分组（中间隔 1 句算同簇）。
  3) 每个簇只留**标注值最慢的连续 ≤3 句**作为核心 —— 一整段都慢是错的。
  4) 两个核心之间只隔 1 句 → 桥接，让慢的部分连起来。
  5) rate：慢 0.84，其余 1.00（base 1.00 是十月铁律：不整本降速）。

产出：rate_llm_narr.json（句级）、rate_narr_sent_v1.json（扁平 sid->rate）
"""
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = 1.00
SLOW = 0.84
CORE = 3       # 每次"呼吸"最多几句
BRIDGE = 1     # 两口之间隔几句就桥接
GAP = 1        # 白名单段内的填洞（只为确定"哪些是查尔斯的戏"）

KEEP_FROM = {
    'c1_0001', 'c2_0244', 'c2_0285', 'c2_0316', 'c2_0345', 'c2_0377',
    'c2_0394', 'c2_0406', 'c2_0482', 'c2_0496',
    'c3_0536', 'c3_0563', 'c3_0568', 'c3_0586', 'c3_0592', 'c3_0605',
    'c3_0621', 'c3_0657', 'c3_0678', 'c3_0700', 'c3_0755', 'c3_0765',
    'c3_0783', 'c3_0817', 'c3_0859', 'c3_0886', 'c3_0918', 'c3_0948',
}

B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
order = [i for b in B for i in b['ids']]
pos = {s: k for k, s in enumerate(order)}
words = {}
for b in B:
    per = b['words'] / max(1, len(b['ids']))
    for i in b['ids']:
        words[i] = per
ann = {}
for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8'):
    if l.strip():
        o = json.loads(l)
        ann[o['sid']] = float(o['rate'])
TXT = {r['id']: r['text'] for r in
       (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
       if r.get('speaker') == 'narrator'}
n = len(order)
hit = [1 if i in ann else 0 for i in order]


def runs_of(f):
    out, cur = [], None
    for k, v in enumerate(f):
        if v:
            if cur and k - cur[1] <= 1:
                cur[1] = k
            else:
                if cur:
                    out.append(cur)
                cur = [k, k]
    if cur:
        out.append(cur)
    return out


# 1) 白名单区间：标注 → 填洞 → 补到 3 句 → 只保留 KEEP_FROM 点名的段
f = hit[:]
for k in range(1, n - 1):
    if f[k]:
        continue
    l = k - 1
    while l >= 0 and not f[l] and k - l <= GAP:
        l -= 1
    r = k + 1
    while r < n and not f[r] and r - k <= GAP:
        r += 1
    if l >= 0 and r < n and f[l] and f[r] and (r - l - 1) <= GAP:
        f[k] = 1
for _ in range(4):
    rr = runs_of(f)
    bad = [(a, b) for a, b in rr if b - a + 1 < 3]
    if not bad:
        break
    for a, b in bad:
        for step in range(1, 3 - (b - a + 1) + 1):
            if b + step < n and not f[b + step]:
                f[b + step] = 1
            elif a - step >= 0 and not f[a - step]:
                f[a - step] = 1

regions = [(a, b) for a, b in runs_of(f) if order[a] in KEEP_FROM]

# 2) 区域内取标注句 → 连续簇 → 每簇最慢的 <=CORE 句
g = [0] * n
for a, b in regions:
    seeds = [k for k in range(a, b + 1) if order[k] in ann]
    if not seeds:
        continue
    clusters, s, e = [], seeds[0], seeds[0]
    for k in seeds[1:]:
        if k - e <= 2:
            e = k
        else:
            clusters.append((s, e))
            s = e = k
    clusters.append((s, e))
    for s, e in clusters:
        idx = [k for k in range(s, e + 1) if order[k] in ann]
        vals = [ann[order[k]] for k in idx]
        L = min(CORE, len(idx))
        best_i, best_v = 0, None
        for i in range(len(idx) - L + 1):
            v = sum(vals[i:i + L]) / L
            if best_v is None or v < best_v - 1e-9:
                best_i, best_v = i, v
        for k in idx[best_i:best_i + L]:
            g[k] = 1

# 3) 桥接：两口之间只隔 1 句 → 并进来（不跨出白名单段）
for a, b in regions:
    for k in range(a + 1, b):
        if g[k]:
            continue
        if g[k - 1] and g[k + 1]:
            g[k] = 1

# 4) 短句并成「一口气」句组 —— 用户 2026-11-20 02:22：「短句要并成一口气再算一句」
#    ≤SHORT 词的碎句并进下一句；组内所有 wav 同一个 rate（一句话不能前半慢后半快）
SHORT = 5
groups, cur = [], []
for i in order:
    cur.append(i)
    if len(TXT[i].split()) > SHORT:
        groups.append(cur)
        cur = []
if cur:
    if groups:
        groups[-1].extend(cur)
    else:
        groups.append(cur)
grp_id = {}
for gi, gm in enumerate(groups, 1):
    for i in gm:
        grp_id[i] = 'G%03d' % gi
# 组内任一成员慢 ⇒ 整组慢
for gm in groups:
    if any(g[k] for k in (pos[i] for i in gm)):
        for i in gm:
            g[pos[i]] = 1

# 5) 每处最多 MAXG 个句组（用户：「两三个句子连起来即可」）——多出来的砍最弱的那组
MAXG = 3
while True:
    runs = runs_of(g)
    over = [r for r in runs if len({grp_id[order[k]] for k in range(r[0], r[1] + 1)}) > MAXG]
    if not over:
        break
    a, b = over[0]
    seen = {}
    for k in range(a, b + 1):
        seen.setdefault(grp_id[order[k]], []).append(k)
    # 最弱 = 组内标注均值最高（越接近 0.79 越不慢）；没标注的算最弱
    def weakness(ks):
        vals = [ann[order[k]] for k in ks if order[k] in ann]
        return sum(vals) / len(vals) if vals else 9.9
    worst = max(seen.values(), key=weakness)
    for k in worst:
        g[k] = 0

rr2 = runs_of(g)
tot_w = sum(words.values())
slow_w = sum(words[order[k]] for k in range(n) if g[k])
print('慢句 %d/%d (%.1f%%)  词 %.1f%%  段 %d  段长分布 %s'
      % (sum(g), n, 100.0 * sum(g) / n, 100 * slow_w / tot_w, len(rr2),
         dict(sorted(Counter(b - a + 1 for a, b in rr2).items()))))
for ch in ('c1', 'c2', 'c3'):
    ks = [k for k, i in enumerate(order) if i.startswith(ch)]
    print('  %s 慢 %d/%d = %.1f%%' % (ch, sum(g[k] for k in ks), len(ks), 100.0 * sum(g[k] for k in ks) / len(ks)))

run_id = {}
for si, (a, b) in enumerate(rr2, 1):
    for k in range(a, b + 1):
        run_id[order[k]] = 'R%02d' % si

sents = {}
for k, i in enumerate(order):
    rec = {'rate': SLOW if g[k] else BASE, 'group': grp_id[i]}
    if g[k]:
        rec['run'] = run_id[i]
        rec['src'] = 'llm_vote' if hit[k] else 'bridge'
    sents[i] = rec

out = {'_meta': {
    'book': 'I am the King of the Castle (Susan Hill)',
    'track': 'narr',
    'unit': 'sentence-group（一口气：<=5 词的碎句并进下一句，组内同一 rate）',
    'base_rate': BASE,
    'slow_rate': SLOW,
    'range': [SLOW, BASE],
    'only_slow_down': True,
    'derived_from': '_ann/merged_v3/rate_ann.jsonl（279 句三路标注，两票 98.9%）',
    'rule': '查尔斯白名单内，每个连续标注簇只取最慢的 <=%d 句；两口之间隔 %d 句则桥接；慢句一律 %.2f'
            % (CORE, BRIDGE, SLOW),
    'note': '2026-11-20 02:1x 用户：「不需要一整段都是慢的，只要两三个句子连起来即可，单个句子也可以；'
            '中间穿插快节奏后又回到慢的，慢的部分最好连起来」。'
            '所以慢的粒度从"整段"改成"一次呼吸 1~3 句"，只桥接 1 句的缝。',
    'n_sent': n,
    'n_slow': sum(g),
    'coverage_words': round(100 * slow_w / tot_w, 1),
    'n_runs': len(rr2),
}}
out['sentences'] = sents
json.dump(out, open(r'G:/_setup/rate_llm_narr.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
json.dump({'_meta': {'base_rate': BASE, 'slow_rate': SLOW, 'unit': 'sentence'},
           'rates': {i: sents[i]['rate'] for i in order}},
          open(r'G:/_setup/rate_narr_sent_v1.json', 'w', encoding='utf-8'), ensure_ascii=False)

plan = {r['id']: r for r in (json.loads(l) for l in open(r'G:/_setup/_narr_plan_for_pause.jsonl', encoding='utf-8') if l.strip())
        if r.get('speaker') == 'narrator'}
print()
for si, (a, b) in enumerate(rr2, 1):
    print('R%02d %s-%s %d 句 | %s' % (si, order[a], order[b], b - a + 1, plan[order[a]]['text'][:52]))
