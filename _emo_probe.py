# -*- coding: utf-8 -*-
import json, os, sys
sys.path.insert(0, "G:/_setup"); sys.path.insert(0, "G:/_setup/emo_bench")
import soundfile as sf
import dialog_gate as DG
import ser as S

st = DG.load_ref_stats()
e2v = S.E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large")
vox = S.VoxDim()

CASES = [
    ("c3_0875", "警惕", "wary", "_ref_try/c3_0875_Thomas_wary_2.wav"),
    ("c2_0468", "激动反抗", "defiant", "_ref_try/c2_0468_Thomas_defiant_2.wav"),
    ("c2_0264", "兴奋", "excited", "_ref_try/c2_0264_Thomas_excited_2.wav"),
    ("c2_0265", "激动反抗", "angry", "_ref_try/c2_0265_Charles_angry_2.wav"),
]
for sid, emo, refemo, w in CASES:
    if not os.path.exists(w):
        print(sid, "缺"); continue
    d = sf.info(w).duration
    r, v, notes = DG.gate_emotion(w, emo, st, vox, e2v=e2v, ref_emo=refemo, dur=d)
    print("%-8s %-6s ref=%-8s -> %-6s %s" % (sid, emo, refemo, v, (r or {}).get("note") or ""))
    if r:
        print("         ", {k: r.get(k) for k in ("signal", "value", "p25", "p10", "tier", "top", "A", "V", "D") if k in r})
    for c, w2 in notes:
        print("          note:", c, w2[:80])
