# -*- coding: utf-8 -*-
"""rate_ann.jsonl（句子级）→ rate_llm.json（block 级）的聚合器。

⛔ 2026-11-20 作废（单位错）：用户原话「我说的慢就是句子中的速度，之前定的测速标注也是这样」。
   rate 的生产单位是**句子**（一个 wav = 一句，逐句 rubberband），不是 block。
   把句子级标注按词加权平均到 block 会**把判据摊平** —— 实测 81 块加权均值全落在 0.756~0.789，
   只能靠"挑最慢的 16 块"，结果散成 12 段、9 段是单块（用户当场指出的"不连续"）。
   正确产物见 `build_rate_sentences.py` → `rate_llm_narr.json`（句级）。
   本脚本留作**统计对照**（哪些块整体偏慢），不要拿它的输出当 rate 判据。

rate_ann.jsonl（句子级）→ rate_llm.json（block 级）的转换器。

★ 为什么不能直接把句子级表当生产用（`_annot_legacy_inventory.md` §七.5 记过这次错）：
  生产口的 `_narr_rate_plan_castle.json` **单位是 chunk block**（target 120 / hard_max 165 词），
  硬约束四条：相邻段差 ≤0.06 / 减速词数 ≤20% / rate≤0.72 最多 1 段 / 只降不升。
  句子级 rate 直接塞进去，等于把 716 句当成 716 个 block，约束全部失效。

⛔ base 0.80 已作废（2026-11-16 用户：「base 不要 0.8 吧？我们之前不是确认过不用降速吗」）。
   十月原话三条钉死了这条：10-22「速度你变了吗？感觉不如原速度」（190 档 tempo 中位 0.798 被否）、
   10-23「不降速了」、10-30「不降速好了，太奇怪了」⇒ **默认 base = 1.00 原速**。
   ⚠️ 但 ADJ_MAX=0.06 是按 base 0.80 设计的：base 拉到 1.00 后，1.00 与 0.77 相邻会被强行抹平。
   重跑前必须先定「入选块允许的最慢值」，否则本脚本会静默把落差压成 0.94/0.88 的假阶梯。

所以这里做三件事：
  1. 按 `_narr_blocks.json` 把句子标注**聚合到已有 block**（不重新切块，块 id 必须与现役一致）
  2. 按词数加权求 block rate，再按预算挑最慢的若干块，其余回 base 1.00（原速）
  3. 逐条校验四条硬约束，违反的不静默放过，直接打印

⭐ 本脚本会打印一个「判别力」指标 —— 如果所有 block 的加权均值挤在 0.75~0.79，
   说明句子级标注**没有区分度**，block 级根本不需要减速对照；这时候结论该是
   「旁白整体原速 1.00，rate 层不生效」，而不是硬凑出一张有高有低的表，
   更不是把整本拉到 0.78（那是 10-22 被用户当场否掉的 190 档）。

用法：
  G:/Python310/python.exe rate_ann2llm.py --dry
  G:/Python310/python.exe rate_ann2llm.py --out G:/_setup/rate_llm_narr.json
"""
import argparse
import json
import os
import sys

