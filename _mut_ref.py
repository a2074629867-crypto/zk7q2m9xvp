# -*- coding: utf-8 -*-
"""_mut_ref.py —— 用「角色归属翻转」判音色突变（相比段间互比的改进方案）。

动机（都是实测出来的，不是猜的）：
  `_mutbench` 上段间余弦几乎无判别力 —— NEG_emo（**同一角色**两条不同句拼接）
  的最小左右余弦 p50 0.724，反而比 POS_hard（**换人**）的 0.700 还低。
  即「两段不像」在这套 TTS 语料上不能推出「换人」，人内方差太大。

所以改用归属判据：每段 embedding 与**角色参考库**逐档取最大余弦 → top-1 属于谁。
  换人 ⇒ top-1 翻转；同人情绪变化 ⇒ top-1 不变（即使余弦也低）。

score(t) = 左右两段 top-1 不同 时，取「双向证据」的最小值
           min( s(L,a)-s(L,b), s(R,b)-s(R,a) )
         = 左右都很确信自己属于不同的人，才算数；否则 0。
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/_setup")
from _mut_all import MODELS, M, to16, cos, nrm

B = "G:/_setup/_mutbench"
REFS = "G:/_setup/refs_cast"


def build_refs(model):
    out = {}
    for f in sorted(os.listdir(REFS)):
        if not f.endswith(".wav"):
            continue
        who = f.split("_")[0]
        e = M(model).emb_f(_feat(model, os.path.join(REFS, f)))
        out.setdefault(who, []).append(e)
    return {k: np.stack(v) for k, v in out.items()}


_F = {}


def _feat(model, path):
    from _mut_all import fbank
    key = (model, path)
    if key not in _F:
        _F[key] = fbank(to16(path), MODELS[model][1])
    return _F[key]


def score_who(e, refs):
    """emb -> (top1, s_top1, s_second)"""
    sc = {w: float(np.max(R @ e)) for w, R in refs.items()}
    order = sorted(sc.items(), key=lambda x: -x[1])
    if len(order) < 2:
        return order[0][0], order[0][1], 0.0
    return order[0][0], order[0][1], order[1][1]


def main(model, half=2.0, step=0.25):
    refs = build_refs(model)
    print("参考库:", {k: len(v) for k, v in refs.items()})
    idx = {x["sid"]: x for x in json.load(open(B + "/index.json", encoding="utf-8"))}
    cd = os.path.join(B, "emb", model)
    out = {}
    for sid, it in idx.items():
        z = np.load(os.path.join(cd, sid + ".npz"))
        c, E = z["centers"], z["embs"]
        best, bt, info = 0.0, None, None
        t = 1.2
        while t <= c.max() - 0.6:
            L = E[(c >= t - half) & (c <= t - 0.18)]
            R = E[(c >= t + 0.18) & (c <= t + half)]
            if len(L) >= 2 and len(R) >= 2:
                a, sa, sa2 = score_who(nrm(L.mean(0)), refs)
                b, sb, sb2 = score_who(nrm(R.mean(0)), refs)
                if a != b:
                    s = min(sa - sa2, sb - sb2)
                    if s > best:
                        best, bt, info = s, t, (a, b, round(sa, 3), round(sb, 3))
            t += step
        out[sid] = {"score": round(best, 4), "pos": bt, "info": info}
    json.dump(out, open(B + "/ref_%s.json" % model, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 分组统计
    def g(k):
        return [(s, out[s]["score"]) for s in out if idx[s]["kind"] == k]
    for k in ("POS_hard", "POS_soft", "NEG_emo", "NEG_real"):
        v = [x[1] for x in g(k)]
        print("  %-9s n=%3d  score p10 %.3f p50 %.3f p90 %.3f  命中(>0) %d"
              % (k, len(v), *np.percentile(v, [10, 50, 90]), sum(1 for x in v if x > 0)))
    # 定位
    err = [abs(out[s]["pos"] - idx[s]["cut"]) for s in out
           if idx[s]["kind"] == "POS_hard" and out[s]["score"] > 0]
    if err:
        print("  POS_hard 定位误差 MAE %.2fs  ≤0.75s 命中 %.0f%%" % (np.mean(err), np.mean([e <= 0.75 for e in err]) * 100))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "campp_en")
