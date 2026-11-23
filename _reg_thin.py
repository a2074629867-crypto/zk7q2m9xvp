# -*- coding: utf-8 -*-
"""_reg_thin.py —— 给 5 个薄档各补 2 条本片 48k 参考，把「单条参考」变成「三条」。

为什么（2026-11-13 实测）：
  薄档只有 1 条参考 ⇒ 生成端只能撞运气。Thomas_defiant_1 换档后声纹降级
  （Charles 余弦上升、cen gap 0.185→0.042，r7 的 c1_0052/c2_0468 因此被拒）；
  警惕档同参考不同 seed 可从 0.9996 掉到 0.0004（双峰）。
  补到 3 条后可以「同句多参考择优」，而不是死磕单条 + 加 seed。

挑选标准（_pick_thin.py 跑出来，三条同时满足）：
  ① 声纹 cos 与角色交付音频质心 ≥0.45  ② 主信号（闸在用的）≥ 该情绪 p25  ③ MOS ≥2.0
  全部来自 **castle_cues 本片 48k 切片**（不是外片 16k 素材）。

写 voice_lib 前逐条查存在性（铁律：11-13 曾覆盖 Thomas_wary_1.wav）。
"""
import json, os, shutil, soundfile as sf

HERE = "G:/_setup"
LIB = os.path.join(HERE, "_emo_refs_all.json")
VL = os.path.join(HERE, "_cloud_backup/voice_lib")

# (role, emo, cid, 主信号说明)
JOBS = [
    ("Thomas", "wary",    "c287_p1", "disgusted 0.9205 / MOS 4.06 / cos 0.622"),
    ("Thomas", "wary",    "c289_p0", "disgusted 0.9566 / MOS 3.83 / cos 0.577"),
    ("Thomas", "defiant", "c217_p0", "vox:d 0.7221 / MOS 2.69 / cos 0.709"),
    ("Thomas", "defiant", "c216_p0", "vox:d 0.7911 / MOS 2.61 / cos 0.691"),
    ("Thomas", "wronged", "c006_p1", "neg_a 0.8520 / MOS 2.98 / cos 0.569"),
    ("Thomas", "wronged", "c300_p0", "neg_a 0.8154 / MOS 3.27 / cos 0.554"),
    ("Charles", "wary",   "c290_p0", "disgusted 0.8985 / MOS 3.78 / cos 0.642"),
    ("Charles", "wary",   "c209_p1", "disgusted 0.6970 / MOS 4.00 / cos 0.457"),
    ("Charles", "wronged", "c028_p0", "neg_a 0.8579 / MOS 3.15 / cos 0.529"),
    ("Charles", "wronged", "c268_p0", "neg_a 0.7829 / MOS 3.46 / cos 0.566"),
]

meas = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"), encoding="utf-8"))}
lib = json.load(open(LIB, encoding="utf-8"))

for role, emo, cid, why in JOBS:
    src = os.path.join(HERE, "_refs_new/cand", cid + ".wav")
    if not os.path.exists(src):
        print("✗ 源缺 %s" % cid)
        continue
    m = meas[cid]
    items = lib.setdefault(role, {}).setdefault(emo, [])
    idx = len(items) + 1
    name = "%s_%s_%d" % (role, emo, idx)
    dst = os.path.join(VL, name + ".wav")
    if os.path.exists(dst):                       # 冲突改名，绝不覆盖
        k = idx
        while os.path.exists(dst):
            k += 1
            name = "%s_%s_%d" % (role, emo, k)
            dst = os.path.join(VL, name + ".wav")
        idx = k
    shutil.copy2(src, dst)
    info = sf.info(dst)
    if info.samplerate != 48000:
        raise SystemExit("采样率不是 48k：%s" % dst)
    items.append({
        "path": "G:/_setup/_cloud_backup/voice_lib/%s.wav" % name,
        "text": m["text"], "f0": round(m["f0"], 1),
        "src": "castle_cues_48k(%s)" % cid, "mos": round(m["mos"], 2),
        "note": why,
    })
    print("%-9s %-9s #%d %-22s %5.2fs MOS %.2f  %s" % (role, emo, idx, name, info.duration, m["mos"], why))

json.dump(lib, open(LIB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n已写 _emo_refs_all.json")
for role, emo in sorted({(r, e) for r, e, _, _ in JOBS}):
    print("  %-9s %-9s %d 条" % (role, emo, len(lib[role][emo])))
