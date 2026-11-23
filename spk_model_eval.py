#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""比较声纹模型在「两个童声」上的可分性。

用 8 个已知角色的锚点（4 Charles / 4 Hooper）两两算余弦相似度：
  类内（同角色）= 应该高
  类间（跨角色）= 应该低
判据：separation = 类内最小 − 类间最大，> 0 才算能分开。
"""
import os, sys, json, itertools
import numpy as np

REF = "G:/_setup/castle_fr_ref16"
C = ["1_charles_normal.wav", "2_charles_soft.wav", "3_charles_excited.wav", "4_charles_angry.wav"]
H = ["5_hooper_loud.wav", "6_hooper_calm.wav", "6b_hooper_scold.wav", "7_hooper_begging.wav"]
import os
MODEL = os.environ.get("SPK_MODEL", "G:/_setup/models/ms/iic/speech_eres2netv2_sv_zh-cn_16k-common")


def eval_vectors(vecs, tag):
    """vecs: {name: (emb, role)}"""
    intra, inter = [], []
    names = list(vecs)
    for a, b in itertools.combinations(names, 2):
        ea, ra = vecs[a]
        eb, rb = vecs[b]
        s = float(np.dot(ea, eb) / (np.linalg.norm(ea) * np.linalg.norm(eb)))
        (intra if ra == rb else inter).append((s, a, b))
    iv = [x[0] for x in intra]
    er = [x[0] for x in inter]
    print("%-14s 类内 min=%.3f 中位=%.3f | 类间 max=%.3f 中位=%.3f | 分离度=%+.3f" % (
        tag, min(iv), float(np.median(iv)), max(er), float(np.median(er)), min(iv) - max(er)))
    worst = max(inter, key=lambda x: x[0])
    print("                 最像的一对跨角色：%s vs %s = %.3f" % (worst[1][:22], worst[2][:22], worst[0]))
    return min(iv) - max(er)


def main():
    sys.path.insert(0, "G:/_setup/emo_bench")
    from modelscope.pipelines import pipeline
    from modelscope.utils.constant import Tasks

    print("加载", os.path.basename(MODEL), flush=True)
    sv = pipeline(task=Tasks.speaker_verification, model=MODEL)

    files = [(f, "C") for f in C] + [(f, "H") for f in H]
    vecs = {}
    for f, role in files:
        p = os.path.join(REF, f)
        if not os.path.exists(p):
            continue
        out = sv([p, p])          # 同一文件对，只为拿 embedding
        emb = out.get("embeddings")
        if emb is None:
            print("no embeddings, keys:", list(out)); return
        vecs[f] = (np.asarray(emb[0], dtype=float), role)
    print("embedding 维度", len(next(iter(vecs.values()))[0]))
    sep = eval_vectors(vecs, "ERes2NetV2")
    json.dump({k: v[0].tolist() for k, v in vecs.items()},
              open("G:/_setup/_emb_eres2netv2.json", "w"), ensure_ascii=False)
    print("\n结论：%s" % ("能分开（分离度 > 0）" if sep > 0 else "分不开（分离度 <= 0）"))


if __name__ == "__main__":
    main()
