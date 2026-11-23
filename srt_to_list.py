# -*- coding: utf-8 -*-
"""srt_to_list.py —— 把用户提供的 .srt 转成 GSV 训练用 .list（挂在 DF3 切片上）

原理
----
.srt 是**句级**时间轴（cue = 一行字幕 + 起止时间），没有词级时间戳。
处理：把每个 cue 的词在 cue 时长内**按序均匀铺开** → 近似词级时间戳
      → 按词中点归属到 DF3 切片（与 v5full_asr_chunked.py 的分配逻辑一致）。

兼容
----
· BOM / CRLF / 多行 cue / <i> <b> 等标签 / 花括号注释 / 说话人前缀
· 时间码同时支持 `HH:MM:SS,mmm` 与 `HH:MM:SS.mmm`，以及 `MM:SS,mmm`
"""
import argparse, json, os, re


def parse_srt(path):
    raw = open(path, 'r', encoding='utf-8-sig', errors='replace').read()
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n\s*\n', raw.strip())
    cues = []
    for b in blocks:
        lines = [l for l in b.split('\n') if l.strip()]
        if not lines:
            continue
        ti = None
        for i, l in enumerate(lines):
            if '-->' in l:
                ti = i; break
        if ti is None:
            continue
        m = re.match(r'\s*(?:(\d+):)?(\d+):(\d+)[,.](\d+)\s*-->\s*(?:(\d+):)?(\d+):(\d+)[,.](\d+)', lines[ti])
        if not m:
            continue
        g = m.groups()
        h1 = int(g[0]) if g[0] else 0
        st = h1 * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000.0
        h2 = int(g[4]) if g[4] else 0
        en = h2 * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000.0
        txt = ' '.join(lines[ti + 1:]).strip()
        txt = re.sub(r'<[^>]+>', ' ', txt)          # <i> <b> <font>
        txt = re.sub(r'\{[^}]*\}', ' ', txt)        # {\an8} 之类
        txt = re.sub(r'^\s*[-–—]\s*', '', txt)      # 对话破折号
        txt = re.sub(r'\s+', ' ', txt).strip()
        if not txt or en <= st:
            continue
        cues.append(dict(start=st, end=en, text=txt))
    cues.sort(key=lambda c: c['start'])
    return cues


def cue_words(cues):
    """cue 级 → 近似词级（按序在 cue 时长内均匀铺开）"""
    out = []
    for c in cues:
        toks = c['text'].split()
        if not toks:
            continue
        span = max(0.01, c['end'] - c['start'])
        n = len(toks)
        for k, t in enumerate(toks):
            out.append((c['start'] + span * k / n, c['start'] + span * (k + 1) / n, t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--srt', required=True)
    ap.add_argument('--slices-json', required=True)
    ap.add_argument('--sliced-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--speaker', default='mcconaughey')
    ap.add_argument('--lang', default='en')
    ap.add_argument('--shift', type=float, default=0.0, help='时间轴整体偏移（秒）')
    ap.add_argument('--min-words', type=int, default=1)
    args = ap.parse_args()

    cues = parse_srt(args.srt)
    if not cues:
        raise SystemExit('SRT 解析为空：' + args.srt)
    print('SRT 解析 %d 条 cue | 时间 %.2f - %.2f s' % (len(cues), cues[0]['start'], cues[-1]['end']))

    words = cue_words(cues)
    if args.shift:
        words = [(a + args.shift, b + args.shift, w) for a, b, w in words]
    print('铺开 %d 词' % len(words))

    SJ = json.load(open(args.slices_json, encoding='utf-8'))
    slices = sorted(SJ['slices'], key=lambda s: s['t0'])
    rows = [dict(file=s['file'], t0=s['t0'], t1=s['t1'], words=[], text='') for s in slices]

    wi = 0
    out_of_range = 0
    for (a, b, w) in words:
        mid = (a + b) / 2.0
        if mid < slices[0]['t0'] or mid > slices[-1]['t1']:
            out_of_range += 1
        while wi < len(rows) - 1 and mid > rows[wi]['t1']:
            wi += 1
        while wi > 0 and mid < rows[wi]['t0']:
            wi -= 1
        rows[wi]['words'].append((a, b, w))
    for r in rows:
        r['text'] = re.sub(r'\s+', ' ', ''.join(w for _, _, w in r['words'])).strip()

    print('落在切片区间外的词 %d（SRT 时间轴与音频不一致时会偏大）' % out_of_range)
    print('有文本切片 %d / 无文本 %d' % (sum(1 for r in rows if r['text']),
                                      sum(1 for r in rows if not r['text'])))
    print('\n无文本切片（需人工/ASR 补）:')
    for r in rows:
        if not r['text']:
            print('   %s  (%.2f-%.2fs)' % (r['file'][-46:], r['t0'], r['t1']))

    nwords = sum(len(r['text'].split()) for r in rows)
    J = dict(source_srt=args.srt, n_cues=len(cues), n_words=nwords,
             n_slices=len(slices), n_windows=0, total_sec=round(slices[-1]['t1'], 2),
             windows=[], slices=[dict(file=r['file'], t0=r['t0'], t1=r['t1'], text=r['text'],
                                      nwords=len(r['words']),
                                      words=[[round(a, 3), round(b, 3), w] for a, b, w in r['words']])
                                 for r in rows])
    json.dump(J, open(args.out + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(args.out + '.list', 'w', encoding='utf-8') as f:
        for r in rows:
            if r['text'] and len(r['text'].split()) >= args.min_words:
                f.write('%s|%s|%s|%s\n' % (os.path.join(args.sliced_dir, r['file']),
                                           args.speaker, args.lang, r['text']))
    print('\n写出 %s.list / .json（%d 词）' % (args.out, nwords))
    print('SRTDONE')


if __name__ == '__main__':
    main()
