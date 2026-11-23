# -*- coding: utf-8 -*-
"""mt_matt_rule_mine.py —— 从马修母带提炼「可迁移的韵律规则」。

为什么不用 wonder_final.json 的间隙当停顿时长：
  实测那批时间戳量化到 80ms 网格（2127 个间隙只有 30 个唯一值，0.16/0.24/0.32 占 83%），
  而夏尔真实停顿 0.15~0.76s 只有 7.6 个格子 ⇒ 精度不足，提炼不出规则。
  ⇒ 停顿一律用 VAD（10ms 精度）测；json 只提供「停顿落在哪两个词之间」的文本结构。

与 mc_pause_rules.py 的区别：
  那一版输出「标点类型 → 中位秒数」= 全局统计，不针对具体句子。
  这一版输出「结构条件 → 时长分布 + F0 行为」，条件由 LLM 从上下文判得出，
  秒数由真人样本支撑。这是「规则」而不是「分位数表」。

用法：
  python mt_matt_rule_mine.py            # 建停顿清单（VAD + 词对齐）
  python mt_matt_rule_mine.py --report   # 打印结构分组
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict

import numpy as np
import soundfile as sf

sys.path.insert(0, r'G:/_setup')

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
WORDS = "G:/GPT-SoVITS/_dataset_v5full/wonder_final.json"
OUT = r'G:/_setup/matt_pause_mined.json'
SR = 32000

CONJ_COORD = set("and but or nor yet so for".split())
CONJ_SUB = set("""because when while if though although unless until since as than that
which who whom whose where whether after before once whenever wherever whereas
whereby wherein whilst""".split())
ART = set("the a an".split())
PREP = set("""of in on at to with from by about into over under through between across
around like without within upon toward towards against along behind beyond during
except inside outside past off onto unto per via""".split())
PRON = set("""i you he she it we they me him her us them my your his its our their
this these those what something someone anything anyone everyone everything nothing
nobody anybody himself herself itself myself yourself themselves ourselves""".split())
AUX = set("""is are was were be been being am do does did have has had will would
can could shall should may might must""".split())
NEG = set("not no never none nothing nobody".split())
ADV = set("""very just still even only too also always now then here there again
once almost really quite rather well back away together apart instead anyway
perhaps maybe actually finally suddenly simply truly slowly quickly softly""".split())
FILLER = set("""well oh ah uh um er yes yeah okay ok right look listen please""".split())

PRIORITY = [("NEG", NEG), ("CONJ_SUB", CONJ_SUB), ("CONJ_COORD", CONJ_COORD),
            ("AUX", AUX), ("ART", ART), ("PREP", PREP), ("PRON", PRON),
            ("ADV", ADV), ("FILLER", FILLER)]

PUNCT_MAP = {",": ",", ".": ".", "?": "?", "!": "!", ";": ";", ":": ":"}


def norm(w):
    return re.sub(r"^[^\w']+|[^\w']+$", "", w.lower())


def cls_of(word):
    w = norm(word)
    if not w:
        return "OTHER"
    for name, s in PRIORITY:
        if w in s:
            return name
    if w.endswith("ly"):
        return "ADV"
    if w.endswith("ing") or w.endswith("ed"):
        return "VERB"
    return "OTHER"


def tail_punct(word):
    m = re.search(r"([,\.\?;:!]+)\s*$", word)
    if not m:
        return None
    return PUNCT_MAP.get(m.group(1)[0])


def syll(w):
    w = norm(w)
    if not w:
        return 1
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def vad_gaps(path, thr=-35.0, fill=8, drop=12, sil=0.10):
    x, sr = sf.read(path, dtype="float64", always_2d=True)
    x = x.mean(1)
    hop = int(0.010 * sr)
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() + thr)
    i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]:
                j += 1
            if i > 0 and j < len(m) and (j - i) < fill:
                m[i:j] = True
            i = j
        else:
            i += 1
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) < drop:
                m[i:j] = False
            i = j
        else:
            i += 1
    segs, i = [], 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]:
                j += 1
            segs.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    out = []
    for k in range(len(segs) - 1):
        s, e = segs[k][1], segs[k + 1][0]
        d = e - s
        if d >= sil:
            out.append((round(s, 2), round(e, 2), round(d, 3)))
    return out, len(x) / sr


def load_words(path):
    d = json.load(open(path, encoding='utf-8'))
    out = []
    for s in d['slices']:
        for a, b, w in s['words']:
            if b < a:
                a, b = b, a
            out.append(dict(t0=float(a), t1=float(b), w=w, norm=norm(w),
                            punct=tail_punct(w), sid=s['file']))
    out.sort(key=lambda r: r['t0'])
    return out


def build():
    print('读母带 …', flush=True)
    gaps, total = vad_gaps(MASTER)
    words = load_words(WORDS)
    print('VAD 停顿 %d 处（≥0.10s），母带 %.1fs' % (len(gaps), total), flush=True)
    print('词 %d 个（时间戳量化 80ms）' % len(words), flush=True)
    gd = np.array([g[2] for g in gaps])
    print('停顿时长 p10 %.2f p50 %.2f p90 %.2f max %.2f'
          % (np.percentile(gd, 10), np.median(gd), np.percentile(gd, 90), gd.max()),
          flush=True)

    t1s = np.array([w['t1'] for w in words])
    t0s = np.array([w['t0'] for w in words])
    rows, miss = [], 0
    for s, e, dur in gaps:
        ip = int(np.searchsorted(t1s, s, side='right') - 1)
        inx = int(np.searchsorted(t0s, e, side='left'))
        if ip < 1 or inx >= len(words) or inx - ip > 4 or inx <= ip:
            miss += 1
            continue
        rows.append(dict(s=s, e=e, gap=dur, i_prev=ip, i_next=inx))
    print('对齐成功 %d / %d（丢 %d）' % (len(rows), len(gaps), miss), flush=True)

    # ---- 结构特征
    recs = []
    for r in rows:
        ip, inx = r['i_prev'], r['i_next']
        p, n = words[ip], words[inx]
        # 距上一个 ≥0.30s 停顿
        sw = ss = 0
        for k in range(ip, -1, -1):
            sw += 1
            ss += syll(words[k]['norm'])
            if k == 0:
                break
            if words[k]['t0'] - words[k - 1]['t1'] >= 0.30:
                break
        tw = ts = 0
        for k in range(inx, len(words)):
            tw += 1
            ts += syll(words[k]['norm'])
            if k == len(words) - 1:
                break
            if words[k + 1]['t0'] - words[k]['t1'] >= 0.30:
                break
        recs.append(dict(
            s=r['s'], e=r['e'], gap=r['gap'],
            prev=p['w'], next=n['w'],
            prev_cls=cls_of(p['norm']), next_cls=cls_of(n['norm']),
            prev_punct=p['punct'], next_punct=n['punct'],
            since_words=sw, since_syll=ss, till_words=tw, till_syll=ts,
        ))
    json.dump(dict(meta=dict(master=MASTER, total_sec=round(total, 1),
                             n_gap=len(gaps), n_aligned=len(recs),
                             note='停顿 VAD 10ms；词时间戳量化 80ms，只用于定结构'),
                   recs=recs), open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('写出', OUT)
    return recs


def report(recs):
    def st(v):
        a = np.array(v)
        return 'n=%3d  中位 %.2f  p25 %.2f  p75 %.2f  跨度 %.2f' % (
            len(a), np.median(a), np.percentile(a, 25), np.percentile(a, 75),
            a.max() - a.min())

    print('\n=== 按「前一词语法类 + 标点」分组 ===')
    g = defaultdict(list)
    for r in recs:
        key = '%s%s' % (r['prev_punct'] or '-', r['prev_cls'])
        g[key].append(r['gap'])
    for k in sorted(g, key=lambda x: -len(g[x])):
        if len(g[k]) >= 8:
            print('  %-16s %s' % (k, st(g[k])))

    print('\n=== 按「后一词语法类」分组（只看 prev 有标点的）===')
    g = defaultdict(list)
    for r in recs:
        if r['prev_punct'] in (',', '.', '?', '!'):
            g[r['next_cls']].append(r['gap'])
    for k in sorted(g, key=lambda x: -len(g[x])):
        if len(g[k]) >= 5:
            print('  %-12s %s' % (k, st(g[k])))

    print('\n=== 节奏：距上一停顿的词数 ===')
    for lo, hi in ((1, 2), (2, 4), (4, 7), (7, 11), (11, 99)):
        v = [r['gap'] for r in recs if lo <= r['since_words'] < hi]
        if len(v) >= 8:
            print('  %2d~%2d 词  %s' % (lo, hi - 1, st(v)))

    print('\n=== 节奏：到下一停顿的词数 ===')
    for lo, hi in ((1, 2), (2, 4), (4, 7), (7, 11), (11, 99)):
        v = [r['gap'] for r in recs if lo <= r['till_words'] < hi]
        if len(v) >= 8:
            print('  %2d~%2d 词  %s' % (lo, hi - 1, st(v)))

    print('\n=== 解释力（log gap 的组间方差占比 eta²）===')
    lg = np.log(np.array([r['gap'] for r in recs]))
    for key in ('prev_punct', 'next_cls', 'prev_cls'):
        g = defaultdict(list)
        for r, y in zip(recs, lg):
            g[r[key]].append(y)
        tot = ((lg - lg.mean()) ** 2).sum()
        between = sum(len(v) * (np.mean(v) - lg.mean()) ** 2 for v in g.values())
        print('  %-12s 组数 %2d  eta² %.3f' % (key, len(g), between / tot))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true')
    a = ap.parse_args()
    if a.report:
        recs = json.load(open(OUT, encoding='utf-8'))['recs']
    else:
        recs = build()
    report(recs)
