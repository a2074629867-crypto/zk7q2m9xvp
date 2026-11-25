# -*- coding: utf-8 -*-
import json
import numpy as np

d = json.load(open("G:/_setup/_noise_stats2.json", encoding="utf-8"))["dlg_out"]
rows = [(k, v) for k, v in d.items() if "floor_q" in v]
clean = [(k, v) for k, v in rows if v["zero_ms"] <= 10]
zero = [(k, v) for k, v in rows if v["zero_ms"] > 10]
print("总 %d | 含数字零 %d | 干净 %d" % (len(rows), len(zero), len(clean)))

fq = [v["floor_q"] for k, v in clean]
print("干净条 floor_q: min %.1f p10 %.1f p50 %.1f p90 %.1f max %.1f"
      % (np.min(fq), np.percentile(fq, 10), np.median(fq),
         np.percentile(fq, 90), np.max(fq)))
for t in (-65, -60, -55, -50, -45):
    n = sum(1 for x in fq if x > t)
    print("  floor_q > %d : %3d 条 (%.0f%%)" % (t, n, 100.0 * n / len(fq)))

sq = [v["snr_q"] for k, v in clean]
print("干净条 snr_q: min %.1f p10 %.1f p50 %.1f"
      % (np.min(sq), np.percentile(sq, 10), np.median(sq)))
print("  snr_q < 35: %d 条 | < 30: %d 条"
      % (sum(1 for x in sq if x < 35), sum(1 for x in sq if x < 30)))

old = json.load(open("G:/_setup/_noise_stats.json", encoding="utf-8"))
print()
print("旧口径(p10) 判 floor > -60 : %d 条" % sum(1 for v in old.values() if v["floor"] > -60))
print("新口径(静音帧) 同阈值      : %d 条"
      % sum(1 for k, v in rows if v["floor_q"] > -60 and v["zero_ms"] <= 10))
print("旧口径 判 SNR < 25         : %d 条" % sum(1 for v in old.values() if v["snr"] < 25))

# 数字零组的底噪
zq = [v["floor_q"] for k, v in zero]
print()
print("含数字零的 %d 条，其静音帧底噪 p50 %.1f（去掉零帧后）"
      % (len(zero), np.median([v["floor_p1"] for k, v in zero])))
