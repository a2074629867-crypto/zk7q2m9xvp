# -*- coding: utf-8 -*-
"""fair_score.py —— 量一下「合并多角色库」为什么掉分，并试更公平的打分规则。

背景
----
五角色库（Charles 10 / Thomas 15 / Fielding 15 / Helena 15 / Joseph 15）回放 59 条法语片
真值：PASS 38→17、准确率 86.4%→47.5%。而四角色版（34 模板）只掉 3 个点。
差别就是「模板多的角色更容易赢」——1-NN 取 max，谁的模板多谁占便宜。

这里对比四种规则（都用同一批 embedding，排除其他变量）：
  1nn        max(cos)                     现行
  top2mean   每角色取前 2 高的均值
  top3mean   每角色取前 3 高的均值
  zrole      每角色内的 cos 先做 z-score 再取 max（消除角色内的尺度差）
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")

ROLE = {"C": "Charles", "E": "Thomas", "Charles": "Charles", "Thomas": "Thomas"}


def load_lib(p, sv):
    d = json.load(open(p, encoding="utf-8"))
    keys, paths = [], []
    for role, slots in d.items():
        for slot, items in slots.items():
            for it in items:
                q = it["path"] if isinstance(it, dict) else it
                if os.path.exists(q):
                    keys.append((role, slot))
                    paths.append(q)
    E = np.array([sv.embed(q) for q in paths], dtype=np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    return E, np.array([k[0] for k in keys])


def scores(E, roles, e):
    s = E @ e
    out = {}
    for r in np.unique(roles):
        v = np.sort(s[roles == r])[::-1]
        out[r] = v
    return out


def rule_scores(s, mode):
    res = {}
    for r, v in s.items():
        if mode == "1nn":
            res[r] = float(v[0])
        elif mode == "top2mean":
            res[r] = float(v[:2].mean())
        elif mode == "top3mean":
            res[r] = float(v[:3].mean())
        elif mode == "zrole":
            res[r] = float((v[0] - v.mean()) / (v.std() + 1e-9))
    return res


def main():
    manifest = json.load(open("G:/_setup/_ch123_final.json", encoding="utf-8"))
    items = [(k, v) for k, v in manifest.items() if v.get("who") in ROLE]
    wavs = []
    for k, v in items:
        p = os.path.join("G:/_setup/ch123_final", k + ".wav")
        if os.path.exists(p):
            wavs.append((p, ROLE[v["who"]]))
    print("测试样本 %d 条" % len(wavs), flush=True)

    from sv_onnx import SV
    sv = SV(name="r34")

    libs = {"2角色(25)": "_emo_refs.json", "5角色(70)": "_emo_refs_all.json"}
    emb = {}
    for p, t in wavs:
        emb[p] = sv.embed(p)

    for name, lp in libs.items():
        E, roles = load_lib(lp, sv)
        print("\n=== %s  %d 条模板" % (name, len(roles)))
        for mode in ("1nn", "top2mean", "top3mean", "zrole"):
            ok = bad = 0
            confuse = {}
            for p, t in wavs:
                e = emb[p]
                e = e / (np.linalg.norm(e) + 1e-9)
                r = rule_scores(scores(E, roles, e), mode)
                top = max(r, key=r.get)          # 全角色 argmax，不搞排除法
                ok += top == t
                if top != t:
                    bad += 1
                    confuse[(t, top)] = confuse.get((t, top), 0) + 1
            print("  %-9s 准确率 %d/%d = %.1f%%  错判去向 %s" % (
                mode, ok, len(wavs), 100.0 * ok / len(wavs),
                confuse if confuse else "-"))


if __name__ == "__main__":
    main()
