# -*- coding: utf-8 -*-
"""_cond_check.py —— 就截图表里那 7 行的前置条件做全量实测（865 条交付版）。

只回答一个问题：**这些 when 条件在真实素材上，是不是真的成立。**
不重跑判定逻辑，只量「条件本身」。
"""
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
sys.path.insert(0, ROOT)

from mt_detectors import (crest_db, cut_drop_guarded, span_st_robust,  # noqa: E402
                          spectral)


def one(p):
    x, sr = sf.read(p, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    dur = len(x) / sr
    d = dict(name=os.path.basename(p)[:-4], dur=round(dur, 2),
             crest=crest_db(x))
    d["span_st"] = span_st_robust(x, sr)
    s = spectral(x, sr)
    d.update(cent=s["cent"], tilt=s["tilt"], flat=s["flat"], hf=s["hf"])
    # 气声：后 40% 帧（弱能量段）的平坦度，用来验证「只取前 40% 会漏」
    import librosa
    S = np.abs(librosa.stft(x, n_fft=1024, hop_length=256))
    P = np.maximum(S ** 2, 1e-20)
    tot = P.sum(0)
    hi_m = tot >= np.quantile(tot, 0.60)
    lo_m = tot <= np.quantile(tot, 0.40)
    def fl(m):
        if m.sum() < 3:
            return None
        return float(np.median(np.exp(np.mean(np.log(P[:, m]), 0)) / np.mean(P[:, m], 0)))
    d["flat_hi"] = round(fl(hi_m) or 0, 4)
    d["flat_lo"] = round(fl(lo_m) or 0, 4)
    cd, pdb, tdb = cut_drop_guarded(x, sr)
    d["cut_drop"], d["cut_prev"] = cd, pdb
    return d


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "_mt_pick", "*.wav")))
    out = []
    for i, f in enumerate(files):
        try:
            out.append(one(f))
        except Exception as e:  # noqa: BLE001
            out.append(dict(name=os.path.basename(f)[:-4], err=str(e)[:80]))
        if (i + 1) % 50 == 0:
            print("  %d/%d" % (i + 1, len(files)), flush=True)
    json.dump(out, open(os.path.join(ROOT, "_cond_check.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)
    print("done", len(out))


if __name__ == "__main__":
    main()