BASE = r'G:/_setup'
BASE_RATE = 1.00   # 2026-11-16：0.80 → 1.00（默认原速；0.80 是整本慢 20%，十月已被否）
RANGE = (0.72, 0.84)
ADJ_MAX = 0.06
BUDGET = 0.20


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ann', default=os.path.join(BASE, r'_ann/merged_v3/rate_ann.jsonl'))
    ap.add_argument('--blocks', default=os.path.join(BASE, '_narr_blocks.json'))
    ap.add_argument('--plan', default=os.path.join(BASE, '_narr_blocks.json'))
    ap.add_argument('--texts', default=os.path.join(BASE, '_narr_plan_for_pause.jsonl'))
    ap.add_argument('--budget', type=float, default=BUDGET, help='允许减速的词数占比上限')
    ap.add_argument('--min-evidence', type=float, default=0.30,
                    help='block 内被标注的词占比低于此值，不参评（样本不足）')
    ap.add_argument('--out', default=os.path.join(BASE, 'rate_llm_narr.json'))
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    texts = {r['id']: r for r in load_jsonl(a.texts)}
    rate = {r['sid']: float(r['rate']) for r in load_jsonl(a.ann)}
    blocks = json.load(open(a.blocks, encoding='utf-8'))
    if isinstance(blocks, dict):
        blocks = blocks.get('blocks') or []

    def wc(sid):
        t = texts.get(sid, {}).get('text', '')
        return len(t.split())

    rows, total_w, ann_w = [], 0, 0
    for b in blocks:
        ids = b.get('ids') or []
        bw = b.get('words') or sum(wc(s) for s in ids)
        total_w += bw
        hit = [s for s in ids if s in rate]
        aw = sum(wc(s) for s in hit)
        ann_w += aw
        wm = (sum(rate[s] * wc(s) for s in hit) / aw) if aw else None
        rows.append(dict(bid=b['bid'], chapter=b.get('chapter', ''), words=bw,
                         n_hit=len(hit), n_ids=len(ids), ann_ratio=aw / max(bw, 1),
                         wm=wm))
    print('block %d 个 / %d 词；被标注覆盖 %d 词 = %.1f%%'
          % (len(rows), total_w, ann_w, 100.0 * ann_w / max(total_w, 1)))

    cands = [r for r in rows if r['wm'] is not None and r['ann_ratio'] >= a.min_evidence]
    vals = sorted(r['wm'] for r in cands)
    if vals:
        print('可参评 block %d 个；加权均值 min %.3f / 中位 %.3f / max %.3f（极差 %.3f）'
              % (len(cands), vals[0], vals[len(vals) // 2], vals[-1], vals[-1] - vals[0]))
        print('  ⭐ 判别力：极差 <0.05 说明句子级标注没有块间区分度，'
              'block 表只能给出「整体略慢」一个结论。' if vals[-1] - vals[0] < 0.05 else
              '  判别力足够（极差 ≥0.05），可按慢块挑。')

    # 按预算挑最慢的块（只降不升：rate < base 才算减速）
    budget_w = int(a.budget * total_w)
    chosen, used = set(), 0
    for r in sorted(cands, key=lambda x: x['wm']):
        if r['wm'] >= BASE_RATE - 1e-9:
            break
        if used + r['words'] > budget_w:
            continue
        chosen.add(r['bid'])
        used += r['words']
    print('预算 ≤%d 词（%.0f%%）→ 入选 %d 块 / %d 词 = %.1f%%'
          % (budget_w, 100 * a.budget, len(chosen), used, 100.0 * used / max(total_w, 1)))

    bychap = {}
    prev = None
    viol_adj, viol_lo = [], []
    for r in rows:
        if r['bid'] in chosen:
            rt = round(min(RANGE[1], max(RANGE[0], r['wm'])), 2)
        else:
            rt = BASE_RATE
        if prev is not None and abs(rt - prev) > ADJ_MAX + 1e-9:
            fixed = round(prev + (ADJ_MAX if rt > prev else -ADJ_MAX), 2)
            viol_adj.append('%s %.2f→%.2f（前一 block %.2f）' % (r['bid'], rt, fixed, prev))
            rt = fixed
        if rt < RANGE[0]:
            viol_lo.append(r['bid'])
            rt = RANGE[0]
        prev = rt
        rec = {'bid': r['bid'], 'rate': rt}
        if r['bid'] in chosen:
            rec['why'] = ('句级标注加权 %.3f（%d/%d 句，覆盖 %.0f%% 词）'
                          % (r['wm'], r['n_hit'], r['n_ids'], 100 * r['ann_ratio']))
        bychap.setdefault(r['chapter'] or 'Chapter', {'base_rate': BASE_RATE,
                                                      'blocks': []})['blocks'].append(rec)

    low = sum(1 for c in bychap.values() for b in c['blocks'] if b['rate'] <= RANGE[0] + 1e-9)
    print('约束自检：相邻段差越界 %d 次%s / rate≤0.72 的段 %d 个（上限 1）'
          % (len(viol_adj), ('（已夹平）' if viol_adj else ''), low))
    for x in viol_adj[:5]:
        print('    ' + x)

    out = {
        '_meta': {
            'book': 'I am the King of the Castle (Susan Hill)',
            'track': 'narr',
            'unit': 'chunk block from _narr_blocks.json (target 120 / hard_max 165 words)',
            'base_rate': BASE_RATE, 'range': list(RANGE), 'only_slow_down': True,
            'rules': '相邻段差<=%.2f，减速词数<=%.0f%%，rate<=0.72 最多 1 段'
                     % (ADJ_MAX, 100 * a.budget),
            'derived_from': os.path.basename(a.ann),
            'note': '由句子级标注聚合到 block（词数加权）；未入选的 block 一律 base_rate。'
                    '句子级标注不是生产单位，本表才是。',
        },
    }
    out.update(bychap)

    if a.dry:
        print('\n（--dry，未写文件）')
        return 0
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n写出 %s（%.1f KB）' % (a.out, os.path.getsize(a.out) / 1024.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
