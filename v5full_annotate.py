# -*- coding: utf-8 -*-
"""v5full_annotate.py —— 标注增强（在 ASR 结果之上做声学校正与质检）

为什么需要
----------
GSV 的标点不是装饰，是**训练符号**：`symbols2.py` 里 `punctuation=[...,",","."]`，
`clean_text("... oceans, and ...")` 会输出 `... OW1 SH AH0 N Z , AH0 N D ...`
—— 逗号/句号作为独立 token 进音素序列，模型必须学会"逗号 → 中等停顿、句号 → 长停顿"。
标注标点与音频实际停顿不一致时，模型学到的就是噪声映射，直接污染韵律。

流程
----
① 采集：从分块 ASR 的词级时间戳算每个词间停顿，取该词的尾标点作标签
② 标定：从 ASR 自身输出学「停顿长度 → 标点」的映射（不拍脑袋定阈值）
③ 校正：按标定阈值重写标点（--fix 才改，默认只报告）
④ 质检：幻觉 / n-gram 重复 / 词数秒越界 / 标点不一致 / 首尾停顿异常
"""
import argparse, json, os, re, sys
from collections import Counter
import numpy as np
import soundfile as sf

HALLUC_PHRASES = [
    'thank you', 'thanks for watching', 'please subscribe', 'subscribe',
    'subtitles by', 'subtitle', 'amara.org', 'transcription by',
    'www.', '.com', 'music', 'applause', 'bye bye',
]
DOMAIN = ['Zoe', 'Snug', 'Grandpa', 'Sirius', 'telescope', 'harbour', 'harbor',
          'sailboat', 'intertidal', 'aquifers', 'constellation', 'meteor',
          'Wonder', 'Calm', 'starlight', 'starfish', 'falcon', 'stuffed']


def split_word(w):
    """把 whisper 的词 token 拆成 (净词, 尾标点)"""
    m = re.match(r"^(.*?)([.,!?;:…]+)$", w.strip())
    if m and m.group(1):
        return m.group(1), m.group(2)
    return w.strip(), ''


def map_punct(p):
    """映射到 GSV 符号表支持的标点集 {. , ! ?}。

    实测（clean_text）：
      `;` `:` `—`  → **被静默丢弃**（音素序列里消失）⇒ 停顿信息丢失，映射成 `,` 保留
      `…`         → 等价于 `.`
      `"` `“”`    → 丢弃
    """
    if not p:
        return ''
    for ch in reversed(p):
        if ch == '.':
            return '.'
        if ch == '!':
            return '!'
        if ch == '?':
            return '?'
        if ch == ',':
            return ','
        if ch == '…':
            return '.'
        if ch in ';:—–':
            return ','
    return ''


def clean_core(c):
    """清理词内引号与孤立撇号（实测 `'` 会变成 `-` 停顿符，孤立 `-` 会读成 "minus"）"""
    c = c.replace('"', '').replace('\u201c', '').replace('\u201d', '')
    c = c.replace('\u2018', "'").replace('\u2019', "'")
    # 只保留「字母-撇号-字母」形式的撇号（don't / Zoe's）
    c = re.sub(r"(?<![A-Za-z])'", '', c)
    c = re.sub(r"'(?![A-Za-z])", '', c)
    # 孤立连字符去掉（会读成 minus）
    c = re.sub(r'(?<![A-Za-z])-(?![A-Za-z])', ' ', c)
    return re.sub(r'\s+', ' ', c).strip()


def pick_punct(gap, t1, t2):
    if gap >= t2:
        return '.'
    if gap >= t1:
        return ','
    return ''


