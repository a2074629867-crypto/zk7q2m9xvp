# -*- coding: utf-8 -*-
"""_dlg_fp.py —— 每条对白的「整条音色指纹」（不切窗，短句也能算）

为什么不用 embedding：实测同一文本的短句之间 r34 cos **全部 = 1.000**
（'No.' 6 条、'Yes.' 3 条、'Why?' 2 条、'Liar.' 2 条），说明 0.36~0.6s 的
音频上 embedding 编码的是**文本内容**，不是说话人。`Yes.` 对 `No.` 的 cos 0.053
是内容不同，不是音色变了。

改用整条谱特征中位（只取浊音帧）：
  cen 谱质心 / slp 谱倾斜 / hnr 谐噪比 / f0 基频中位 / voiced 浊音帧占比
0.36s 的 'No.' 也有 ~22 个 16ms 帧，足够算谱质心与谱倾斜。

输出 _dlg_fp.json
用法：G:/Python310/python.exe _dlg_fp.py
"""
import sys, os, json
sys.path.insert(0, r"G:/_setup")
os.chdir(r"G:/_setup")
import numpy as np
import mt_seg_drift as D

plan = [json.loads(l) for l in open("_dlg_plan_v2.jsonl", encoding="utf-8")]
out = {}
for i, r in enumerate(plan, 1):
    p = r["path"]
    try:
        a, sr = D.read_wav(p)
        S = D.series(a, sr)
        f0 = np.array([x for x in S["f_p"] if x > 0], dtype=float)
        h = np.array([x for x in S["h_h"] if x is not None and np.isfinite(x)], dtype=float)
        cen = np.array([x for x in S["cen"] if np.isfinite(x)], dtype=float)
        slp = np.array([x for x in S["slp"] if np.isfinite(x)], dtype=float)
        out[r["id"]] = dict(
            dur=round(len(a) / sr, 2),
            f0=round(float(np.median(f0)), 1) if len(f0) else None,
            hnr=round(float(np.median(h)), 1) if len(h) else None,
            cen=round(float(np.median(cen)), 0) if len(cen) else None,
            slp=round(float(np.median(slp)), 2) if len(slp) else None,
            n_f0=len(f0), n_fr=len(cen),
        )
    except Exception as e:  # noqa: BLE001
        out[r["id"]] = dict(err=repr(e))
    if i % 40 == 0 or i == len(plan):
        print("  %d/%d" % (i, len(plan)), flush=True)

json.dump(out, open("_dlg_fp.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
ok = sum(1 for v in out.values() if "err" not in v)
print("成功 %d / 失败 %d -> _dlg_fp.json" % (ok, len(out) - ok))
