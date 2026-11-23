# -*- coding: utf-8 -*-
"""登记 r6 换档用的新参考（只登记 _ref_try 验证过的）。

  Thomas/wary    <- c286_p2  (MOS 4.25, e2v 厌恶, "Ils te mettront avec moi...")
     验证 c3_0875：MOS 3.45->3.97，自然度 0.21σ->0.65σ，声纹 0.641->0.644
  Thomas/defiant <- c301_p0  (MOS 3.13, e2v 生气, "Mesdames et messieurs...")
     验证 c2_0468：情绪闸 从 ref_fallback(MANUAL) -> **PASS** d=0.6947≥p25 0.6239
  Thomas/excited **不登记**：换 c314_p0 实测 a_x_v 0.180 更差，属生成层上限（见 EMO_UNREACHABLE）
"""
import json, os, shutil, soundfile as sf

HERE = "G:/_setup"
LIB = os.path.join(HERE, "_emo_refs_all.json")
VL = os.path.join(HERE, "_cloud_backup/voice_lib")
meas = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"), encoding="utf-8"))}

JOBS = [("Thomas", "wary", "c286_p2"), ("Thomas", "defiant", "c301_p0")]
lib = json.load(open(LIB, encoding="utf-8"))
for role, emo, cid in JOBS:
    src = os.path.join(HERE, "_refs_new/cand", cid + ".wav")
    idx = len(lib.setdefault(role, {}).setdefault(emo, [])) + 1
    name = "%s_%s_%d" % (role, emo, idx)
    dst = os.path.join(VL, name + ".wav")
    shutil.copy2(src, dst)
    it = {"path": "G:/_setup/_cloud_backup/voice_lib/%s.wav" % name,
          "text": meas[cid]["text"], "f0": round(meas[cid]["f0"], 1),
          "src": "refs_new_48k(%s)" % cid, "mos": round(meas[cid]["mos"], 2)}
    lib[role][emo].append(it)
    print("%-8s %-8s idx=%d  %-20s MOS %.2f  %.2fs  %dHz" % (
        role, emo, idx, name, it["mos"], meas[cid]["dur"], sf.info(dst).samplerate))
json.dump(lib, open(LIB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n已写 _emo_refs_all.json")
for role, emo, _ in JOBS:
    print("  %s/%s -> %s" % (role, emo, [os.path.basename(x["path"]) for x in lib[role][emo]]))
