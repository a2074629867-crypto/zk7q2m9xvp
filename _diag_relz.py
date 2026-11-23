# -*- coding: utf-8 -*-
"""诊断：新旧两库的 rel_z 分布离散度是否变化。

为什么必须查：rel_z 是「句内归一」的比值指标，rubberband 等比拉伸不改变比值
⇒ 单靠 tempo 不可能把副词 z 从 0.81 压到 0.39。
若新库全体词的 z 标准差明显变小，就是 **80ms 时间戳量化在快语速下把 z 压平**（测量衰减），
不是模型真的不强调了。两个结论对生产决策完全相反，必须分清。

用法：G:/Python310/python.exe -u _diag_relz.py
"""
import io
import json
import os
import statistics as st
import sys

ROOT = r"G:/_setup"
sys.path.insert(0, ROOT)
from _loop_1123 import word_zs  # noqa: E402


def load(p):
    return {os.path.basename(k).rsplit(".", 1)[0]: v
            for k, v in json.load(io.open(os.path.join(ROOT, p), encoding="utf-8")).items()}


def stats(wl, d, ids):
    zs, rels, durs = [], [], []
    n = 0
    for sid in ids:
        rec = wl.get(sid)
        p = os.path.join(ROOT, d, sid + ".wav")
        if not rec or not os.path.exists(p):
            continue
        ws = word_zs(rec)
        if len(ws) < 3 or "z" not in ws[0]:
            continue
        n += 1
        zs.extend(x["z"] for x in ws)
        durs.extend(x["dur"] for x in ws)
    if not zs:
        return None
    mz = st.mean(zs)
    sd = st.pstdev(zs)
    return dict(n_sent=n, n_word=len(zs), z_mean=round(mz, 3), z_sd=round(sd, 3),
                dur_med=round(st.median(durs), 3))


def main():
    ids = [ln.strip() for ln in io.open(os.path.join(ROOT, "_partial_ids.txt"),
                                        encoding="utf-8") if ln.strip()]
    old = load("_wl_words.json")
    new = load("_wl_regen1123.json")
    a = stats(old, "_audio_ch123/out_bak_prepause", ids)
    b = stats(new, "_regen_1123", ids)
    print("同一批 %d 句" % len(ids))
    for tag, s in (("旧 0.80", a), ("新 1.00/0.84", b)):
        if s:
            print("  %-12s n_sent=%-4d n_word=%-5d z_mean=%+.3f  z_sd=%.3f  词时长中位=%.3fs"
                  % (tag, s["n_sent"], s["n_word"], s["z_mean"], s["z_sd"], s["dur_med"]))
    if a and b:
        print()
        print("  z_sd 比 %.3f （<1 说明新库 z 被压平 = 量化衰减）" % (b["z_sd"] / a["z_sd"]))
        print("  词时长中位比 %.3f （预期 ≈ 0.80/1.00 = 0.80）"
              % (b["dur_med"] / a["dur_med"]))
        # 用旧库 z_sd 归一，把新库 z 还原到旧库尺度，看副词差距还剩多少
        k = b["z_sd"] / a["z_sd"]
        print("  若纯属衰减：新库 0.394 × (1/%.3f) = %.3f（对比旧库 0.814）"
              % (k, 0.394 / k))
    json.dump({"old": a, "new": b, "n_ids": len(ids)},
              io.open(os.path.join(ROOT, "_diag_relz.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
