# -*- coding: utf-8 -*-
"""_wary_apply.py —— 警惕 12 条：把各 seed 候选归一后重新择优，胜者落 _regen_r6_out。

## 为什么不能直接用 _wary_pick.py 的结论

`_wary_pick.py` 直接 `probe(cur)` vs `probe(alt)`，但 `cur` 在 `finish_r6 --norm` 之后
已经是 voiced RMS −24dBFS，而 `alt` 是**刚生成的原始电平**（通常更响 3~6dB）。
NISQA-MOS 对电平敏感 ⇒ 比较偏向备用 seed，实测「7/11 备用胜出」里有一部分是电平占的便宜。

本脚本改为：**所有候选先按同一把尺子归一到 −24dBFS，再比 disgusted（判据本身）与 MOS。**
胜者写回 `_regen_r6_out/<id>.wav` 时已经是归一版，后续 `finish_r6.py --norm` 对它无操作。

判据阈值取自 `dialog_gate.load_ref_stats()['警惕']`：p10 0.0009 / p25 0.0052。
p25 以上 = 到位，p10~p25 = 勉强（MANUAL），p10 以下 = 未达（真 REGEN）。

用法：python _wary_apply.py
"""
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
from norm_dlg import vdb, soft_clip

HERE = "G:/_setup"
OUT = os.path.join(HERE, "_regen_r6_out")
TMP = os.path.join(HERE, "_wary_norm")
TARGET = -24.0
PEAK_MAX = 0.891
GAIN_LIMIT = 20.0
P10, P25 = 0.0009, 0.0052


def norm_to_tmp(src, dst):
    """归一到 voiced RMS TARGET；返回 (ok, rms_before, rms_after, clipped, note)。"""
    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    r0 = vdb(y, sr)
    gain = TARGET - r0
    if abs(gain) > GAIN_LIMIT:
        return False, round(r0, 2), None, False, "超 ±%ddB 未处理" % GAIN_LIMIT
    y = y * (10 ** (gain / 20.0))
    pk = float(np.abs(y).max())
    clip = pk > PEAK_MAX
    if clip:
        y = soft_clip(y, PEAK_MAX)
    sf.write(dst, y.astype(np.float32), sr, subtype="PCM_16")
    return True, round(r0, 2), round(vdb(y, sr), 2), clip, ""


def main():
    os.makedirs(TMP, exist_ok=True)
    todo = [t for t in json.load(open(os.path.join(HERE, "_regen_r6.json"), encoding="utf-8"))
            if t["emo"] == "警惕"]

    import ser as S
    import _nat_guard as NG
    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))

    rows = []
    for k, t in enumerate(todo, 1):
        i = t["id"]
        cands = [("cur", os.path.join(OUT, i + ".wav"))]
        for s in ("7", "11", "23"):
            p = os.path.join(HERE, "_wary_s" + s, "%s_s%s.wav" % (i, s))
            if os.path.exists(p) and os.path.getsize(p) > 50000:
                cands.append(("s" + s, p))

        scored = []
        for tag, p in cands:
            if not (os.path.exists(p) and os.path.getsize(p) > 50000):
                continue
            dst = os.path.join(TMP, "%s_%s.wav" % (i, tag))
            ok, r0, r1, clip, note = norm_to_tmp(p, dst)
            if not ok:
                scored.append(dict(tag=tag, path=p, rms0=r0, mos=None, d=None,
                                   note=note, ok=False))
                continue
            sc = e2v.score(dst) or {}
            mos = float(NG.raw(dst).get("nq_mos") or 0)
            scored.append(dict(tag=tag, path=p, norm=dst, rms0=r0, rms1=r1, clip=clip,
                               d=round(float(sc.get("厌恶/disgusted", 0)), 4),
                               mos=round(mos, 2), top=sc.get("_top"), ok=True, note=note))

        good = [x for x in scored if x["ok"]]
        if not good:
            rows.append(dict(id=i, win=None, note="无可用候选"))
            print("[%2d/%d] %-8s 无可用候选" % (k, len(todo), i), flush=True)
            continue
        # 择优规则（2026-11-13 01:42 定，按「两个闸都要」的思路，不追噪声）：
        #   1) 「双过」= d>=p25 且 MOS>=2.0，在其中取 MOS 最大 —— 情绪到位且音质不崩
        #   2) 没有双过但有 d>=p10，取 d 最大 —— 换档的目的就是情绪，音质交给自然度闸判
        #   3) d 全部 < p10（情绪根本不出现）⇒ 取 MOS 最大 ——
        #      此时 0.0001 vs 0.0004 是噪声，为它牺牲 0.4 MOS 是拿假信号做决策
        dual = [x for x in good if x["d"] >= P25 and x["mos"] >= 2.0]
        near = [x for x in good if x["d"] >= P10]
        if dual:
            pick_pool, why = dual, "双过"
        elif near:
            pick_pool, why = near, "情绪优先"
        else:
            pick_pool, why = good, "情绪不来→保音质"
        order = {"cur": 0, "s7": 1, "s11": 2, "s23": 3}
        if why == "情绪优先":
            best = sorted(pick_pool, key=lambda x: (-x["d"], -x["mos"], order.get(x["tag"], 9)))[0]
        else:
            best = sorted(pick_pool, key=lambda x: (-x["mos"], -x["d"], order.get(x["tag"], 9)))[0]
        tier = "到位" if best["d"] >= P25 else ("勉强" if best["d"] >= P10 else "未达")
        rows.append(dict(id=i, win=best["tag"], rule=why, d=best["d"], mos=best["mos"],
                         tier=tier, rms1=best["rms1"], clip=best["clip"],
                         detail=[{kk: x.get(kk) for kk in ("tag", "d", "mos", "rms0", "rms1", "top")}
                                 for x in good]))
        # ★ 2026-11-13 01:52 修：原来只在「非 cur 胜出」时回写，于是 cur 胜出但本身
        #   未经归一（例如 _wary_pick 把原始 s7 直接 copy 到 OUT）时会漏归一 ——
        #   实测 15 条回填里出现 −32.78dBFS，跨 8.78dB，违反「跨度 ≤1dB」。
        #   改为：只要源文件不在 −24dBFS（±0.05），就把归一版写回。
        stale = best.get("rms0") is not None and abs(best["rms0"] - TARGET) > 0.05
        if best["tag"] != "cur" or stale:
            shutil.copy2(best["norm"], os.path.join(OUT, i + ".wav"))
        print("[%2d/%d] %-8s 胜 %-4s disgusted %.4f  MOS %.2f  %s/%s  (候选 %s)"
              % (k, len(todo), i, best["tag"], best["d"], best["mos"], tier, why,
                 ", ".join("%s:%.4f/%.2f" % (x["tag"], x["d"], x["mos"]) for x in good)),
              flush=True)

    json.dump(rows, open(os.path.join(HERE, "_wary_apply_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = sum(1 for r in rows if r.get("tier") == "到位")
    mid = sum(1 for r in rows if r.get("tier") == "勉强")
    print("\n到位 %d / 勉强 %d / 未达 %d（共 %d）"
          % (ok, mid, len(rows) - ok - mid, len(rows)), flush=True)
    print("台账 _wary_apply_log.json；胜者已按 −24dBFS 归一写入 %s" % OUT, flush=True)


if __name__ == "__main__":
    main()
