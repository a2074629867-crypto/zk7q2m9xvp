import sys, json, os, glob
import numpy as np, soundfile as sf, parselmouth
sys.path.insert(0, "G:/_setup"); sys.path.insert(0, "G:/_setup/emo_bench")
from _mut_all import M, to16, fbank
import _nat_guard as NG
import ser as S

def nrm(v): return v / (np.linalg.norm(v) + 1e-9)
m = M("r34")
z = np.load("_utt_emb/r34.npz"); whos = list(z["whos"]); E = z["embs"]
cen = {w: nrm(E[[i for i, x in enumerate(whos) if x == w]].mean(0)) for w in ("Charles", "Thomas", "Joseph", "Helena")}
e2v = S.E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large")

def f0(p):
    s = parselmouth.Sound(p); pit = s.to_pitch(0.01, 60, 500)
    v = pit.selected_array["frequency"]; v = v[v > 0]
    return float(np.median(v)) if len(v) else 0

for sid, who in (("c2_0246", "Charles"), ("c1_0020", "Thomas")):
    print("=== %s (%s) ===" % (sid, who))
    print("%-5s %6s %6s %8s %8s %8s %-12s %6s" % ("变体", "时长", "F0", "vs本角色", "vs另一人", "MOS", "e2v", "概率"))
    for tag in ("old", "n48", "n16"):
        p = "_ab_out/%s_%s.wav" % (sid, tag)
        if not os.path.exists(p):
            print("%-5s 缺" % tag); continue
        e = nrm(m.emb_f(fbank(to16(p), m.cmn)))
        other = "Thomas" if who == "Charles" else "Charles"
        r = NG.raw(p)
        sc = e2v.score(p); tp = sc.get("_top")
        print("%-5s %6.2f %6.0f %8.3f %8.3f %8.2f %-12s %6.2f" % (
            tag, sf.info(p).duration, f0(p), float(e @ cen[who]), float(e @ cen[other]),
            r.get("nq_mos") or 0, (tp or "-")[:12], sc.get(tp, 0)), flush=True)
    print()
