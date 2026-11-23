# -*- coding: utf-8 -*-
"""c2_0312 音色归属对比：当前交付（nervous_2 参考）vs 用户自带参考（c185）候选。

只回答一个问题：换成 c185 之后，这条还算不算「同一个 Charles」。
参照系三个：Charles 角色中心、nervous_2 档中心、neutral_1 档中心。
"""
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
import _utt_verify as UV

HERE = "G:/_setup"
AUD = os.path.join(HERE, "_audio_ch123", "out_paused")
PLAN = os.path.join(HERE, "_dlg_plan_v2_paused.jsonl")


def nrm(v):
    return v / (np.linalg.norm(v) + 1e-9)


def main():
    z = np.load(os.path.join(HERE, "_utt_emb", "r34.npz"), allow_pickle=True)
    ids, whos, E = list(z["ids"]), list(z["whos"]), z["embs"]
    E = np.array([nrm(e) for e in E])
    ix = {k: i for i, k in enumerate(ids)}

    plan = {}
    for line in open(PLAN, encoding="utf-8"):
        if line.strip():
            o = json.loads(line)
            plan[o["id"]] = o

    role_i = [i for i, k in enumerate(ids) if whos[i] == "Charles"]
    role_c = nrm(E[role_i].mean(0))
    tier_i = {v: [ix[k] for k in ids if plan.get(k, {}).get("voice") == v] for v in
              ("Charles_nervous_2", "Charles_neutral_1", "Charles_neutral_4")}
    tier_c = {v: nrm(E[idx].mean(0)) for v, idx in tier_i.items() if idx}

    print("索引 n=%d，Charles %d" % (len(ids), len(role_i)))
    for v, idx in tier_i.items():
        print("  档 %-20s %d 句" % (v, len(idx)))

    model = UV.M("r34")

    def rep(name, path):
        v = nrm(UV.utt_emb(model, path))
        s = "%-24s vs Charles 中心 %.3f" % (name, float(v @ role_c))
        for k, c in tier_c.items():
            s += "  | %s %.3f" % (k.replace("Charles_", ""), float(v @ c))
        print(s)

    rep("当前交付(nervous_2)", os.path.join(AUD, "c2_0312.wav"))
    for p in sorted(glob.glob(os.path.join(HERE, "_sweep", "cand45", "*.wav"))):
        rep(os.path.basename(p)[:-4], p)


if __name__ == "__main__":
    main()
