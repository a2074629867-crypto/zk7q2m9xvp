# -*- coding: utf-8 -*-
"""stress_ann.jsonl → stress_llm.json 的转换器（重读进生产链的第一跳）。

和 pause_ann2llm.py 同源问题、不同表：
  · 标注产物只有 `sid / tok / level(可为 2.333 这种三票均值) / why`
  · 生产格式（NARR_STANDARD §X / REQUIREMENTS 205）要求
    `token 下标 + 强度 1-3 + why + sentence_type(stmt/wh/yesno/tag/echo) + focus(焦点词原词)`

所以这里补三件事：
  1. level 三票均值 → 整数档（四舍五入后夹到 1..3），原值留在 `level_raw` 里，不丢证据
  2. `word` / `focus` 从原文 `parse_text` 取，并校验 tok 没有越界
     （越界不会报错，只会把重读打到隔壁词上 —— 与 pause 的 #N 串位是同一类事故）
  3. `sentence_type` 由原文末尾标点 + 疑问词/反意疑问尾**规则推导**，
     标 `derived:rule`，不是标注出来的；标不出的一律 stmt 并在统计里单列

用法：
  G:/Python310/python.exe stress_ann2llm.py --dry
  G:/Python310/python.exe stress_ann2llm.py --out G:/_setup/stress_llm_narr.json
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mt_pause_rules import parse_text      # 单一实现：切词口径绝不在转换器里重写

WH = {'what', 'why', 'who', 'whom', 'whose', 'where', 'when', 'which', 'how'}
TAG_AUX = ("isn't|aren't|wasn't|weren't|don't|doesn't|didn't|can't|couldn't|"
           "won't|wouldn't|hasn't|haven't|hadn't|shouldn't|mustn't")
TAG_RE = re.compile(r"(?:%s)\s+(?:it|he|she|they|you|we|i|there)\s*[?.!]*$"
                    % TAG_AUX, re.I)


def sentence_type(text):
    """stmt / wh / yesno / tag —— 纯规则推导，返回 (type, 依据)。"""
    t = (text or '').strip()
    if not t.endswith('?') and not t.endswith('?\u2019'):
        return 'stmt', 'rule:punct'
    # 末尾反意疑问（", isn't it?"）
    if TAG_RE.search(t):
        return 'tag', 'rule:tag_tail'
    words = re.findall(r"[A-Za-z\u2019']+", t)
    low = [w.lower().replace('\u2019', "'") for w in words]
    # 疑问词可能被前置介词/助动词推后一位（"And what did you say?"）
    head = low[:2]
    if any(w in WH for w in head):
        return 'wh', 'rule:wh_head'
    return 'yesno', 'rule:aux_head'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ann', default=r'G:/_setup/_ann/merged_v3/stress_ann.jsonl')
    ap.add_argument('--texts', default=r'G:/_setup/_narr_plan_for_pause.jsonl')
    ap.add_argument('--out', default=r'G:/_setup/stress_llm_narr.json')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    texts = {}
    for ln in open(a.texts, encoding='utf-8'):
        ln = ln.strip()
        if ln:
            r = json.loads(ln)
            texts[r['id']] = r['text']

    ann = []
    for ln in open(a.ann, encoding='utf-8'):
        ln = ln.strip()
        if ln:
            ann.append(json.loads(ln))

    out = {}
    bad_sid, bad_tok, bad_word, dup = [], [], [], 0
    stype_cnt = collections.Counter()
    lvl_cnt = collections.Counter()
    for r in ann:
        sid = str(r.get('sid') or '')
        if sid not in texts:
            bad_sid.append(sid or '<空>')
            continue
        toks = parse_text(texts[sid])
        try:
            tok = int(r['tok'])
        except Exception:
            bad_tok.append('%s tok=%r 非整数' % (sid, r.get('tok')))
            continue
        if tok < 0 or tok >= len(toks):
            bad_tok.append('%s tok=%d 越界（该句 %d 词）' % (sid, tok, len(toks)))
            continue
        word, punct = toks[tok]
        if not word:
            bad_word.append('%s tok=%d 是纯标点槽' % (sid, tok))
            continue

        raw = float(r.get('level') or 0)
        lvl = int(min(3, max(1, round(raw))))
        lvl_cnt[lvl] += 1
        st, why_st = sentence_type(texts[sid])
        stype_cnt[st] += 1

        slot = out.setdefault(sid, {})
        key = str(tok)
        if key in slot:
            dup += 1
            if lvl <= slot[key]['level']:
                continue                     # 同位置重复：留更强的那条
        slot[key] = {
            'level': lvl,
            'level_raw': round(raw, 3),
            'word': word,
            'focus': word,                  # 焦点词原词（REQUIREMENTS 205）
            'punct': punct,
            'sentence_type': st,
            'sentence_type_src': why_st,
            'why': str(r.get('why') or ''),
            'src': 'llm' if str(r.get('src') or '').startswith('llm') else str(r.get('src') or ''),
            'src_detail': str(r.get('src') or ''),
            'vote': str(r.get('vote') or ''),
        }

    n_slots = sum(len(v) for v in out.values())
    print('标注 %d 条 → 可落盘 %d 处 / %d 句' % (len(ann), n_slots, len(out)))
    print('  跳过：原文缺 %d / 下标越界 %d / 纯标点槽 %d；同位置重复 %d（留强档）'
          % (len(bad_sid), len(bad_tok), len(bad_word), dup))
    for tag, arr in (('原文缺', bad_sid), ('下标异常', bad_tok), ('标点槽', bad_word)):
        for x in arr[:5]:
            print('    %s: %s' % (tag, x))
    print('  强度分布：' + ', '.join('%d档=%d' % (k, v) for k, v in sorted(lvl_cnt.items())))
    print('  句式推导：' + ', '.join('%s=%d' % (k, v) for k, v in stype_cnt.most_common()))

    # 每句重读数自检：>4 个重读的句子基本等于没重读（重读要稀）
    heavy = collections.Counter({k: len(v) for k, v in out.items() if len(v) > 4})
    if heavy:
        print('  ⚠ 单句 >4 处重读：%d 句（最多 %s）'
              % (len(heavy), heavy.most_common(3)))
    covered_tok = sum(len(parse_text(texts[s])) for s in out)
    if covered_tok:
        print('  密度：%d 处 / %d 词 = %.1f%%（1 处 / %.1f 词）'
              % (n_slots, covered_tok, 100.0 * n_slots / covered_tok,
                 covered_tok / max(1, n_slots)))

    payload = {
        '_meta': {
            'book': 'I am the King of the Castle (Susan Hill)',
            'track': 'narr',
            'unit': 'token index from mt_pause_rules.parse_text (0 起，含非标点词)',
            'level': '1..3 整数；level_raw 是三路均值原值，保留可追溯',
            'sentence_type': '规则推导（rule:*），非标注；推导不出的疑问句归 yesno',
            'source': os.path.basename(a.ann),
            'slots': n_slots,
            'sentences': len(out),
        },
    }
    payload.update(out)

    if a.dry:
        print('\n（--dry，未写文件）')
        return 0
    json.dump(payload, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n写出 %s（%.1f KB）' % (a.out, os.path.getsize(a.out) / 1024.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
