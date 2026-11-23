# -*- coding: utf-8 -*-
"""v5full_reassign.py —— 把已有词流重挂到新切片边界（换音频时不重跑 ASR）

原理
----
notch 只在 60-85Hz 有影响（实测 90Hz 以上 ≤0.3dB），whisper 的 log-mel 在该频段
分辨力极低 ⇒ ASR 文本与音频版本无关。所以换音频时：
  ① 复用已有词流（全局时间戳不变）
  ② 只把词重新分配到新切片的 [t0,t1] 边界上
  ③ 按新边界重算窗（供 repair 脚本用）

输出格式与 v5full_asr_chunked.py 完全一致（.json / .list）。
"""
import argparse, json, os, re
import numpy as np


def group_slices(slices, target=26.0):
    groups, cur = [], []
    for s in slices:
        if not cur:
            cur = [s]; continue
        if s['t1'] - cur[0]['t0'] <= target:
            cur.append(s)
        else:
            groups.append(cur); cur = [s]
    if cur:
        groups.append(cur)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--words-json', required=True, help='已有词流（含 slices[].words 全局时间戳）')
    ap.add_argument('--slices-json', required=True, help='新切片锚点')
    ap.add_argument('--sliced-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--speaker', default='mcconaughey')
    ap.add_argument('--lang', default='en')
    ap.add_argument('--target', type=float, default=26.0)
    ap.add_argument('--drop-anomalous', action='store_true',
                    help='先剔除旧 json 中 wps 异常的窗（致幻/漏转）的词，避免污染新边界')
    ap.add_argument('--lo', type=float, default=0.35)
    ap.add_argument('--hi', type=float, default=1.9)
    args = ap.parse_args()

    W = json.load(open(args.words_json, encoding='utf-8'))
    SJ = json.load(open(args.slices_json, encoding='utf-8'))
    slices = sorted(SJ['slices'], key=lambda s: s['t0'])

    # ---- 可选：剔除旧异常窗 ----
    drop_spans = []
    if args.drop_anomalous:
        ow = W['windows']
        wps = np.array([x['nwords'] / max(0.5, x['t1'] - x['t0']) for x in ow])
        med = float(np.median(wps))
        lo, hi = args.lo * med, args.hi * med
        for x in ow:
            wp = x['nwords'] / max(0.5, x['t1'] - x['t0'])
            if wp < lo or wp > hi:
                drop_spans.append((x['t0'], x['t1']))
        print('旧窗级 wps 中位 %.3f | 剔除异常窗 %d 个: %s'
              % (med, len(drop_spans), [(round(a, 1), round(b, 1)) for a, b in drop_spans]))

    def dropped(mid):
        return any(a <= mid <= b for a, b in drop_spans)

    # 收集全部词（全局时间戳）
    all_words = []
    ndrop = 0
    for s in W['slices']:
        for a, b, w in (s.get('words') or []):
            if drop_spans and dropped((float(a) + float(b)) / 2.0):
                ndrop += 1; continue
            all_words.append((float(a), float(b), w))
    all_words.sort(key=lambda t: t[0])
    print('复用词流 %d 词（剔除 %d 词）| 新切片 %d 段' % (len(all_words), ndrop, len(slices)))

    # 分配到新切片
    rows = [dict(file=s['file'], t0=s['t0'], t1=s['t1'], words=[], text='') for s in slices]
    wi = 0
    for (ws, we, w) in all_words:
        mid = (ws + we) / 2.0
        while wi < len(rows) - 1 and mid > rows[wi]['t1']:
            wi += 1
        while wi > 0 and mid < rows[wi]['t0']:
            wi -= 1
        rows[wi]['words'].append((ws, we, w))
    for r in rows:
        r['text'] = re.sub(r'\s+', ' ', ' '.join(w for _, _, w in r['words'])).strip()

    # 按新边界重算窗
    groups = group_slices(slices, target=args.target)
    windows = []
    for gi, g in enumerate(groups):
        a, b = g[0]['t0'], g[-1]['t1']
        # 窗内文本 = 落在窗区间的词
        ws_ = []
        for (s0, s1, w) in all_words:
            m = (s0 + s1) / 2.0
            if a <= m <= b:
                ws_.append(w)
        windows.append(dict(i=gi, t0=round(a, 2), t1=round(b, 2), n=len(g),
                            nwords=len(ws_), sec=0.0,
                            text=re.sub(r'\s+', ' ', ' '.join(ws_)).strip()))
    spans = [g[-1]['t1'] - g[0]['t0'] for g in groups]
    print('新分窗 %d 个 | 窗长 中位 %.1fs' % (len(groups), float(np.median(spans))))

    nwords = sum(len(r['text'].split()) for r in rows)
    print('有文本切片 %d / 无文本 %d | 总词 %d'
          % (sum(1 for r in rows if r['text']), sum(1 for r in rows if not r['text']), nwords))

    J = dict(model=W.get('model', '?'), src=args.sliced_dir, total_sec=round(slices[-1]['t1'], 2),
             n_slices=len(slices), n_windows=len(groups), n_words=nwords,
             reassigned_from=args.words_json,
             windows=windows,
             slices=[dict(file=r['file'], t0=r['t0'], t1=r['t1'], text=r['text'],
                          nwords=len(r['words']),
                          words=[[round(a, 3), round(b, 3), w] for a, b, w in r['words']])
                     for r in rows])
    json.dump(J, open(args.out + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    with open(args.out + '.list', 'w', encoding='utf-8') as f:
        for r in rows:
            if r['text']:
                f.write('%s|%s|%s|%s\n' % (os.path.join(args.sliced_dir, r['file']),
                                           args.speaker, args.lang, r['text']))
    print('写出 %s.json / .list' % args.out)
    print('REASSIGNDONE')


if __name__ == '__main__':
    main()
