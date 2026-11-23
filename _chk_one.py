import sys, json, numpy as np, soundfile as sf
sys.path.insert(0, "G:/_setup")
from chain_check import SV
lib = json.load(open("_emo_refs_all.json", encoding="utf-8"))
m = SV("r34")
def cos(a, b): return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
cen = np.mean([m.embed(it["path"]) for items in lib["Charles"].values()
               for it in items if "self-cut" not in it.get("src", "")], axis=0)
for p in ["_regen_r3_out/c2_0265.wav", "_audio_ch123/out/c2_0265.wav"]:
    e = m.embed(p)
    print("%-42s 声纹vs质心 %.3f  时长 %.2fs" % (p, cos(e, cen), sf.info(p).duration), flush=True)
