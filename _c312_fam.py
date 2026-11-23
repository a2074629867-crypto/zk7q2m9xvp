# -*- coding: utf-8 -*-
"""Charles 的两个参考来源家族有多像：
  A 家族 = castle_cues/*.wav（用户早期自己从片子里切的 16k 段）
  B 家族 = _cloud_backup/voice_lib/*.wav（48k 干净档）
输出族内/族间 cos，回答「换参考到底换了多少音色」。
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
import _utt_verify as UV

HERE = "G:/_setup"


def nrm(v):
    return v / (np.linalg.norm(v) + 1e-9)


def main():
    z = np.load(os.path.join(HERE, "_utt_emb", "r34.npz"), allow_pickle=True)
    ids, whos, E = list(z["ids"]), list(z["whos"]), z["embs"]
    E = np.array([nrm(e) for e in E])
    plan = {}
    for line in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8"):
        if line.strip():
            o = json.loads(line)
            plan[o["id"]] = o
    lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))

    def ref_of(voice):
        head, n = voice.rsplit("_", 1)
        role, _, emo = head.partition("_")
        items = (lib.get(role) or {}).get(emo) or []
        try:
            return items[int(n) - 1]["path"]
        except Exception:
            return ""

    fam = {"castle_cues": [], "voice_lib": []}
    for i, k in enumerate(ids):
        if whos[i] != "Charles":
            continue
        p = ref_of(plan.get(k, {}).get("voice", "")).replace("\\", "/")
        if "castle_cues" in p:
            fam["castle_cues"].append(i)
        elif "voice_lib" in p:
            fam["voice_lib"].append(i)
    cs = {f: nrm(E[v].mean(0)) for f, v in fam.items() if v}
    for f, v in fam.items():
        if not v:
            continue
        intra = [float(E[a] @ E[b]) for a in v for b in v if a != b]
        print("%-12s %2d 句  族内 cos 中位 %.3f" % (f, len(v), float(np.median(intra)) if intra else 0))
    cross = [float(E[a] @ E[b]) for a in fam["castle_cues"] for b in fam["voice_lib"]]
    if cross:
        print("族间 cos 中位 %.3f  p10 %.3f  min %.3f" % (float(np.median(cross)),
                                                     float(np.percentile(cross, 10)), float(min(cross))))
    print("族心互 cos %.3f" % float(cs["castle_cues"] @ cs["voice_lib"]))


if __name__ == "__main__":
    main()
