# -*- coding: utf-8 -*-
"""_cloud_pick.py —— 对云端批量候选做本地评测择优（闸口径）。

输入：`_cand_bcg/cand/<id>__<voice>__s<seed>.wav`（云端已归一到 −24dBFS）
      `_audio_ch123/out/<id>.wav`（现役，作为「不改」基准）
输出：`_regen_r12_out/<id>.wav` 胜者；`_regen_r12.json` 清单；`_cloud_pick_log.json` 台账

评分口径与 `_multi_ref.py` 完全一致（同一把尺子，不许另写一套）：
  主信号（闸在用的那个） + 声纹 cos（本角色质心） + NISQA MOS + 硬闸（时长/语速/削波/MOS/cos）

择优规则（DECISIONS 01:42 三条 + 18:35 时长硬闸）：
  1) 过硬闸且 val≥p25 ⇒ 取 MOS 最高
  2) 过硬闸且 val≥p10 ⇒ 取 val 最高
  3) 没有达 p10 的 ⇒ 取 MOS 最高（别为 0.0001 的情绪噪声牺牲 0.4 MOS）
  全部过硬闸失败 ⇒ 保留原文件（不写 OUT）
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
# 目录可由命令行覆盖：python _cloud_pick.py <cand根目录> <norm目录> <out目录> <台账名> <regen名>
_argv = [a for a in sys.argv[1:] if not a.startswith("-")]
_CROOT = _argv[0] if len(_argv) > 0 else os.path.join(HERE, "_cand_bcg")
CAND = os.path.join(_CROOT, "cand") if os.path.isdir(os.path.join(_CROOT, "cand")) else _CROOT
NORM = os.path.join(_CROOT, "norm")
OUT = _argv[2] if len(_argv) > 2 else os.path.join(HERE, "_regen_r12_out")
_TAG = _argv[3] if len(_argv) > 3 else "r12"
_REGEN = _argv[4] if len(_argv) > 4 else "_regen_r12.json"
DELIV = os.path.join(HERE, "_audio_ch123/out")
TARGET, PEAK_MAX = -24.0, 0.891

PRIMARY = {"警惕": ("e2v", "厌恶/disgusted"), "激动反抗": ("vox", "d"),
           "委屈": ("vox", "neg_a"), "兴奋": ("vox", "a_x_v"),
           "平静": ("vox", "a_x_v"), "紧张": ("vox", "neg_a")}


def normalize(src, dst):
    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    r0 = vdb(y, sr)
    g = TARGET - r0 if r0 > -60 else 0.0
    g = max(-12.0, min(12.0, g))          # 防 vdb 极端值把音频拉爆（云端已归一到 −24，正常 g≈0）
    y = y * (10 ** (g / 20.0))
    if float(np.abs(y).max()) > PEAK_MAX:
        y = soft_clip(y, PEAK_MAX)
    sf.write(dst, y.astype(np.float32), sr, subtype="PCM_16")
    return round(float(vdb(y, sr)), 2), round(float(np.abs(y).max()), 3)


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
    print("候选 %d 条，覆盖 %d 个条目" % (len(files), len(by)))

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
        cands = [("cur", cur)] if os.path.exists(cur) else []
        cands += [("%s_s%d" % (v, s), p) for v, s, p in sorted(by[i])]
        d_old = sf.info(cur).duration if os.path.exists(cur) else 0
        wc = len([k for k in (p0.get("text") or "").split() if any(c.isalpha() for c in k)])

        scored = []
        for tag, p in cands:
            npth = os.path.join(NORM, "%s__%s.wav" % (i, tag))
            rms1, pk = normalize(p, npth)
            sc = e2v.score(npth) or {}
            vs = VOX.score(npth) or {}
            if kind == "e2v":
                val = float(sc.get(key, 0))
            else:
                try:
                    val = float(V.vox_feat(vs, key))
                except Exception:
                    val = 0.0
            vv = utt_emb(spk, npth)
            vv = vv / (np.linalg.norm(vv) + 1e-9)
            cos = float(vv @ cent.get(who, vv))
            dur = sf.info(npth).duration
            # NISQA 对 <1s 的残片会抛 RuntimeError（n_wins=0），且本来也没意义
            if dur >= 1.0:
                try:
                    mos = float((NG.raw(npth) or {}).get("nq_mos") or 0)
                except Exception:
                    mos = 0.0
            else:
                mos = 0.0
            bad = []
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
            scored.append(dict(tag=tag, path=p, norm=npth, val=round(val, 4), cos=round(cos, 3),
                               mos=round(mos, 2), rms=rms1, peak=pk, dur=round(dur, 2), bad=bad))

        clean = [x for x in scored if not x["bad"]]
        if not clean:
            best = next(x for x in scored if x["tag"] == "cur")
            why = "全部候选过硬闸失败→保留原文件"
        else:
            g25 = [x for x in clean if x["val"] >= p25]
            g10 = [x for x in clean if x["val"] >= p10]
            if g25:
                best = max(g25, key=lambda x: (x["mos"], x["val"], x["cos"]))
                why = "到位(p25)→MOS最高"
            elif g10:
                best = max(g10, key=lambda x: (x["val"], x["mos"]))
                why = "达标(p10)→主信号最高"
            else:
                best = max(clean, key=lambda x: (x["mos"], x["val"]))
                why = "无达p10→MOS最高"
        tier = "到位" if best["val"] >= p25 else ("勉强" if best["val"] >= p10 else "未达")
        if best["tag"] != "cur":
            shutil.copy2(best["norm"], os.path.join(OUT, i + ".wav"))
            voice = best["tag"].rsplit("_s", 1)[0]
            seed = int(best["tag"].rsplit("_s", 1)[1])
        else:
            voice = p0["voice"]
            seed = 42
        rows.append(dict(id=i, emo=emo, who=who, win=best["tag"], voice=voice, seed=seed,
                         val=best["val"], cos=best["cos"], mos=best["mos"], tier=tier, why=why,
                         p10=round(p10, 4), p25=round(p25, 4),
                         detail=[{k: x[k] for k in ("tag", "val", "cos", "mos", "dur", "bad")}
                                 for x in scored]))
        print("%-8s %-6s 胜 %-22s val %.4f (p10 %.4f) cos %.3f MOS %.2f %-4s [%s]"
              % (i, emo, best["tag"], best["val"], p10, best["cos"], best["mos"], tier, why), flush=True)
        for x in scored:
            print("      %-24s %.4f cos %.3f MOS %.2f %.2fs %s%s" % (
                x["tag"], x["val"], x["cos"], x["mos"], x["dur"],
                "←胜" if x["tag"] == best["tag"] else "",
                ("  拒:" + ",".join(x["bad"])) if x["bad"] else ""), flush=True)

    json.dump(rows, open(os.path.join(HERE, "_cloud_pick_log_%s.json" % _TAG), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    change = [r for r in rows if r["win"] != "cur"]
    json.dump([dict(id=r["id"], role=r["who"], emo=r["emo"], voice=r["voice"], seed=r["seed"])
               for r in change],
              open(os.path.join(HERE, _REGEN), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    n25 = sum(1 for r in rows if r["tier"] == "到位")
    print("\n换掉 %d / %d 条；到位 %d / 勉强 %d / 未达 %d"
          % (len(change), len(rows), n25,
             sum(1 for r in rows if r["tier"] == "勉强"),
             sum(1 for r in rows if r["tier"] == "未达")))


if __name__ == "__main__":
    main()
