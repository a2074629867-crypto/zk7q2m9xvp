# -*- coding: utf-8 -*-
"""_utt_verify.py —— 说话人验证基线：这套 TTS 语料上哪个 embedding 模型更可靠。

不依赖拼接基准，只看最基础的能力：
  同角色两条不同句（intra）应当比 跨角色（inter）更像。
  用 AUC / EER / d' 量化，同时报告 intra 余弦中位数（越高说明人内方差越小、
  越适合做「句内一致性」判据）。

用法：
  G:/Python310/python.exe _utt_verify.py campp_en
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/_setup")
from _mut_all import MODELS, M, to16, fbank

AUD = "G:/_setup/_audio_ch123/out"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
OUT = "G:/_setup/_utt_emb"
SR = 16000
CHUNK, HOP = 6.0, 3.0


def utt_emb(m, path):
    a = to16(path)
    f = fbank(a, m.cmn)
    T = f.shape[0]
    cf, hf = int(CHUNK * 100), int(HOP * 100)
    spans = []
    if T <= cf:
        spans = [(0, T)]
    else:
        s = 0
        while s + cf <= T:
            spans.append((s, s + cf)); s += hf
        if spans[-1][1] < T:
            spans.append((T - cf, T))
    embs = []
    for s, e in spans:
        seg = a[int(s * 0.01 * SR):int(e * 0.01 * SR)]
        if len(seg) and float(np.sqrt(np.mean(seg ** 2))) < 1e-4:
            continue
        embs.append(m.emb_f(f[s:e]))
    if not embs:
        embs = [m.emb_f(f)]
    v = np.mean(np.stack(embs), axis=0)
    return v / (np.linalg.norm(v) + 1e-9)


def main(model):
    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, model + ".npz")
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l); plan[o["id"]] = o
    ids, whos, embs = [], [], []
    m = M(model)
    if os.path.exists(dst):
        z = np.load(dst, allow_pickle=True)
        ids, whos, embs = list(z["ids"]), list(z["whos"]), list(z["embs"])
        print("已有缓存 %d 条" % len(ids))
    else:
        for k, (i, o) in enumerate(sorted(plan.items()), 1):
            p = os.path.join(AUD, i + ".wav")
            if not os.path.exists(p):
                continue
            ids.append(i); whos.append(o["who"]); embs.append(utt_emb(m, p))
            if k % 60 == 0:
                print("  %s %d/%d" % (model, k, len(plan)), flush=True)
        np.savez(dst, ids=np.array(ids), whos=np.array(whos), embs=np.stack(embs))
    E = np.stack(embs)
    W = np.array(whos)
    S = E @ E.T
    iu = np.triu_indices(len(E), 1)
    same = (W[:, None] == W[None, :])[iu]
    s = S[iu]
    intra, inter = s[same], s[~same]
    # AUC：intra 排在 inter 前面的概率
    allv = np.concatenate([intra, inter])
    r = allv.argsort().argsort() + 1
    auc = (r[:len(intra)].sum() - len(intra) * (len(intra) + 1) / 2) / (len(intra) * len(inter))
    d = (intra.mean() - inter.mean()) / np.sqrt(0.5 * (intra.var() + inter.var()) + 1e-12)
    # EER
    ths = np.unique(np.concatenate([intra, inter]))
    best = (1.0, 0)
    for t in ths[::max(1, len(ths) // 400)]:
        far = (inter >= t).mean()
        frr = (intra < t).mean()
        if abs(far - frr) < best[0]:
            best = (abs(far - frr), (far + frr) / 2)
    print("%-9s n=%d | intra p50 %.3f (p10 %.3f) | inter p50 %.3f (p90 %.3f) | AUC %.4f | d' %.2f | EER %.2f%%"
          % (model, len(E), np.median(intra), np.percentile(intra, 10),
             np.median(inter), np.percentile(inter, 90), auc, d, best[1] * 100))
    return dict(model=model, n=len(E), intra=float(np.median(intra)),
                intra_p10=float(np.percentile(intra, 10)),
                inter=float(np.median(inter)), auc=float(auc), d=float(d), eer=float(best[1]))


if __name__ == "__main__":
    res = [main(x) for x in sys.argv[1:]] or [main("campp_en")]
    json.dump(res, open(os.path.join(OUT, "verify.json"), "w", encoding="utf-8"), indent=1)
