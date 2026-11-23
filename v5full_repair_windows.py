# -*- coding: utf-8 -*-
"""v5full_repair_windows.py —— 异常窗修复（漏转 / 重复致幻）

背景
----
v5full_asr_chunked.py 分窗转写时，个别窗会出现两种病：
  ① 漏转：窗内明明有大量人声，却只转出几个词（whisper 的 no_speech 误判 / 解码提前停）；
  ② 重复致幻：同一个短语被反复吐出来（解码陷入 loop），词数远超该时长合理上限。

判据
----
以**全片窗级 wps（词/秒）中位数**为基准 med：
  wps = nwords / (t1 - t0)
  异常 = wps < LO*med 或 wps > HI*med     （默认 LO=0.35, HI=1.9）

修复
----
对每个异常窗跑一组「重转阶梯」，每档用不同解码策略：
  A: beam5 + 无 initial_prompt          （去上下文污染）
  B: beam1 + temperature=0 + vad_filter  （VAD 切静音，治漏转）
  C: beam5 + vad_filter + 严 compression_ratio/logprob（治重复 loop）
  D: beam5 + 无 prompt + temperature 阶梯回退（默认行为）
取 wps 最接近 med 的那一档；若都偏离太远，取最接近者。
"""
import argparse, json, os, re, sys, time
import numpy as np
import soundfile as sf


def read_mono(path):
    x, sr = sf.read(path, dtype='float64', always_2d=True)
    return x.mean(1), sr


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


def transcribe_cfg(model, seg, lang, prompt, cfg):
    """按 cfg 跑一次转写，返回词列表 [(start,end,word)] 与文本。"""
    segs, info = model.transcribe(
        seg, language=lang,
        beam_size=cfg.get('beam', 5),
        word_timestamps=True,
        condition_on_previous_text=False,
        initial_prompt=(prompt if cfg.get('use_prompt', True) else None),
        vad_filter=cfg.get('vad', False),
        compression_ratio_threshold=cfg.get('cr', 2.4),
        log_prob_threshold=cfg.get('lp', -1.0),
        no_speech_threshold=cfg.get('ns', 0.6),
        temperature=cfg.get('temp', [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]),
    )
    ws, txt = [], ''
    for s in segs:
        txt += s.text
        for w in (s.words or []):
            ws.append((float(w.start), float(w.end), w.word))
    return ws, txt


LADDER = [
    dict(name='A_beam5_noprompt',      beam=5, use_prompt=False, vad=False),
    dict(name='B_beam1_t0_vad',        beam=1, use_prompt=False, vad=True, temp=[0.0]),
    dict(name='C_beam5_vad_strict',    beam=5, use_prompt=True,  vad=True, cr=2.2, lp=-0.8),
    dict(name='D_beam5_prompt_t0',     beam=5, use_prompt=True,  vad=False, temp=[0.0]),
    dict(name='E_permissive_nospeech', beam=5, use_prompt=False, vad=False,
         ns=0.95, lp=-2.0, cr=3.0),
]


