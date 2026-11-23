# -*- coding: utf-8 -*-
"""给非 Wonder 编号体系的书生成 _punct_expr.json（REQUIREMENTS 19e）。

为什么需要这个脚本：`mt_punct_expr.py` 的 `expr_of(wav, text)` 本身是通用的，
但它的 `main()` 硬编码 `from ch123_plan import PLAN, INNER`（Wonder 的 L%03d/I%02d）。
本书编号是 c1_0001…，于是 `_punct_expr.json` 里没有任何本书条目
⇒ `mt_final_pause.py` 的 EXPR 对本书永远是空 dict ⇒ 19f 的 weak/none 逻辑不执行。
这与「mt_final_pause 的 TEXTS 只认 Wonder 编号」是同一个坑，已修过一半（--texts），
这里是另一半。

用法：
  G:/Python310/python.exe run_expr_custom.py --texts _castle_en_ch123_plan.jsonl \
      --audio _audio_ch123/out --out _punct_expr_castle.json [--limit N] [--workers 4]
"""
import argparse
import json
import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mt_punct_expr import expr_of      # 单一实现，绝不在这里重写一份


def one(args):
    k, wav, text = args
    try:
        rows, rw, toks = expr_of(wav, text)
        return k, rows, len(rw), len(toks), None
    except Exception as e:
        return k, [], 0, 0, '%s: %s' % (type(e).__name__, e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--texts', required=True, help='jsonl，每行含 id / text（可含 speaker）')
    ap.add_argument('--audio', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--workers', type=int, default=1,
                    help='>1 用进程池；parselmouth 单条占 CPU，2~4 一般最快')
    a = ap.parse_args()

    items = []
    for ln in open(a.texts, encoding='utf-8'):
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        wav = os.path.join(a.audio, r['id'] + '.wav')
        if os.path.exists(wav):
            items.append((r['id'], wav, r['text']))
    if a.limit:
        items = items[:a.limit]
    print('待测 %d 条（音频缺 %d 条）' % (len(items), 0), flush=True)

    out = {}
    bad = []
    if a.workers > 1:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(one, it) for it in items]
            for n, f in enumerate(as_completed(futs), 1):
                k, rows, nrw, ntok, err = f.result()
                if err:
                    bad.append((k, err))
                else:
                    out[k] = rows
                if n % 50 == 0:
                    print('  %d/%d' % (n, len(items)), flush=True)
    else:
        for n, it in enumerate(items, 1):
            k, rows, nrw, ntok, err = one(it)
            if err:
                bad.append((k, err))
            else:
                out[k] = rows
            if n % 50 == 0:
                print('  %d/%d' % (n, len(items)), flush=True)

    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    import collections
    c = collections.Counter(r['status'] for v in out.values() for r in v)
    tot = sum(c.values())
    print('\n写出 %s：%d 条台词 / %d 处标点' % (a.out, len(out), tot))
    for s in ('strong', 'weak', 'none', 'unaligned'):
        if c[s]:
            print('  %-10s %3d (%.0f%%)' % (s, c[s], 100 * c[s] / tot))
    if bad:
        print('失败 %d 条（前 5）：' % len(bad))
        for k, e in bad[:5]:
            print('  %-9s %s' % (k, e))


if __name__ == '__main__':
    main()
