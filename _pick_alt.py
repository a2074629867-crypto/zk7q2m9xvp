# -*- coding: utf-8 -*-
"""_pick_alt.py —— 给配角（Joseph / Helena）从**本片 393 段**里挑参考，替掉外片 16k 素材。

为什么（2026-11-13 18:25 核实）：
  参考库里 Joseph 6 档、Helena 5 档、Fielding 5 档，`src` 全部是
  `Hope Gap 2019` / `Another Year 2010` / `Son of Rambow 2007` —— **外片演员**，
  而且都是 16k。而本片明明有 Joseph 59 段、Helena 42 段、Fielding 5 段 48k 切片没用上。
  Joseph 一个人就有 53 条对白，全用外片音色。

挑选标准同 _pick_thin.py：声纹 cos ≥0.45 ∧ 主信号 ≥p25（或 p10 备选）∧ MOS ≥2.0。

用法：python _pick_alt.py Joseph 平静 紧张 激动反抗
      python _pick_alt.py Helena 平静 紧张
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
from _mut_all import M
from _utt_verify import utt_emb

HERE = "G:/_setup"
SIG = {"平静": ("vox", "v"), "紧张": ("vox", "a"), "激动反抗": ("vox", "d"),
       "委屈": ("vox", "neg_a"), "兴奋": ("vox", "a_x_v"), "警惕": ("e2v", "厌恶/disgusted")}
MIN_COS, MIN_MOS = 0.45, 2.0


def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法：_pick_alt.py <角色> <情绪> [情绪...]")
    role, emos = sys.argv[1], sys.argv[2:]

    import ser as S
    import verdict as V
    import dialog_gate as DG
    stats = DG.load_ref_stats()
    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))
    VOX = S.VoxDim()

    rows = json.load(open(os.path.join(HERE, "_refs_new/meas.json"), encoding="utf-8"))
    cand = [r for r in rows if r.get("role") == role]
    print("本片候选 %d 段" % len(cand))

    mp = M("r34")
    emb_p = os.path.join(HERE, "_refs_new/thin_emb.npz")
    z = np.load(emb_p, allow_pickle=True)
    cids_all, vecs_all = z["cids"].tolist(), z["vecs"]
    idx_of = {c: k for k, c in enumerate(cids_all)}

    # ★ 质心必须用「本片段自己的质心」，不能用交付音频质心。
    #   2026-11-13 实测：Joseph/Helena 的交付音频是**外片演员**生成的，
    #   拿它当质心会把本片素材全部排斥（Joseph 最高 cos 仅 0.367 ⇒ 0 条候选）。
    #   本片 59 段自比中位 0.699、50 段 cos≥0.5 ⇒ 素材本身很干净。
    Vs = []
    for r in cand:
        if r["cid"] in idx_of:
            v = vecs_all[idx_of[r["cid"]]]
            Vs.append(v / (np.linalg.norm(v) + 1e-9))
    Vs = np.stack(Vs)
    c0 = Vs.mean(0)
    c0 /= np.linalg.norm(c0)
    core = Vs[Vs @ c0 >= 0.5]
    c = core.mean(0)
    cent = c / (np.linalg.norm(c) + 1e-9)
    sc_all = Vs @ cent
    print("本片段质心：%d 段参与，核心 %d 段（cos≥0.5），cos 中位 %.3f"
          % (len(Vs), len(core), float(np.median(sc_all))))
    # 交付音频与本片素材是否同源（同源应 >0.5；Joseph/Helena 实测只有 0.21）
    d = np.load(os.path.join(HERE, "_utt_emb/r34.npz"), allow_pickle=True)
    whos, embs = d["whos"], d["embs"]
    vv = embs[whos == role]
    if len(vv):
        vv = vv / (np.linalg.norm(vv, axis=1, keepdims=True) + 1e-9)
        cc = vv.mean(0)
        cc /= np.linalg.norm(cc)
        print("⚠ 交付音频与本片素材 cos = %.3f（<0.4 说明现役参考不是本片音色）\n"
              % float(cc @ cent))
    else:
        print("")

    out = {}
    for emo in emos:
        kind, key = SIG[emo]
        st = stats[emo]["signals"]["%s:%s" % (kind, key)]["pos"]
        p10, p25 = st["p10"], st["p25"]
        scored = []
        for r in cand:
            cid = r["cid"]
            if cid not in idx_of:
                continue
            vv = vecs_all[idx_of[cid]]
            vv = vv / (np.linalg.norm(vv) + 1e-9)
            cos = float(vv @ cent)
            if cos < MIN_COS or (r.get("mos") or 0) < MIN_MOS:
                continue
            p = os.path.join(HERE, "_refs_new/cand", cid + ".wav")
            if not os.path.exists(p):
                continue
            if kind == "e2v":
                val = float((e2v.score(p) or {}).get(key, 0))
            else:
                try:
                    val = float(V.vox_feat(VOX.score(p) or {}, key))
                except Exception:
                    val = 0.0
            scored.append(dict(cid=cid, cos=round(cos, 3), val=round(val, 4),
                               mos=round(r.get("mos") or 0, 2),
                               dur=round(r.get("dur") or 0, 2), text=r.get("text", "")))
        ok = sorted([x for x in scored if x["val"] >= p25],
                    key=lambda x: (-x["cos"], -x["mos"]))
        mid = sorted([x for x in scored if p10 <= x["val"] < p25],
                     key=lambda x: (-x["cos"], -x["mos"]))
        print("== %s/%s  %s:%s  p10 %.3f / p25 %.3f  达 p25 %d 条" % (
            role, emo, kind, key, p10, p25, len(ok)))
        for x in (ok + mid)[:4]:
            print("     %-10s cos %.3f  %.4f  MOS %.2f  %.1fs  %s" % (
                x["cid"], x["cos"], x["val"], x["mos"], x["dur"], x["text"][:50]))
        out[emo] = dict(sig="%s:%s" % (kind, key), p10=p10, p25=p25, picks=(ok + mid)[:3])
        print()

    json.dump(out, open(os.path.join(HERE, "_alt_picks_%s.json" % role), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已写 _alt_picks_%s.json" % role)


if __name__ == "__main__":
    main()
