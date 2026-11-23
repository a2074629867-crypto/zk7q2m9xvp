# -*- coding: utf-8 -*-
"""逐条在 s42 / s1234 里挑更好的 take，输出替换清单。

判据（优先级）：
  1. ASR 覆盖率差 > 0.10 → 要覆盖率高的
  2. 时长/词 偏离该 seed 中位 > 40% → 要更接近的
  3. 其余保持当前（s1234，RDR 更好）
"""
import json, os, sys
sys.path.insert(0, "D:/py_libs")
import numpy as np, soundfile as sf

A = json.load(open("_asr_cov_s42.json", encoding="utf-8"))
B = json.load(open("_asr_cov_s1234.json", encoding="utf-8"))
S = json.load(open("_mt_loop_state.json", encoding="utf-8"))["units"]

def spw(d, seed):
    out = {}
    for u in d:
        p = "_mt_trim_ch1_s%s/%s.wav" % (seed, u)
        if not os.path.exists(p): continue
        i = sf.info(p)
        out[u] = i.frames / i.samplerate / max(1, d[u]["n"])
    return out

sa, sb = spw(A, "42"), spw(B, "1234")
ma, mb = np.median(list(sa.values())), np.median(list(sb.values()))
print("秒/词 中位：s42 %.3f  s1234 %.3f" % (ma, mb))

swap, keep = [], []
for u in sorted(set(A) & set(B)):
    ca, cb = A[u]["cov"], B[u]["cov"]
    da = abs(sa.get(u, ma) / ma - 1)
    db = abs(sb.get(u, mb) / mb - 1)
    reason = None
    if ca - cb > 0.10:
        reason = "ASR s42 更好 %.2f vs %.2f" % (ca, cb)
    elif db > 0.40 and da < 0.25:
        reason = "s1234 时长异常 %+.0f%%" % (100 * (sb.get(u, mb) / mb - 1))
    if reason:
        swap.append(dict(uid=u, reason=reason, cov_a=ca, cov_b=cb,
                         spw_a=round(sa.get(u, ma), 3), spw_b=round(sb.get(u, mb), 3)))
    else:
        keep.append(u)

print("\n建议换成 s42 的 %d 条：" % len(swap))
for s in swap:
    print("  %-6s %-34s cov %.2f→%.2f  s/词 %.2f→%.2f"
          % (s["uid"], s["reason"], s["cov_b"], s["cov_a"], s["spw_b"], s["spw_a"]))
print("\n保持 s1234 的 %d 条" % len(keep))
json.dump(swap, open("_pick_swap.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
