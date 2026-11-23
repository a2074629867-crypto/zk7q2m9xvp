# -*- coding: utf-8 -*-
"""_pick_thin.py —— 给「只有 1 条参考」的薄档补第 2、3 条候选（从原片 393 段里挑）。

为什么必须补（2026-11-13 18:xx 实测）：
  薄档 = Thomas/wary、Thomas/defiant、Thomas/wronged、Charles/wary、Charles/wronged。
  r6/r7 里 Thomas_defiant_1 换档后 **声纹降级**（Charles 余弦上升、cen gap 0.185→0.042），
  r7 的 c1_0052 / c2_0468 都因此被拒。单条参考 = 没有分布，生成端只能撞运气。

挑选标准（三条都要，缺一不可）：
  1. 声纹 cos 与**该角色交付音频质心** ≥ 0.45（保证是同一个人，不能换个更差的）
  2. 主信号（闸在用的那个，不是语义猜的）≥ 该情绪 p25；不够则 ≥ p10 备选
  3. NISQA MOS ≥ 2.0（音质可听，否则参考会把噪声带进去）

输出 `_thin_picks.json`，不写 voice_lib（登记另走 _reg_thin.py）。
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
from _mut_all import M, MODELS
from _utt_verify import utt_emb

HERE = "G:/_setup"
TARGETS = [
    ("Thomas", "wary", "e2v:厌恶/disgusted"),
    ("Thomas", "defiant", "vox:d"),
    ("Thomas", "wronged", "vox:neg_a"),
    ("Charles", "wary", "e2v:厌恶/disgusted"),
    ("Charles", "wronged", "vox:neg_a"),
]
MIN_COS, MIN_MOS = 0.45, 2.0

# --- 角色质心：用交付音频的 r34 向量（验证过的那份）---
d = np.load(os.path.join(HERE, "_utt_emb/r34.npz"), allow_pickle=True)
ids, whos, embs = d["ids"], d["whos"], d["embs"]
cent = {}
for who in set(whos.tolist()):
    v = embs[whos == who]
    v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
    c = v.mean(0)
    cent[who] = c / (np.linalg.norm(c) + 1e-9)
print("角色质心：%s" % ", ".join("%s(%d)" % (k, int((whos == k).sum())) for k in sorted(cent)))

# --- 阈值 ---
import dialog_gate as DG
stats = DG.load_ref_stats()
p10, p25 = {}, {}
for _, emo_en, sig in TARGETS:
    zh = {"wary": "警惕", "defiant": "激动反抗", "wronged": "委屈"}[emo_en]
    s = stats[zh]["signals"][sig]
    p10[(emo_en, sig)] = s["pos"]["p10"]
    p25[(emo_en, sig)] = s["pos"]["p25"]
    print("%-9s %-20s p10 %.3f  p25 %.3f" % (emo_en, sig, s["pos"]["p10"], s["pos"]["p25"]))

# --- 候选池 ---
meas = json.load(open(os.path.join(HERE, "_refs_new/meas2.json"), encoding="utf-8")) \
    if os.path.exists(os.path.join(HERE, "_refs_new/meas2.json")) \
    else json.load(open(os.path.join(HERE, "_refs_new/meas.json"), encoding="utf-8"))
rows = meas if isinstance(meas, list) else list(meas.values())
print("候选池 %d 段" % len(rows))

# 主信号要靠 ser/vox 现算，候选里只有 e2v 标签与 eprob，故先按 e2v 粗筛再实测
import ser as S
import verdict as V
e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))
VOX = S.VoxDim()
VFAIL = [0]


def feat(path):
    """返回 {e2v: {...}, vox: 维度原始分}。

    ★ vox_feat 的签名是 (sc, key)，不是 (path)。必须先用 VoxDim().score 出维度分。
    异常不再静默吞：计数并打印，否则整批会被判成 0 而看不出是代码错。
    """
    out = {"e2v": e2v.score(path) or {}, "vox": {}}
    try:
        out["vox"] = VOX.score(path) or {}
    except Exception as e:
        VFAIL[0] += 1
        if VFAIL[0] <= 3:
            print("  ! vox 失败 %s: %s: %s" % (os.path.basename(path), type(e).__name__, e))
    return out


ONLY = set(sys.argv[1:])


def main():
    mp = M("r34")
    cache_p = os.path.join(HERE, "_refs_new/thin_emb.npz")
    if os.path.exists(cache_p):
        z = np.load(cache_p, allow_pickle=True)
        cids, vecs = z["cids"].tolist(), z["vecs"]
    else:
        cids, vecs = [], []
        for k, r in enumerate(rows, 1):
            p = os.path.join(HERE, "_refs_new/cand", r["cid"] + ".wav")
            if not os.path.exists(p):
                continue
            try:
                cids.append(r["cid"]); vecs.append(utt_emb(mp, p))
            except Exception:
                pass
            if k % 50 == 0:
                print("  向量 %d/%d" % (k, len(rows)), flush=True)
        vecs = np.stack(vecs)
        np.savez(cache_p, cids=np.array(cids), vecs=vecs)
        print("已缓存 %d 段向量 → %s" % (len(cids), cache_p))

    by_cid = {r["cid"]: r for r in rows}
    picked = {}
    for role, emo_en, sig in TARGETS:
        if ONLY and emo_en not in ONLY:
            continue
        cand = [r for r in rows if r.get("role") == role]
        print("\n== %s/%s  候选 %d 段，主信号 %s" % (role, emo_en, len(cand), sig))
        scored = []
        for r in cand:
            if r["cid"] not in by_cid:
                continue
            idx = cids.index(r["cid"]) if r["cid"] in cids else -1
            if idx < 0:
                continue
            v = vecs[idx] / (np.linalg.norm(vecs[idx]) + 1e-9)
            cos = float(v @ cent[role])
            if cos < MIN_COS or (r.get("mos") or 0) < MIN_MOS:
                continue
            p = os.path.join(HERE, "_refs_new/cand", r["cid"] + ".wav")
            f = feat(p)
            if sig.startswith("e2v:"):
                val = float(f["e2v"].get(sig[4:], 0))
            else:
                try:
                    val = float(V.vox_feat(f["vox"], sig[4:]))
                except Exception:
                    val = 0.0
            scored.append(dict(cid=r["cid"], cos=round(cos, 3), val=round(val, 4),
                               mos=round(r.get("mos") or 0, 2), f0=round(r.get("f0") or 0, 1),
                               dur=round(r.get("dur") or 0, 2), e2v=r.get("text") and f["e2v"].get("_top"),
                               text=r.get("text", "")))
        key = (emo_en, sig)
        ok = [x for x in scored if x["val"] >= p25[key]]
        mid = [x for x in scored if p10[key] <= x["val"] < p25[key]]
        ok.sort(key=lambda x: (-x["val"], -x["cos"]))
        mid.sort(key=lambda x: (-x["cos"], -x["mos"]))
        print("   达 p25 %d 条 / p10~p25 %d 条" % (len(ok), len(mid)))
        for x in (ok + mid)[:6]:
            print("     %-10s cos %.3f  %s %.4f  MOS %.2f  %.1fs  %-12s %s" % (
                x["cid"], x["cos"], sig, x["val"], x["mos"], x["dur"], x["e2v"] or "-", x["text"][:44]))
        picked["%s/%s" % (role, emo_en)] = dict(sig=sig, p10=p10[key], p25=p25[key],
                                                picks=(ok + mid)[:2])
    out_p = os.path.join(HERE, "_thin_picks.json")
    old = json.load(open(out_p, encoding="utf-8")) if os.path.exists(out_p) else {}
    old.update(picked)
    json.dump(old, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nvox 失败 %d 次" % VFAIL[0])
    print("\n已写 _thin_picks.json")


if __name__ == "__main__":
    main()
