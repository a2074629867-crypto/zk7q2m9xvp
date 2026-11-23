# -*- coding: utf-8 -*-
"""parakeet_run.py —— 用 onnx-asr 跑 Parakeet-TDT-0.6B-v3（CPU/ONNX，无 torch）

用法
----
python parakeet_run.py probe --wav <片段>            # 先看结果结构
python parakeet_run.py run   --wav <整段> --out <前缀>   # 全量转写 → .srt + .json

输出
----
<out>.srt   段级字幕（自带标点与大小写）
<out>.json  段 + token 级时间戳（供 GSV 流水线用）
"""
import argparse, json, os, sys, time

MODEL = 'nemo-parakeet-tdt-0.6b-v3'


def fmt_ts(t, comma=True):
    if t is None:
        return '00:00:00,000'
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return '%02d:%02d:%02d%s%03d' % (h, m, s, ',' if comma else '.', ms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['probe', 'run'])
    ap.add_argument('--wav', required=True)
    ap.add_argument('--out', default='')
    ap.add_argument('--quant', default='', help='int8 / fp16 / 留空=默认')
    ap.add_argument('--no-vad', action='store_true', help='不用 VAD（短片段）')
    ap.add_argument('--threads', type=int, default=0)
    args = ap.parse_args()

    if args.threads:
        os.environ['OMP_NUM_THREADS'] = str(args.threads)

    import onnx_asr
    t0 = time.time()
    kw = {}
    if args.quant:
        kw['quantization'] = args.quant
    model = onnx_asr.load_model(MODEL, **kw)
    print('[load] %.1fs' % (time.time() - t0), flush=True)

    m = model.with_timestamps()
    if not args.no_vad:
        vad = onnx_asr.load_vad('silero')
        m = m.with_vad(vad)
        print('[vad] silero 已挂', flush=True)

    t0 = time.time()
    results = list(m.recognize(args.wav))
    dt = time.time() - t0
    print('[asr] %d 段  %.1fs' % (len(results), dt), flush=True)

    if args.mode == 'probe':
        r = results[0]
        print('\n类型:', type(r))
        print('字段:', [a for a in dir(r) if not a.startswith('_')])
        for i, r in enumerate(results[:6]):
            d = {a: getattr(r, a, None) for a in ('start', 'end', 'text')}
            print('\n--- 段 %d ---' % i)
            print('  start=%s end=%s' % (d['start'], d['end']))
            print('  text=%r' % (str(d['text'])[:200],))
            tk = getattr(r, 'tokens', None)
            ts = getattr(r, 'timestamps', None)
            if tk is not None:
                print('  tokens(%d): %s' % (len(tk), tk[:25]))
            if ts is not None:
                print('  timestamps(%d): %s' % (len(ts), [round(float(x), 2) for x in ts[:25]]))
            if getattr(r, 'logprobs', None) is not None:
                print('  logprobs: %d 个' % len(r.logprobs))
        print('\nPROBEDONE')
        return

    # ---- run：写 srt + json ----
    segs = []
    for r in results:
        st = getattr(r, 'start', None)
        en = getattr(r, 'end', None)
        tx = (getattr(r, 'text', '') or '').strip()
        if not tx:
            continue
        tk = getattr(r, 'tokens', None)
        ts = getattr(r, 'timestamps', None)
        segs.append(dict(start=float(st) if st is not None else None,
                         end=float(en) if en is not None else None,
                         text=tx,
                         tokens=list(tk) if tk is not None else [],
                         timestamps=[float(x) for x in ts] if ts is not None else []))

    srt = []
    for i, s in enumerate(segs, 1):
        srt.append('%d\n%s --> %s\n%s\n' % (i, fmt_ts(s['start']), fmt_ts(s['end']), s['text']))
    open(args.out + '.srt', 'w', encoding='utf-8').write('\n'.join(srt))

    ntok = sum(len(s['tokens']) for s in segs)
    nw = sum(len(s['text'].split()) for s in segs)
    json.dump(dict(model=MODEL, quant=args.quant or 'default', wav=args.wav,
                   vad=(not args.no_vad), n_segments=len(segs), n_words=nw, n_tokens=ntok,
                   asr_sec=round(dt, 1), segments=segs),
              open(args.out + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('\n写出 %s.srt（%d 段 / %d 词 / %d token）' % (args.out, len(segs), nw, ntok))
    print('写出 %s.json' % args.out)
    print('\n前 8 段预览:')
    for s in segs[:8]:
        print('  [%s-%s] %s' % (fmt_ts(s['start'])[:12], fmt_ts(s['end'])[:12], s['text'][:110]))
    print('\nPARAKEETDONE')


if __name__ == '__main__':
    main()
