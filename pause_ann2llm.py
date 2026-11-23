# -*- coding: utf-8 -*-
"""标注 → pause_llm.json 的转换器。补上「标好了喂不进生产链」的最后一段。

★ 这个脚本存在的唯一理由，是两套编号完全不同：

| 来源 | 序号含义 | 起点 |
|---|---|---|
| 标注产物 `p_lead_v2_b0.jsonl` 的 `bid = "c1_0001#3"` | 该句里**第 3 个标点** | **1 起** |
| `pause_llm.json` 的 key（`{"c1_0001": {"7": {...}}}`） | **token 下标**（含非标点词） | **0 起** |

直接拿 `#3` 当 key 会整体串位 —— 而且**不会报错**，插到错的位置上去，
听起来就是「停顿落在半句话中间」。所以必须用原文重新对齐，并逐条校验标点一致。

另外两侧的档位名也不同（标注用 inner/bound/clause，生产用 kind 字符串），
但 `mt_final_pause` 只把 kind 写进报告、不参与判定，所以直接透传即可。

用法：
  # 先干跑，看对齐率
  G:/Python310/python.exe pause_ann2llm.py --ann _pause_vote/p_lead_v2_b0.jsonl \
      --texts _castle_en_ch123_plan.jsonl --dry
  # 合并多批并落盘
  G:/Python310/python.exe pause_ann2llm.py \
      --ann _pause_vote/p_lead_v2_b*.jsonl \
      --texts _castle_en_ch123_plan.jsonl --out pause_llm_castle.json
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mt_pause_rules import parse_text      # 单一实现：绝不在转换器里重写一套切词


def punct_slots(text):
    """原文里**带标点**的 token 下标（0 起）。返回 [(token_index, punct), ...]。

    与 mk_pause_ctx.py 的 `enumerate(marks, 1)` 必须一一对应：
    marks 就是按同一顺序收集的带标点 token。
    """
    toks = parse_text(text)
    return [(i, p) for i, (_, p) in enumerate(toks) if p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ann', nargs='+', required=True, help='标注 jsonl（可多个，按序合并）')
    ap.add_argument('--texts', required=True)
    ap.add_argument('--out', default='pause_llm_castle.json')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    texts, spk = {}, {}
    for ln in open(a.texts, encoding='utf-8'):
        ln = ln.strip()
        if ln:
            r = json.loads(ln)
            texts[r['id']] = r['text']
            spk[r['id']] = r.get('speaker') or ''

    files = []
    for pat in a.ann:
        files.extend(sorted(glob.glob(pat)) or [pat])

    ann = []
    for fp in files:
        n0 = len(ann)
        for ln in open(fp, encoding='utf-8'):
            ln = ln.strip()
            if ln:
                ann.append(json.loads(ln))
        print('读 %-42s %d 条' % (os.path.basename(fp), len(ann) - n0))

    out, bad_missing, bad_punct, bad_seq = {}, [], [], []
    for r in ann:
        bid = r['bid']
        sid, _, tail = bid.partition('#')
        if not tail.isdigit():
            bad_seq.append('%s 缺 #N' % bid)
            continue
        nth = int(tail)                 # 1 起
        if sid not in texts:
            bad_missing.append(bid)
            continue
        slots = punct_slots(texts[sid])
        if nth < 1 or nth > len(slots):
            bad_seq.append('%s 越界（该句只有 %d 个标点）' % (bid, len(slots)))
            continue
        tok_i, punct = slots[nth - 1]
        if r.get('punct') and r['punct'] != punct:
            # 标点对不上 = 两侧的切词/标点口径已经漂了，宁可不写
            bad_punct.append('%s 标注=%r 原文=%r（token %d）'
                             % (bid, r['punct'], punct, tok_i))
            continue
        src = str(r.get('src') or 'lead_ann')
        out.setdefault(sid, {})[str(tok_i)] = {
            'd': round(float(r['dur']), 3),
            'kind': str(r.get('mark', '')),
            'why': str(r.get('why', '')),
            # src=llm 是 REQUIREMENTS 32.0 的验收口径（比较对象是 tier 兜底）
            'src': 'llm' if src.startswith('llm') else src,
            'src_detail': src,
            'bid': bid,                 # 留痕，便于反查
        }

    ann_sids = set(r.get('sid') for r in ann if r.get('sid'))
    n_slots = sum(len(v) for v in out.values())
    print('\n标注 %d 条 → 可落盘 %d 处 / %d 条台词' % (len(ann), n_slots, len(out)))
    print('  跳过：原文缺 %d / 标点不符 %d / 序号异常 %d'
          % (len(bad_missing), len(bad_punct), len(bad_seq)))
    for tag, arr in (('原文缺', bad_missing), ('标点不符', bad_punct), ('序号异常', bad_seq)):
        for x in arr[:5]:
            print('    %s: %s' % (tag, x))
        if len(arr) > 5:
            print('    %s: …共 %d' % (tag, len(arr)))

    # 覆盖率：**本次标注涉及的那些台词**能插停顿的位置有多少被判过
    #   ★ 2026-11-15 05:1x 修：原来分母是整本书（旁白+对白同一本 plan），
    #     只标旁白时算出 47.4%，看着像漏了一半，其实是分母混了两条轨。
    total_slots = sum(len(punct_slots(texts[sid])) for sid in ann_sids if sid in texts)
    if total_slots:
        print('  本书标点总槽位 %d，覆盖 %.1f%%'
              % (total_slots, 100.0 * n_slots / total_slots))

    # 分轨尺度自检（REQUIREMENTS 32.1b）：旁白 0.51/1.135/1.695，对白 0/0.20/0.49/0.68
    # 混尺度不会报错，只会静默把旁白切短 2~3 倍，所以这里硬拦。
    try:
        from ann_spec import KIND_SEC, track_of_speaker, nearest_kind
        bad = []
        for sid, slots in out.items():
            trk = track_of_speaker(spk.get(sid, ''))
            for k, v in slots.items():
                nk = nearest_kind(trk, v['d'])
                if abs(KIND_SEC[trk][nk] - v['d']) > 0.03:
                    bad.append('%s#%s %s d=%.2f 不在 %s 尺度' % (sid, k, trk, v['d'], trk))
        if bad:
            print('\n  ⚠ 尺度越轨 %d 处（旁白/对白尺子混了？）：' % len(bad))
            for x in bad[:5]:
                print('    ' + x)
        else:
            import collections as _c
            cc = _c.Counter()
            for sid, slots in out.items():
                trk = track_of_speaker(spk.get(sid, ''))
                for v in slots.values():
                    cc[(trk, v['kind'] or nearest_kind(trk, v['d']))] += 1
            print('  尺度自检通过：' + ', '.join('%s/%s=%d' % (a1, a2, n)
                                          for (a1, a2), n in sorted(cc.items())))
    except ImportError:
        pass

    if a.dry:
        print('\n（--dry，未写文件）')
        return 0
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n写出 %s' % a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
