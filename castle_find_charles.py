#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从切好的 cue 里找出「Charles 本人 + 高效价（开心/兴奋）」的片段。

两步：
  1. 声纹：与 Charles 锚点（castle_fr_ref 的 charles 系列）比相似度，同时跟 Hooper 锚点比，
     取更接近 Charles 的。CAM++ 对短片段不稳，所以取 max(与任一 Charles 锚点的相似度)。
  2. 之后由 score_real.py 跑 vox_dim 看效价 V。

输出 castle_cues_charles.json，按 V 排序。
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/voice_lib")
import spk_embed as SE

HERE = "G:/_setup"
REF = os.path.join(HERE, "castle_fr_ref")
C_ANCH = ["1_charles_normal.wav", "2_charles_soft.wav", "3_charles_excited.wav", "4_charles_angry.wav"]
H_ANCH = ["5_hooper_loud.wav", "6_hooper_calm.wav", "6b_hooper_scold.wav", "7_hooper_begging.wav"]


def main():
    cues = json.load(open(os.path.join(HERE, "castle_cues_index.json"), encoding="utf-8"))
    print("总 cue %d" % len(cues), flush=True)

    C = [SE.embed_file(os.path.join(REF, f)) for f in C_ANCH if os.path.exists(os.path.join(REF, f))]
    H = [SE.embed_file(os.path.join(REF, f)) for f in H_ANCH if os.path.exists(os.path.join(REF, f))]
    # 锚点内部一致性（自检）
    print("Charles 锚点互比 min=%.3f" % min(SE.cos(a, b) for i, a in enumerate(C) for b in C[i + 1:]))
    print("Hooper  锚点互比 min=%.3f" % min(SE.cos(a, b) for i, a in enumerate(H) for b in H[i + 1:]))
    print("跨角色           max=%.3f" % max(SE.cos(a, b) for a in C for b in H), flush=True)

    rows = []
    for i, c in enumerate(cues):
        try:
            e = SE.embed_file(c["path"], max_sec=12.0)
        except Exception:
            continue
        sc = max(SE.cos(e, a) for a in C)
        sh = max(SE.cos(e, a) for a in H)
        rows.append(dict(c, sim_charles=round(float(sc), 4), sim_hooper=round(float(sh), 4),
                         margin=round(float(sc - sh), 4)))
        if (i + 1) % 50 == 0:
            print("  %d/%d" % (i + 1, len(cues)), flush=True)

    json.dump(rows, open(os.path.join(HERE, "castle_cues_spk.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    isc = [r["sim_charles"] for r in rows]
    print()
    print("sim_charles: p10=%.3f p50=%.3f p90=%.3f" % tuple(np.percentile(isc, [10, 50, 90])))
    n = sum(1 for r in rows if r["sim_charles"] >= 0.55 and r["margin"] > 0)
    print("判为 Charles 的 cue：%d / %d" % (n, len(rows)))


if __name__ == "__main__":
    main()
