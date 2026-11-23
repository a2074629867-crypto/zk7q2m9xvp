# -*- coding: utf-8 -*-
"""候选声纹体检：候选音频不在 r34 索引里，`gate_scs.check` 一律回 scs_short（dur=0.0），
等于**候选从来没验过音色** —— 而换参考最可能改的就是音色（MEMORY 里 Thomas_begging_1
换完直接变 Charles）。这个脚本补这一环：

对每个候选算
  vs现役   = cos(候选, 交付里的同名文件)
  vs档中心 = cos(候选, 该 voice 档的中心)
  vs档min  = 与档内（>=2s）各条的最小 cos
判据沿用交付侧口径：vs档min >= 0.65 才算「还是同一个人」。

用法：
  python _cand_scs.py --ids c1_0034,c2_0437 --cand _sweep/cand10n
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

AUD = os.path.join(HERE, "_audio_ch123", "out")
PLAN = os.path.join(HERE, "_dlg_plan_v2.jsonl")
EMB = os.path.join(HERE, "_utt_emb", "%s.npz")
MIN_DUR = 2.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--model", default="r34")
    ap.add_argument("--min-cos", type=float, default=0.65)
    a = ap.parse_args()

    import soundfile as sf
    import _utt_verify as UV

    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l)
            plan[o["id"]] = o

    z = np.load(EMB % a.model, allow_pickle=True)
    ids, E = list(z["ids"]), z["embs"]
    E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
    ix = {k: i for i, k in enumerate(ids)}
    dur = {}
    for k in ids:
        try:
            dur[k] = sf.info(os.path.join(AUD, k + ".wav")).duration
        except Exception:  # noqa: BLE001
            dur[k] = 0.0

    model = UV.M(a.model)
    rows = []
    for rid in [x.strip() for x in a.ids.split(",") if x.strip()]:
        voice = plan[rid]["voice"]
        tier = [k for k in ids if plan[k]["voice"] == voice and dur.get(k, 0) >= MIN_DUR]
        tc = E[[ix[k] for k in tier]].mean(0)
        tc /= np.linalg.norm(tc) + 1e-9
        v0 = UV.utt_emb(model, os.path.join(AUD, rid + ".wav"))
        v0 /= np.linalg.norm(v0) + 1e-9
        print("== %s  档=%s（>=2s 共 %d 句）" % (rid, voice, len(tier)))
        print("   现役 vs档中心 %.3f  vs档min %.3f"
              % (float(tc @ v0), float(min(E[ix[k]] @ v0 for k in tier)) if tier else float("nan")))
        for p in sorted(glob.glob(os.path.join(a.cand, "%s__s*.wav" % rid))):
            v = UV.utt_emb(model, p)
            v /= np.linalg.norm(v) + 1e-9
            c_tc = float(tc @ v)
            c_min = float(min(E[ix[k]] @ v for k in tier)) if tier else float("nan")
            c_now = float(v0 @ v)
            ok = c_min >= a.min_cos
            print("   %-18s vs现役 %.3f  vs档中心 %.3f  vs档min %.3f  %s"
                  % (os.path.basename(p)[:-4], c_now, c_tc, c_min,
                     "OK" if ok else "★ 音色漂（<%.2f）" % a.min_cos))
            rows.append(dict(id=rid, seed=os.path.basename(p).rsplit("__s", 1)[1][:-4],
                             vs_now=c_now, vs_tier_c=c_tc, vs_tier_min=c_min, ok=ok))
    out = os.path.join(HERE, "_sweep", "cand_scs_%s.json" % os.path.basename(a.cand.rstrip("/\\")))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
