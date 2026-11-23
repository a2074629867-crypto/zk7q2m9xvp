# -*- coding: utf-8 -*-
"""_pick_r15.py —— r15 专用择优：**先修音色突变，再比情绪/MOS**

为什么不能直接用 `_cloud_pick.py`：那套是「情绪主信号 ≥p10/p25 里取 MOS 最高」，
本次目标是修**音色突变**（路2 标点后换音区 / 路3 句内声道突变），
情绪分高但音色突变更重的候选会被误选。

择优顺序（硬闸不满足直接淘汰）：
  0) 硬闸：削波 / MOS≥2.0 / cos≥0.55 / 时长语速（沿用 _cloud_pick 同口径）
  1) **路3**：候选 drift(profile=dlg) 不能是 FAIL（原条是 FAIL 时必须变成非 FAIL）
  2) **路2**：候选的跨停顿跳变命中数必须 < 原条命中数
  3) 在通过 1+2 的候选里：优先 tier 高（情绪），再比 MOS
  4) 没有任何候选通过 ⇒ 保留原文件（不写 OUT），如实记 `keep`

输入 `_cand_r15/cand/<id>__<voice>__s<seed>.wav`
输出 `_regen_r15_out/<id>.wav`（胜者，已归一 −24dBFS）
     `_regen_r15_pick.json`（回填清单：id/role/emo/voice/seed）
     `_r15_pick_log.json`（完整台账，含每条候选的三路与情绪明细）
"""
import glob
import json
import os
import re
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
from norm_dlg import vdb, soft_clip  # noqa: E402

HERE = "G:/_setup"
CAND = os.path.join(HERE, "_cand_r15/cand")
NORM = os.path.join(HERE, "_cand_r15/norm")
OUT = os.path.join(HERE, "_regen_r15_out")
DELIV = os.path.join(HERE, "_audio_ch123/out")
TARGET, PEAK_MAX = -24.0, 0.891
ST2, CEN2 = 6.0, 1.30

PRIMARY = {"警惕": ("e2v", "厌恶/disgusted"), "激动反抗": ("vox", "d"),
           "委屈": ("vox", "neg_a"), "兴奋": ("vox", "a_x_v"),
           "平静": ("vox", "a_x_v"), "紧张": ("vox", "neg_a")}


def normalize(src, dst):
    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    r0 = vdb(y, sr)
    g = TARGET - r0 if r0 > -60 else 0.0
    g = max(-12.0, min(12.0, g))
    y = y * (10 ** (g / 20.0))
    if float(np.abs(y).max()) > PEAK_MAX:
        y = soft_clip(y, PEAK_MAX)
    sf.write(dst, y.astype(np.float32), sr, subtype="PCM_16")
    return round(float(vdb(y, sr)), 2), round(float(np.abs(y).max()), 3)


def same_audio(p1, p2, thr=0.999):
    """两文件是否同一次生成。

    ★ 2026-11-14 21:5x 教训：同文本同参考同 seed 是**确定性输出**（DECISIONS 已记），
    用现役那条的 seed 重跑，拿回来的就是同一个音频 —— 波形相关 1.000000，
    情绪/MOS/cos 全一致，却被「路3 从 FAIL 变 PASS」的边界抖动骗成「修复」。
    所以必须显式判重，重复候选一律作废。
    """
    try:
        a, _ = sf.read(p1, dtype="float32")
        b, _ = sf.read(p2, dtype="float32")
    except Exception:
        return False
    n = min(len(a), len(b))
    if n < 1000:
        return False
    if abs(len(a) - len(b)) > 0.02 * max(len(a), len(b)):
        return False
    try:
        r = float(np.corrcoef(a[:n], b[:n])[0, 1])
    except Exception:
        return False
    return r > thr


def road23(p):
    """对一条音频算 路2 命中数 与 路3 是否 FAIL（口径同 gate_timbre_seq）"""
    import mt_seg_drift as D
    r = D.one(p, profile="dlg")
    r2 = []
    for pr in (r.get("pairs") or []):
        gap, dst, dcen = pr.get("gap") or 0, pr.get("dst"), pr.get("dcen")
        if gap < 2 or dst is None or not dcen:
            continue
        ratio = max(dcen, 1.0 / dcen)
        if abs(dst) >= ST2 and ratio >= CEN2:
            r2.append(dict(t=round(float(pr["t"]), 2), delta_st=round(float(dst), 2),
                           cen_ratio=round(float(ratio), 2)))
    r3 = None
    if r.get("verdict") == "FAIL":
        ev = [e for e in (r.get("events") or []) if e.get("level") == "FAIL"]
        if ev:
            r3 = dict(t=round(float(ev[0]["t"]), 2), why="/".join(ev[0].get("why") or []))
    return dict(r2=r2, r3=r3, verdict=r.get("verdict"), dur=round(r.get("dur") or 0, 2))


