# -*- coding: utf-8 -*-
"""登记 Thomas/excited 新档 —— c292_p0（原片 48k 切片，不是 loud 替代）。

背景（2026-11-13 18:xx，用户明确要求「绝对不能用 loud 代替」）：
  现役 loud 参考 c218 的 a_x_v 仅 0.287，且 valence 只有 0.35（"凶"不是"兴奋"），
  产物 a_x_v 掉到 0.169，五条兴奋对白全判未达。

三轮 A/B 置换（试句 c2_0491，现役 a_x_v 0.169）：
  c312_p0 0.187 / c216_p0 0.178 / c093_p0 0.191 / c207_p0 0.217 / **c292_p0 0.251**
  c292_p0 参考自身 a_x_v 0.401、valence 0.53、MOS 3.57，是 Thomas 133 段里
  「高唤醒 + 正效价 + 音质可听」交集最好的一条；产物 0.251 > p10 0.247（勉强档），
  MOS 3.78 > 现役 2.81。

传递比实测 0.45~0.63（参考 a_x_v → 产物 a_x_v），故 p25 0.3745 需参考 ~0.60，
Thomas 全片最高只有 0.422 ⇒ p25 仍不可达，但 p10 可达，判「勉强」而非「未达」。
"""
import json, os, shutil, soundfile as sf

HERE = "G:/_setup"
LIB = os.path.join(HERE, "_emo_refs_all.json")
VL = os.path.join(HERE, "_cloud_backup/voice_lib")
CID = "c292_p0"

meas = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"), encoding="utf-8"))}
pick = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_excited_pick.json"), encoding="utf-8"))}
m, p = meas[CID], pick[CID]

lib = json.load(open(LIB, encoding="utf-8"))
have = (lib.get("Thomas") or {}).get("excited") or []
name = "Thomas_excited_%d" % (len(have) + 1)
dst = os.path.join(VL, name + ".wav")
# 铁律：写 voice_lib 前必须查存在性（11-13 曾覆盖 Thomas_wary_1.wav）
if os.path.exists(dst):
    raise SystemExit("目标已存在，拒绝覆盖：%s" % dst)

shutil.copy2(os.path.join(HERE, "_refs_new/cand", CID + ".wav"), dst)
info = sf.info(dst)
item = {
    "path": "G:/_setup/_cloud_backup/voice_lib/%s.wav" % name,
    "text": m["text"],
    "f0": round(m["f0"], 1),
    "src": "refs_new_48k(%s)" % CID,
    "mos": round(m["mos"], 2),
    "a_x_v": round(p["a_x_v"], 3),
    "note": "兴奋档：高唤醒+正效价，非 loud 替代",
}
lib.setdefault("Thomas", {}).setdefault("excited", []).append(item)
json.dump(lib, open(LIB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("登记 %-18s %dHz %.2fs MOS %.2f a_x_v %.3f" % (name, info.samplerate, info.duration, m["mos"], p["a_x_v"]))
print("文本 %s" % m["text"][:70])
print("Thomas/excited -> %s" % [os.path.basename(x["path"]) for x in lib["Thomas"]["excited"]])
