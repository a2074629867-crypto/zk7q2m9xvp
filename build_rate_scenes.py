# -*- coding: utf-8 -*-
"""⛔ 2026-11-20 作废：rate 的单位是**句子**，不是 block（见 build_rate_sentences.py）。
本脚本只保留做「哪些块整体偏慢」的统计对照，**产物不进生产链**。

按「情节段」重划旁白 rate：先由三路句级标注得块级慢句占比，再连成 >=2 块的场景段。

改动口径（2026-11-20 用户）：
  - base = 1.00（十月起铁律：不整本降速）
  - 慢读只给 0.84（他选的档：−16%，最轻）
  - 慢读必须**连片**：单块(≈9 句/127 词)不算一段，场景段至少 2 块
"""
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = 1.00
SLOW = 0.84
TH = 0.40          # 块级慢句占比阈值
MIN_BLOCKS = 2     # 场景段最少块数

B = json.load(open(r'G:/_setup/_narr_blocks.json', encoding='utf-8'))
ann = {json.loads(l)['sid'] for l in open(r'G:/_setup/_ann/merged_v3/rate_ann.jsonl', encoding='utf-8') if l.strip()}
sh = [sum(1 for i in b['ids'] if i in ann) / max(1, len(b['ids'])) for b in B]
n = len(B)
flags = [1 if s >= TH else 0 for s in sh]

# 1) 填 1 块空洞（场景中间夹一个未达阈值的块）
for k in range(1, n - 1):
    if not flags[k] and flags[k - 1] and flags[k + 1]:
        flags[k] = 1


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


# 2) 单块段补到 2 块：挑邻居里慢句占比更高的那块
rr = runs_of(flags)
for a, b in rr:
    if a == b:
        left = sh[a - 1] if a - 1 >= 0 else -1
        right = sh[a + 1] if a + 1 < n else -1
        if right >= left and a + 1 < n:
            flags[a + 1] = 1
        elif a - 1 >= 0:
            flags[a - 1] = 1
rr = runs_of(flags)

# 3) 再填一次空洞（补块后可能产生 1 块缝）
for k in range(1, n - 1):
    if not flags[k] and flags[k - 1] and flags[k + 1]:
        flags[k] = 1
rr = runs_of(flags)

tot_w = sum(b['words'] for b in B)
slow_w = sum(b['words'] for b, f in zip(B, flags) if f)
print('慢块 %d/%d  词 %.1f%%  场景段 %d 段  各段块数 %s  最短 %d 块'
      % (sum(flags), n, 100.0 * slow_w / tot_w, len(rr), [b - a + 1 for a, b in rr], min(b - a + 1 for a, b in rr)))

# 4) 落表
out = {'_meta': {
    'book': 'I am the King of the Castle (Susan Hill)',
    'track': 'narr',
    'unit': 'chunk block from _narr_blocks.json (target 120 / hard_max 165 words)',
    'base_rate': BASE,
    'slow_rate': SLOW,
    'range': [SLOW, BASE],
    'only_slow_down': True,
    'derived_from': '_ann/merged_v3/rate_ann.jsonl（279 句三路标注，两票 98.9%）',
    'rule': '块级慢句占比 >=%.2f 判慢；1 块空洞填平；场景段至少 %d 块；慢段一律 %.2f，其余 %.2f'
            % (TH, MIN_BLOCKS, SLOW, BASE),
    'note': '2026-11-20 用户：「该慢的情节应该很多，句子应该连续起来」+ 选档 2（0.84）。'
            'base 0.80 是十一月自造数，已作废（十月原话见 DECISIONS 末二条）。',
    'coverage_words': round(100.0 * slow_w / tot_w, 1),
    'n_scenes': len(rr),
}}

chapters = {}
for k, (b, f) in enumerate(zip(B, flags)):
    chapters.setdefault(b['chapter'], []).append(
        {'bid': b['bid'], 'rate': SLOW if f else BASE, 'words': b['words'], 'n': b['n'],
         'slow_share': round(sh[k], 3)})

idx = {b['bid']: k for k, b in enumerate(B)}

# 场景编号
scene_id = {}
for si, (a, b) in enumerate(rr, 1):
    for k in range(a, b + 1):
        scene_id[B[k]['bid']] = 'S%02d' % si
for ch, lst in chapters.items():
    for rec in lst:
        rec['scene'] = scene_id.get(rec['bid'])

d = {'_meta': out['_meta']}
for ch in ['Chapter One', 'Chapter Two', 'Chapter Three']:
    d[ch] = {'base_rate': BASE, 'blocks': chapters[ch]}
json.dump(d, open(r'G:/_setup/rate_llm_narr_scene_v1.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# 句级映射（生成端直接读这个）
sid_rate = {}
bid_map = {b['bid']: b for b in B}
for ch, lst in chapters.items():
    for rec in lst:
        for i in bid_map[rec['bid']]['ids']:
            sid_rate[i] = {'rate': rec['rate'], 'scene': rec['scene']}
json.dump({'_meta': {'base_rate': BASE, 'slow_rate': SLOW, 'n_sent': len(sid_rate)},
           'sentences': sid_rate},
          open(r'G:/_setup/rate_narr_scene_v1.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

# 场景清单（人看）
print()
for si, (a, b) in enumerate(rr, 1):
    ws = sum(B[k]['words'] for k in range(a, b + 1))
    head = B[a]['text'][:60].replace('\n', ' ')
    print('S%02d %s-%s  %d 块  %d 词  %s…' % (si, B[a]['bid'], B[b]['bid'], b - a + 1, ws, head))
