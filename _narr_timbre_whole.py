# -*- coding: utf-8 -*-
"""_narr_timbre_whole.py —— 旁白 716 整条声纹稳定性（含跨章漂移）

★ 为什么不用 ch123_segcheck 的句内切段口径（2026-11-14 实测否定）：
  旁白单段常 0.3~1.0s，循环补长到 2s 后 CAM++ 失去区分力：
  within(同句内) 中位 0.432 vs between(不同句) 中位 0.450，差 -0.018 ⇒ 纯噪声。
  相似度几乎只由段长决定（0.6-0.8s 段 < 0.55 占 100%，>=2s 段只占 9%）。

★ 现行口径：整条 2~21s 直接提嵌入（不切段不补长）。
  零分布（16 条抽 120 对）：中位 0.741 / p10 0.616 / min 0.454；<0.55 占 3%。
  验收：cos >= 0.65 可接受，>= 0.70 更好；< 0.55 报警。

输出：_narr_spk.json
"""
import os, sys, json
import numpy as np

sys.path.insert(0, 'G:/_setup')
import ch123_segcheck as CS

AUD = 'G:/_setup/_audio_ch123/out'
LIST = 'G:/_setup/_narr_check4/_narr_check.json'
OUT = 'G:/_setup/_narr_spk.json'
TMP = 'G:/_setup/_segchk_whole'
MIN_RELIABLE = 2.0

units = [x['unit'] for x in json.load(open(LIST, encoding='utf-8'))]
os.makedirs(TMP, exist_ok=True)

res = []
if os.path.exists(OUT):
    try:
        res = json.load(open(OUT, encoding='utf-8'))
    except Exception:
        res = []
done = {r['unit'] for r in res}
print('[in] %d units, 已有 %d' % (len(units), len(done)), flush=True)

for k, u in enumerate(units, 1):
    if u in done:
        continue
    p = os.path.join(AUD, u + '.wav')
    if not os.path.exists(p):
        continue
    try:
        a, sr = CS.read_wav(p)
        dur = len(a) / sr
        fp = os.path.join(TMP, u + '.wav')
        CS.write_wav(fp, a, sr)
        e = CS.SPK.embed(fp)
        res.append(dict(unit=u, dur=round(dur, 2), ch=u[1],
                        emb=[round(float(x), 5) for x in e]))
    except Exception as ex:
        print('  %s ERR %s' % (u, ex), flush=True)
        continue
    if k % 50 == 0:
        json.dump(res, open(OUT, 'w', encoding='utf-8'))
        print('  %d/%d' % (k, len(units)), flush=True)

json.dump(res, open(OUT, 'w', encoding='utf-8'))
print('[out] %d -> %s' % (len(res), OUT), flush=True)

# ---- 统计 ----
rel = [r for r in res if r['dur'] >= MIN_RELIABLE]
short = [r for r in res if r['dur'] < MIN_RELIABLE]
print('[split] 可靠(>=%.1fs) %d 条 | 太短 %d 条' % (MIN_RELIABLE, len(rel), len(short)))

E = np.array([r['emb'] for r in rel])
E = E / np.linalg.norm(E, axis=1, keepdims=True)
chs = np.array([r['ch'] for r in rel])

cent = {}
for c in sorted(set(chs)):
    cent[c] = E[chs == c].mean(0)
    cent[c] /= np.linalg.norm(cent[c])
print('\n[章] 样本数', {c: int((chs == c).sum()) for c in sorted(set(chs))})
for c in sorted(set(chs)):
    v = E[chs == c] @ cent[c]
    print('  ch%s: 与本中中心 cos 中位 %.3f  p05 %.3f' % (c, np.median(v), np.percentile(v, 5)))

# 全体中心（全库当成同一 voice）
gl = E.mean(0); gl /= np.linalg.norm(gl)
cos_all = E @ gl
print('\n[全库] cos 中位 %.3f  p05 %.3f  p01 %.3f  min %.3f' % (
    np.median(cos_all), np.percentile(cos_all, 5), np.percentile(cos_all, 1), cos_all.min()))
print('[判据] <0.65 %d 条 | <0.55 %d 条' % ((cos_all < .65).sum(), (cos_all < .55).sum()))

idx = np.argsort(cos_all)
print('\n最差 15:')
for i in idx[:15]:
    r = rel[i]
    print('  %-9s %.2fs cos=%.3f' % (r['unit'], r['dur'], cos_all[i]))

for r, c in zip(rel, cos_all):
    r['cos_global'] = round(float(c), 4)
    r['cos_chapter'] = None
    r['emb'] = None
json.dump(res, open('G:/_setup/_narr_spk_stats.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('\n明细 -> _narr_spk_stats.json')
