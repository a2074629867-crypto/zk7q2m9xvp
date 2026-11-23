"""先测基线：TTS 生成音频 vs 角色参考音的声纹余弦，确定严格阈值。

为什么要先测基线：生成音频是合成的，声纹余弦天然低于真人之间的余弦。
直接套用「≥0.65」会把正常条全判废。必须先看同角色/跨角色的实际分布。
"""
import json, os, sys, random
import numpy as np

sys.path.insert(0, "G:/_setup")
from sv_onnx import SV

PLAN = "_castle_en_ch123_plan.jsonl"
OUT = "_audio_ch123/out"
LIB = "_emo_refs_all.json"

rows = {}
for line in open(PLAN, encoding="utf-8"):
    r = json.loads(line)
    rows[r["id"]] = r

lib = json.load(open(LIB, encoding="utf-8"))

# 每个角色取参考音质心
def role_centroid(role, m):
    vecs = []
    for emo, lst in lib.get(role, {}).items():
        for it in lst:
            p = it["path"]
            if os.path.exists(p):
                vecs.append(m.embed(p))
    if not vecs:
        return None
    c = np.mean(vecs, 0)
    return c / (np.linalg.norm(c) + 1e-9)

m = SV("r34")
cent = {}
for role in ("Charles", "Joseph", "Helena", "Thomas", "Fielding"):
    c = role_centroid(role, m)
    if c is not None:
        cent[role] = c
print("角色质心:", list(cent))

# 抽样：每个 speaker 取 8 条
random.seed(11)
byspk = {}
for rid, r in rows.items():
    byspk.setdefault(r.get("speaker"), []).append(rid)

for spk, ids in sorted(byspk.items()):
    if spk == "narrator":
        continue
    pick = random.sample(ids, min(8, len(ids)))
    print("\n=== %s (n=%d) ===" % (spk, len(ids)))
    for rid in pick:
        p = os.path.join(OUT, rid + ".wav")
        if not os.path.exists(p):
            continue
        e = m.embed(p)
        sims = {k: float(e @ v) for k, v in cent.items()}
        best = max(sims, key=sims.get)
        own = sims.get(spk)
        other = max((v for k, v in sims.items() if k != spk), default=0)
        print("  %-9s own=%.3f  best=%s %.3f  gap=%+.3f" % (
            rid, own if own is not None else -1, best, sims[best],
            (own - other) if own is not None else -9))
