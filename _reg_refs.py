# -*- coding: utf-8 -*-
"""把 A/B 验证过的 48k 新参考登记进 voice_lib 与 _emo_refs_all.json。
   Charles/nervous: c030_p0 -> Charles_nervous_2   (A/B: 1.55 -> 2.20/2.82，e2v 生气->恐惧)
   Charles/angry  : c068_p1 -> Charles_angry_2     (A/B: 1.50 -> 3.21/3.47，声纹 0.325 -> 0.608)
"""
import json, os, shutil, soundfile as sf

HERE = "G:/_setup"
LIB = os.path.join(HERE, "_emo_refs_all.json")
VL = os.path.join(HERE, "_cloud_backup/voice_lib")
meas = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"), encoding="utf-8"))}

JOBS = [("Charles", "nervous", "c030_p0"), ("Charles", "angry", "c068_p1")]
lib = json.load(open(LIB, encoding="utf-8"))
for role, emo, cid in JOBS:
    src = os.path.join(HERE, "_refs_new/cand", cid + ".wav")
    idx = len(lib[role][emo]) + 1
    name = "%s_%s_%d" % (role, emo, idx)
    dst = os.path.join(VL, name + ".wav")
    shutil.copy2(src, dst)
    it = {
        "path": "G:/_setup/_cloud_backup/voice_lib/%s.wav" % name,
        "text": meas[cid]["text"],
        "f0": round(meas[cid]["f0"], 1),
        "src": "refs_new_48k(%s)" % cid,
        "mos": round(meas[cid]["mos"], 2),
    }
    lib[role][emo].append(it)
    print("%-10s %-8s 追加 idx=%d  %s  MOS %.2f  %.2fs  %dHz" % (
        role, emo, idx, name, it["mos"], meas[cid]["dur"], sf.info(dst).samplerate))
json.dump(lib, open(LIB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n_emo_refs_all.json 已更新")
for role, emo, _ in JOBS:
    print("  %s/%s -> %s" % (role, emo, [os.path.basename(x["path"]) for x in lib[role][emo]]))