def main():
    os.makedirs(NORM, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
    files = glob.glob(os.path.join(CAND, "*.wav"))
    by = {}
    for p in files:
        m = re.match(r"(.+?)__(.+?)__s(\d+)\.wav$", os.path.basename(p))
        if m:
            by.setdefault(m.group(1), []).append((m.group(2), int(m.group(3)), p))
    print("候选 %d 个，覆盖 %d 条" % (len(files), len(by)), flush=True)

    import ser as S
    import verdict as V
    import dialog_gate as DG
    import _nat_guard as NG
    from _mut_all import M
    from _utt_verify import utt_emb

    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))
    VOX = S.VoxDim()
    stats = DG.load_ref_stats()
    spk = M("r34")
    d = np.load(os.path.join(HERE, "_utt_emb/r34.npz"), allow_pickle=True)
    whos, embs = d["whos"], d["embs"]
    cent = {}
    for who in set(whos.tolist()):
        v = embs[whos == who]
        v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
        c = v.mean(0)
        cent[who] = c / (np.linalg.norm(c) + 1e-9)

    rows = []
    for i in sorted(by):
        p0 = plan[i]
        who, emo = p0["who"], p0["emo"]
        kind, key = PRIMARY.get(emo, ("vox", "a_x_v"))
        sig = "%s:%s" % (kind, key)
        try:
            p10 = stats[emo]["signals"][sig]["pos"]["p10"]
            p25 = stats[emo]["signals"][sig]["pos"]["p25"]
        except KeyError:
            p10, p25 = 0.0, 0.0
        cur = os.path.join(DELIV, i + ".wav")
        d_old = sf.info(cur).duration if os.path.exists(cur) else 0
        wc = len([k for k in (p0.get("text") or "").split() if any(c.isalpha() for c in k)])

        # 原条的三路基线（用 gate_timbre_seq 口径，避免两套实现）
        import gate_timbre_seq as TS
        TS.load()
        c0 = TS.check(i)
        base2 = len(c0["r2"])
        base3 = bool(c0["r3"])

        scored = []
        cands = [("cur", cur)] + [("%s_s%d" % (v, s), p) for v, s, p in sorted(by[i])]
        cur_norm = None
        for tag, p in cands:
            npth = os.path.join(NORM, "%s__%s.wav" % (i, tag))
            rms1, pk = normalize(p, npth)
            if tag == "cur":
                cur_norm = npth
            sc = e2v.score(npth) or {}
            vs = VOX.score(npth) or {}
            val = float(sc.get(key, 0)) if kind == "e2v" else float(V.vox_feat(vs, key) or 0)
            vv = utt_emb(spk, npth)
            vv = vv / (np.linalg.norm(vv) + 1e-9)
            cos = float(vv @ cent.get(who, vv))
            dur = sf.info(npth).duration
            mos = 0.0
            if dur >= 1.0:
                try:
                    mos = float((NG.raw(npth) or {}).get("nq_mos") or 0)
                except Exception:
                    mos = 0.0
            bad = []
            if tag != "cur" and cur_norm and same_audio(npth, cur_norm):
                bad.append("重复现役")
            if pk >= 0.999:
                bad.append("削波")
            if mos < 2.0:
                bad.append("MOS%.2f" % mos)
            if cos < 0.55:
                bad.append("cos%.2f" % cos)
            if d_old > 0:
                ratio = dur / d_old
                wpm = wc / dur * 60 if dur > 0 else 0
                if wc <= 9:
                    if ratio < 0.75:
                        bad.append("短句变短x%.2f" % ratio)
                    elif ratio > 1.40 and wpm < 120:
                        bad.append("短句变长%.0fwpm" % wpm)
                elif not (90 <= wpm <= 260):
                    bad.append("%.0fwpm" % wpm)
            # ★ 音色突变两路（候选是独立文件，必须自己跑 drift）
            if tag == "cur":
                rr = dict(r2=c0["r2"], r3=c0["r3"], verdict=None, dur=round(dur, 2))
            else:
                rr = road23(npth)
            scored.append(dict(tag=tag, path=p, norm=npth, val=round(val, 4), cos=round(cos, 3),
                               mos=round(mos, 2), rms=rms1, peak=pk, dur=round(dur, 2),
                               bad=bad, n2=len(rr["r2"]), r3=rr["r3"],
                               tier=("到位" if val >= p25 else ("勉强" if val >= p10 else "未达"))))

        clean = [x for x in scored if not x["bad"]]
        # 1) 路3：**候选一律不许带路3 FAIL**（哪怕原条没有）
        #    ★ 2026-11-14 22:0x 修：原写法 `(not base3) or ...` 让 base3=False 时全放行，
        #    结果 c2_0230 选了个「路2 修好但自己带出路3 FAIL」的候选 —— 修一个问题造一个新问题。
        s1 = [x for x in clean if x["r3"] is None]
        if not s1:
            # 没有任何候选能避开路3 ⇒ 保留原文件，不拿更差的顶
            s1 = [x for x in clean if x["tag"] == "cur"]
        # 2) 路2：命中数必须严格少于原条
        s2 = [x for x in s1 if x["n2"] < base2] if base2 > 0 else s1
        pool = s2 or s1 or clean
        if not pool:
            rows.append(dict(id=i, who=who, emo=emo, win="keep", voice=p0.get("voice"),
                             seed=None, base2=base2, base3=base3, why="全部候选过硬闸失败→保留原文件",
                             detail=scored))
            print("%-9s %-8s %-5s 全部失败 → 保留原文件" % (i, who, emo), flush=True)
            continue
        # 3) 优先「路3 已修 + 路2 已修」，再优先**原档**（换档会造成条间 F0 落差），
        #    最后比 tier / MOS / 情绪
        pool.sort(key=lambda x: (x["r3"] is not None, x["n2"] > 0, x["tag"] != "cur",
                                 {"到位": 0, "勉强": 1, "未达": 2}[x["tier"]],
                                 -x["mos"], -x["val"], -x["cos"]))
        best = pool[0]
        fixed2 = best["n2"] < base2
        fixed3 = (best["r3"] is None) if base3 else True
        why = []
        if base2:
            why.append("路2 %d→%d" % (base2, best["n2"]))
        if base3:
            why.append("路3 %s" % ("修复" if fixed3 else "仍在"))
        why.append("tier=%s MOS%.2f" % (best["tier"], best["mos"]))
        if best["tag"] != "cur":
            shutil.copy2(best["norm"], os.path.join(OUT, i + ".wav"))
            voice = best["tag"].rsplit("_s", 1)[0]
            seed = int(best["tag"].rsplit("_s", 1)[1])
        else:
            voice, seed = p0.get("voice"), 42
        rows.append(dict(id=i, who=who, emo=emo, win=best["tag"], voice=voice, seed=seed,
                         val=best["val"], cos=best["cos"], mos=best["mos"], tier=best["tier"],
                         base2=base2, base3=base3, n2=best["n2"], r3=best["r3"],
                         fixed2=bool(fixed2), fixed3=bool(fixed3),
                         why="；".join(why), detail=scored))
        print("%-9s %-8s %-5s 胜 %-22s %s" % (i, who, emo, best["tag"], "；".join(why)), flush=True)
        for x in scored:
            print("      %-24s val %.4f cos %.3f MOS %.2f %.2fs 路2=%d 路3=%s %s%s"
                  % (x["tag"], x["val"], x["cos"], x["mos"], x["dur"], x["n2"],
                     "FAIL" if x["r3"] else "-", "←胜" if x["tag"] == best["tag"] else "",
                     ("  拒:" + ",".join(x["bad"])) if x["bad"] else ""), flush=True)

    json.dump(rows, open(os.path.join(HERE, "_r15_pick_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    change = [r for r in rows if r["win"] not in ("cur", "keep")]
    json.dump([dict(id=r["id"], role=r["who"], emo=r["emo"], voice=r["voice"], seed=r["seed"])
               for r in change],
              open(os.path.join(HERE, "_regen_r15_pick.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    nf2 = sum(1 for r in rows if r.get("fixed2"))
    nf3 = sum(1 for r in rows if r.get("fixed3") and r.get("base3"))
    print("\n换掉 %d / %d 条；路2 修复 %d / %d，路3 修复 %d / %d，保留原文件 %d"
          % (len(change), len(rows), nf2,
             sum(1 for r in rows if r.get("base2")), nf3,
             sum(1 for r in rows if r.get("base3")),
             sum(1 for r in rows if r["win"] == "keep")))


if __name__ == "__main__":
    main()