def repeat_score(words):
    """重复 3-gram / 4-gram 计数（致幻的指纹）"""
    toks = [re.sub(r'[^a-z0-9]', '', w.lower()) for _, _, w in words]
    toks = [t for t in toks if t]
    s = 0
    for n in (3, 4):
        for k in range(len(toks) - 2 * n + 1):
            if toks[k:k + n] == toks[k + n:k + 2 * n]:
                s += 1
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True)
    ap.add_argument('--src', required=True)
    ap.add_argument('--json', required=True, help='chunked 脚本产出的 .json')
    ap.add_argument('--slices-json', required=True)
    ap.add_argument('--out', required=True, help='修复后 json 前缀')
    ap.add_argument('--target', type=float, default=26.0)
    ap.add_argument('--threads', type=int, default=10)
    ap.add_argument('--lo', type=float, default=0.35)
    ap.add_argument('--hi', type=float, default=1.9)
    ap.add_argument('--only', default='', help='只修指定窗号，逗号分隔（调试）')
    args = ap.parse_args()

    from faster_whisper import WhisperModel

    J = json.load(open(args.json, encoding='utf-8'))
    wins = J['windows']
    SJ = json.load(open(args.slices_json, encoding='utf-8'))
    slices = sorted(SJ['slices'], key=lambda s: s['t0'])
    groups = group_slices(slices, target=args.target)
    assert len(groups) == len(wins), '窗数不符 %d vs %d' % (len(groups), len(wins))

    # ---- 全片 wps 中位数（只用有词的窗，避免空窗的 0 拉低基准）----
    wps_all = []
    for w in wins:
        span = max(0.5, w['t1'] - w['t0'])
        if w['nwords'] >= 3:
            wps_all.append(w['nwords'] / span)
    if not wps_all:
        wps_all = [1.0]
    med = float(np.median(wps_all))
    print('全片窗级 wps 中位 %.3f（%d 个有词窗）| p10 %.3f p90 %.3f' %
          (med, len(wps_all), float(np.percentile(wps_all, 10)), float(np.percentile(wps_all, 90))))

    lo, hi = args.lo * med, args.hi * med
    flags = []
    for w in wins:
        span = max(0.5, w['t1'] - w['t0'])
        wps = w['nwords'] / span
        if wps < lo or wps > hi:
            flags.append(w['i'])
    if args.only:
        flags = [int(v) for v in args.only.split(',')]
    print('异常窗 %d 个: %s' % (len(flags), flags))
    if not flags:
        print('无需修复'); return

    x, sr = read_mono(args.src)
    t0 = time.time()
    model = WhisperModel(args.model, device='cpu', compute_type='int8', cpu_threads=args.threads)
    print('[load] %.1fs' % (time.time() - t0))

    fixed = {}
    # 原词流（用于把「原窗」也作为一个候选，保证修复不会越修越差）
    orig_words = []
    for s in J['slices']:
        for a_, b_, w_ in (s.get('words') or []):
            orig_words.append((float(a_), float(b_), w_))
    orig_words.sort(key=lambda t: t[0])

    for gi in flags:
        g = groups[gi]
        a, b = g[0]['t0'], g[-1]['t1']
        span = max(0.5, b - a)
        seg = x[int(a * sr):int(b * sr)].astype(np.float32)
        # 上下文：取上一窗文本尾 200 字
        prev = ''
        if gi > 0:
            prev = wins[gi - 1].get('text', '')[-200:]
        print('\n--- 窗 %d  %.2f-%.2f (%.1fs)  原 %d词 wps %.2f (med %.2f) ---'
              % (gi, a, b, span, wins[gi]['nwords'], wins[gi]['nwords'] / span, med))
        cands = []
        # 候选 0：原窗（不重转）
        ow = [(s0, s1, wd) for (s0, s1, wd) in orig_words if a <= (s0 + s1) / 2.0 <= b]
        if ow:
            wps = len(ow) / span
            rep = repeat_score(ow)
            cands.append(dict(cfg='ORIG', n=len(ow), wps=wps,
                              d=abs(np.log(max(1e-6, wps) / med)), rep=rep,
                              score=abs(np.log(max(1e-6, wps) / med)) + 0.6 * min(rep, 4),
                              text=re.sub(r'\s+', ' ', ''.join(w for _, _, w in ow)).strip(),
                              words=[[round(s0, 3), round(s1, 3), wd] for s0, s1, wd in ow]))
            print('   %-22s -> %3d词  wps %.2f  dev %.2f  rep %d  | %s'
                  % ('ORIG(保留原结果)', len(ow), wps, cands[-1]['d'], rep, cands[-1]['text'][:60]))
        for cfg in LADDER:
            tt = time.time()
            try:
                ws, txt = transcribe_cfg(model, seg, 'en', prev, cfg)
            except Exception as e:
                print('   %-22s 失败: %s' % (cfg['name'], str(e)[:70]))
                continue
            wps = len(ws) / span
            d = abs(np.log(max(1e-6, wps) / med))
            rep = repeat_score(ws)
            score = d + 0.6 * min(rep, 4)
            cands.append(dict(cfg=cfg['name'], n=len(ws), wps=wps, d=d, rep=rep,
                              score=score, text=txt.strip(),
                              words=[[round(a + s, 3), round(a + e, 3), w] for s, e, w in ws]))
            print('   %-22s -> %3d词  wps %.2f  dev %.2f  rep %d  (%.1fs)  | %s'
                  % (cfg['name'], len(ws), wps, d, rep, time.time() - tt, txt.strip()[:60]))
        # 择优：先要落在 [0.55*med, 1.7*med] 内，取 score 最小；没有则取全局 score 最小
        ok = [c for c in cands if 0.55 * med <= c['wps'] <= 1.7 * med]
        pick = min(ok or cands, key=lambda c: c['score']) if cands else None
        if pick:
            print('   ==> 选 %s (%d词 wps %.2f rep %d)' % (pick['cfg'], pick['n'], pick['wps'], pick['rep']))
            fixed[gi] = pick

    # ---- 合并回 windows ----
    for gi, c in fixed.items():
        wins[gi]['nwords'] = c['n']
        wins[gi]['text'] = c['text']
        wins[gi]['repair'] = c['cfg']

    # ---- 重建全量词流：原有 slices[].words 剔除被修复窗区间，再并入新词 ----
    fixed_spans = [(wins[gi]['t0'], wins[gi]['t1']) for gi in fixed]

    def in_fixed(mid):
        for a_, b_ in fixed_spans:
            if a_ <= mid <= b_:
                return True
        return False

    all_words = []
    for s in J['slices']:
        for ws_, we_, wd in (s.get('words') or []):
            if not in_fixed((ws_ + we_) / 2.0):
                all_words.append((ws_, we_, wd))
    for gi in fixed:
        for ws_, we_, wd in fixed[gi]['words']:
            all_words.append((ws_, we_, wd))
    all_words.sort(key=lambda t: t[0])

    rows = [dict(file=s['file'], t0=s['t0'], t1=s['t1'], words=[], text='') for s in slices]
    wi = 0
    for (ws_, we_, w) in all_words:
        mid = (ws_ + we_) / 2.0
        while wi < len(rows) - 1 and mid > rows[wi]['t1']:
            wi += 1
        while wi > 0 and mid < rows[wi]['t0']:
            wi -= 1
        rows[wi]['words'].append((ws_, we_, w))
    for r in rows:
        r['text'] = re.sub(r'\s+', ' ', ''.join(w for _, _, w in r['words'])).strip()

    nwords = sum(len(r['text'].split()) for r in rows)
    print('\n修复后总词数 %d（原 %d）' % (nwords, J['n_words']))
    print('有文本切片 %d / 无文本 %d' % (sum(1 for r in rows if r['text']),
                                      sum(1 for r in rows if not r['text'])))

    J['windows'] = wins
    J['n_words'] = nwords
    J['slices'] = [dict(file=r['file'], t0=r['t0'], t1=r['t1'], text=r['text'],
                        nwords=len(r['words']),
                        words=[[round(a, 3), round(b, 3), w] for a, b, w in r['words']])
                   for r in rows]
    J['repaired_windows'] = sorted(fixed.keys())
    json.dump(J, open(args.out + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # list
    with open(args.out + '.list', 'w', encoding='utf-8') as f:
        for r in rows:
            if r['text']:
                f.write('%s|mcconaughey|en|%s\n' % (r['file'], r['text']))
    print('写出 %s.json / .list' % args.out)
    print('REPAIRDONE')


if __name__ == '__main__':
    main()
