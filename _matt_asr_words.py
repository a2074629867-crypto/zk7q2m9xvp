# -*- coding: utf-8 -*-
"""转写马修母带，拿可靠的词级时间戳（whisper small.en word_timestamps）。"""
import json, sys, time
sys.path.insert(0, r'G:/_setup')
from transplant_prosody2 import word_times

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
OUT = r'G:/_setup/_matt_asr_words.json'

t0 = time.time()
ws = word_times(MASTER)
print('转写完成 %d 词，耗时 %.1f 分钟' % (len(ws), (time.time() - t0) / 60), flush=True)
# 存
json.dump([[round(a, 3), round(b, 3), w] for a, b, w in ws],
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('写出', OUT, flush=True)
# 抽查连续性
print('\n抽查第 200~215 词：')
print(' '.join(w for _, _, w in ws[200:216]))
print('\n抽查第 1200~1215 词：')
print(' '.join(w for _, _, w in ws[1200:1216]))
gaps = [ws[i+1][0] - ws[i][1] for i in range(len(ws)-1)]
import numpy as np
g = np.array(gaps)
print('\n间隙 p50 %.3f p90 %.3f max %.2f  <0 的 %d' % (
    np.median(g), np.percentile(g, 90), g.max(), (g < 0).sum()))
print('间隙 >=0.10 的 %d 处，>=0.60 的 %d 处' % ((g >= 0.10).sum(), (g >= 0.60).sum()))