def calibrate(rows):
    buckets = {'': [], ',': [], '.': []}
    for r in rows:
        for k, g in enumerate(r['gaps']):
            p = r['act'][k]
            cls = '.' if p in '.!?' else (',' if p == ',' else '')
            buckets[cls].append(g)
    print('\n=== 标定：停顿长度 → 标点（来自 ASR 自身输出）===')
    arrs = {}
    for k, name in [('', '无标点'), (',', '逗号'), ('.', '句号')]:
        d = np.array(buckets[k]) if buckets[k] else np.array([0.0])
        arrs[k] = d
        print('  %-6s n=%-5d p10 %.2f p25 %.2f p50 %.2f p75 %.2f p90 %.2f'
              % (name, len(d), *[np.percentile(d, q) for q in (10, 25, 50, 75, 90)]))
    t1 = (np.percentile(arrs[''], 85) + np.percentile(arrs[','], 25)) / 2
    t2 = (np.percentile(arrs[','], 85) + np.percentile(arrs['.'], 25)) / 2
    t1 = float(np.clip(t1, 0.15, 0.60))
    t2 = float(np.clip(t2, t1 + 0.15, 2.0))
    print('  ⇒ 阈值：无标点 < %.2fs < 逗号 < %.2fs < 句号' % (t1, t2))
    return t1, t2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--sliced-dir', required=True)
    ap.add_argument('--speaker', default='mcconaughey')
    ap.add_argument('--lang', default='en')
    ap.add_argument('--comma-th', type=float, default=None, help='不填则自动标定')
    ap.add_argument('--period-th', type=float, default=None)
    ap.add_argument('--fix', action='store_true', help='按声学重写标点（默认只报告）')
    ap.add_argument('--keep-min-words', type=int, default=1)
    args = ap.parse_args()

    J = json.load(open(args.json, encoding='utf-8'))
    sl = sorted(J['slices'], key=lambda s: s['t0'])
    print('切片 %d 条 | 模型 %s' % (len(sl), J.get('model', '?')))

    # ---------- Pass A：采集 ----------
    base = []
    for i, s in enumerate(sl):
        ws = [(float(a), float(b), w) for a, b, w in s.get('words', [])]
        nxt = sl[i + 1] if i + 1 < len(sl) else None
        gaps = [max(0.0, ws[k + 1][0] - ws[k][1]) for k in range(len(ws) - 1)]
        tail = None
        if ws:
            tail = max(0.0, s['t1'] - ws[-1][1])
            if nxt and nxt.get('words'):
                tail += max(0.0, float(nxt['words'][0][0]) - nxt['t0'])
            elif nxt:
                tail += (nxt['t1'] - nxt['t0'])
        lead = max(0.0, ws[0][0] - s['t0']) if ws else 0.0
        core, puncs = [], []
        for a, b, w in ws:
            c, p = split_word(w)
            c = clean_core(c) or c          # 保持与 gaps 一一对应，不丢词
            core.append(c); puncs.append(map_punct(p))
        base.append(dict(i=i, file=s['file'], t0=s['t0'], t1=s['t1'],
                         gaps=gaps, tail=tail, lead=lead, core=core, act=puncs,
                         nwords=len(ws),
                         clip_l=sum(1 for a, b, w in ws if a < s['t0'] - 0.04),
                         clip_r=sum(1 for a, b, w in ws if b > s['t1'] + 0.04)))

    # ---------- 标定 ----------
    if args.comma_th is None or args.period_th is None:
        t1, t2 = calibrate(base)
        if args.comma_th is None: args.comma_th = t1
        if args.period_th is None: args.period_th = t2
    else:
        t1, t2 = args.comma_th, args.period_th
        print('\n使用指定阈值：%.2f / %.2f' % (t1, t2))

    # ---------- Pass B：校正 + 质检 ----------
    rows, stat = [], Counter()
    for r in base:
        ws_n = r['nwords']; dur = r['t1'] - r['t0']
        exp = [pick_punct(g, t1, t2) for g in r['gaps']]
        exp_tail = pick_punct(r['tail'], t1, t2) if r['tail'] is not None else ''
        core, puncs = list(r['core']), list(r['act'])

        if args.fix and ws_n >= 2:
            newp = []
            for k in range(ws_n - 1):
                p, want = puncs[k], exp[k]
                if want == '' and p in '.,':
                    p = ''
                elif want == '.' and p in ',;:':
                    p = '.'
                elif want == ',' and p == '':
                    p = ','
                elif want == '.' and p == '':
                    p = '.'
                newp.append(p)
            newp.append(puncs[-1])
            puncs = newp

        text = re.sub(r'\s+', ' ', ' '.join(core)).strip()
        fixed = re.sub(r'\s+', ' ', ''.join(
            (c + (p if p else '') + ' ') for c, p in zip(core, puncs))).strip()

        wps = ws_n / dur if dur > 0 else 0
        flags = []
        low = text.lower()
        if any(h in low for h in HALLUC_PHRASES) and ws_n <= 6:
            flags.append('halluc_phrase'); stat['halluc_phrase'] += 1
        toks = low.split()
        for n in (2, 3):
            hit = any(toks[k:k + n] == toks[k + n:k + 2 * n]
                      for k in range(len(toks) - 2 * n + 1))
            if hit:
                flags.append('repeat_%dgram' % n); stat['repeat'] += 1; break
        if wps > 5.0:
            flags.append('fast_wps'); stat['fast_wps'] += 1
        if dur > 1.2 and wps < 0.9:
            flags.append('slow_wps'); stat['slow_wps'] += 1
        if ws_n < args.keep_min_words:
            flags.append('no_word'); stat['no_word'] += 1
        mism = sum(1 for k in range(ws_n - 1) if puncs[k] != exp[k])
        if mism:
            flags.append('punc%d' % mism); stat['punc_slices'] += 1
            stat['punc_total'] += mism
        if r['tail'] is not None and ws_n:
            lastp = puncs[-1]
            if lastp in '.!?' and r['tail'] < t1:
                flags.append('period_no_pause'); stat['period_no_pause'] += 1
            if lastp == '' and r['tail'] >= t2:
                flags.append('pause_no_period'); stat['pause_no_period'] += 1
        if r['tail'] is not None and r['tail'] >= 2.8:
            flags.append('long_tail'); stat['long_tail'] += 1
        if r['clip_l'] or r['clip_r']:
            flags.append('clip%d%d' % (r['clip_l'], r['clip_r'])); stat['clipped'] += 1

        rows.append(dict(i=r['i'], file=r['file'], t0=r['t0'], t1=r['t1'],
                         dur=round(dur, 2), nwords=ws_n, wps=round(wps, 2),
                         lead=round(r['lead'], 2),
                         tail=round(r['tail'], 2) if r['tail'] is not None else None,
                         gaps=[round(g, 2) for g in r['gaps']],
                         exp=exp, act=r['act'], punc=puncs, exp_tail=exp_tail,
                         core=core, text=text, fixed=fixed, flags=flags))

    n_out = nw_tot = 0
    with open(args.out + '.list', 'w', encoding='utf-8') as f:
        for r in rows:
            t = r['fixed'] if args.fix else r['text']
            if not t or r['nwords'] < args.keep_min_words:
                continue
            f.write('%s|%s|%s|%s\n' % (os.path.join(args.sliced_dir, r['file']),
                                       args.speaker, args.lang, t))
            n_out += 1; nw_tot += len(t.split())
    json.dump(dict(src_json=args.json, fix=args.fix, comma_th=args.comma_th,
                   period_th=args.period_th, n_slices=len(rows), n_out=n_out,
                   n_words=nw_tot, stat=dict(stat), slices=rows),
              open(args.out + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('\n写出 %s.list（%d 条 / %d 词）' % (args.out, n_out, nw_tot))
    print('写出 %s.json' % args.out)
    print('\n=== 质检统计 ===')
    for k, v in stat.most_common():
        print('  %-22s %d' % (k, v))
    tot_gap = sum(len(r['gaps']) for r in rows)
    print('\n  词间停顿 %d 个 | 标点不一致 %d 处 (%.1f%%)'
          % (tot_gap, stat['punc_total'], 100 * stat['punc_total'] / max(1, tot_gap)))
    print('ANNOTDONE')


if __name__ == '__main__':
    main()
