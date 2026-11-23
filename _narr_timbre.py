# -*- coding: utf-8 -*-
"""_narr_timbre.py —— 旁白 716 条逐段音色稳定性批处理

复用 ch123_segcheck.check()（CAM++ 段间互比），本脚本只负责批量、落盘、统计。
必须用装 kaldi_native_fbank 的解释器跑：
    C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe

输出：_narr_timbre.json
"""
import os, sys, json

sys.path.insert(0, 'G:/_setup')
import ch123_segcheck as CS

AUD = 'G:/_setup/_audio_ch123/out'
LIST = 'G:/_setup/_narr_check4/_narr_check.json'
OUT = 'G:/_setup/_narr_timbre.json'


units = [x['unit'] for x in json.load(open(LIST, encoding='utf-8'))]
print('[in] %d units' % len(units), flush=True)

res = []
if os.path.exists(OUT):
    try:
        res = json.load(open(OUT, encoding='utf-8'))
        print('[resume] %d 已完成' % len(res), flush=True)
    except Exception:
        res = []
done = {r['unit'] for r in res}

for k, u in enumerate(units, 1):
    if u in done:
        continue
    p = os.path.join(AUD, u + '.wav')
    if not os.path.exists(p):
        continue
    try:
        r = CS.check(p)
    except Exception as e:
        print('  %s ERR %s' % (u, e), flush=True)
        continue
    if not r:
        continue
    res.append(dict(unit=u, n=r['n'], rows=[round(x, 4) for x in r['rows']],
                    worst=r['worst'], f0_span=r.get('f0_span'),
                    lvl_max=r.get('lvl_max'),
                    segs=[dict(i=d['i'], t0=round(d['t0'], 2), t1=round(d['t1'], 2),
                               f0=round(d['f0'], 1)) for d in r['info']]))
    if k % 20 == 0:
        json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
        print('  %d/%d  %s  min=%.3f' % (k, len(units), u, min(res[-1]['rows'])), flush=True)

json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('[out] %d 条 -> %s' % (len(res), OUT), flush=True)

mins = sorted(min(r['rows']) for r in res if r['rows'])
if mins:
    qq = lambda p: mins[int(p * (len(mins) - 1))]
    print('[stat] 段间最低相似度  min %.3f  p05 %.3f  p10 %.3f  中位 %.3f  max %.3f' % (
        mins[0], qq(.05), qq(.1), qq(.5), mins[-1]))
    print('[judge] <0.55 报警 %d 条 | <0.45 严重 %d 条' % (
        sum(1 for x in mins if x < 0.55), sum(1 for x in mins if x < 0.45)))
    print('  worst 10:', [(r['unit'], round(min(r['rows']), 3)) for r in
                          sorted(res, key=lambda r: min(r['rows']))[:10]])
