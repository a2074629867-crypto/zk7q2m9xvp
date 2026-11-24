# -*- coding: utf-8 -*-
"""收尾修补：尾部补足衰减、开头剪掉过长静音。

为什么纯后处理就够：
  tail = 文件尾 − 最后一个有声帧。FIX 的 12 条只有 0.02~0.05s（门槛 0.06），
  补一段**本条自己的**底噪再淡出即可，不动语音一个采样。
  lead 过长（1.0~1.2s）是插停顿后前导静音没被裁，剪到 0.10s。

用法：
  G:/Python310/python.exe -u _tail_fix.py --dir _regen_final --dry
  G:/Python310/python.exe -u _tail_fix.py --dir _regen_final --apply
"""
import argparse
import io
import json
import os
import sys

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
sys.path.insert(0, ROOT)
import _speedlib  # noqa: E402

FL = 0.02
TAIL_MIN = 0.06
TAIL_TARGET = 0.10       # 补到 0.10s，留出余量
LEAD_MAX = 1.00          # 与 narr_gate_phys.LEAD_MAX 一致，别把正常呼吸位置当缺陷
LEAD_TARGET = 0.10


def voiced_frames(y, sr):
    db, h = _speedlib._frames_db(y, sr)
    hi = db[db > np.percentile(db, 90)]
    thr = max(-60.0, float(np.percentile(hi, 90)) - 20.0) if len(hi) else -45.0
    return db > thr, h / float(sr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default=os.path.join(ROOT, "_tail_fix_report.json"))
    a = ap.parse_args()

    ids = [f[:-4] for f in sorted(os.listdir(a.dir)) if f.endswith(".wav")]
    rows, fixed = [], 0
    for sid in ids:
        p = os.path.join(a.dir, sid + ".wav")
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        on, hop = voiced_frames(y, sr)
        idx = np.flatnonzero(on)
        if len(idx) == 0:
            continue
        first = idx[0] * hop
        last_end = (idx[-1] + 1) * hop
        dur = len(y) / sr
        tail = dur - last_end
        rec = dict(id=sid, dur=round(dur, 3), lead=round(first, 3), tail=round(tail, 3))
        act = []

        if tail < TAIL_MIN:
            # 用本条末尾已有的静音当底噪样本（20~40ms），循环拼到目标长度
            seg = y[-max(1, int(0.03 * sr)):]
            need = int((TAIL_TARGET - tail) * sr)
            if need > 0:
                reps = int(np.ceil(need / max(1, len(seg))))
                pad = np.tile(seg, reps)[:need]
                fade = np.linspace(1.0, 0.0, min(len(pad), int(0.06 * sr))) ** 1.5
                pad[-len(fade):] *= fade
                y = np.concatenate([y, pad.astype(y.dtype)])
                act.append("tail %.3f→%.3f" % (tail, tail + need / sr))

        if first > LEAD_MAX:
            cut = int((first - LEAD_TARGET) * sr)
            if cut > 0:
                y = y[cut:]
                act.append("lead %.2f→%.2f" % (first, LEAD_TARGET))

        if act:
            fixed += 1
            rec["act"] = act
            if a.apply:
                sf.write(p, y, sr, subtype="PCM_16")
        rows.append(rec)

    n_tail = sum(1 for r in rows if r["tail"] < TAIL_MIN)
    n_lead = sum(1 for r in rows if r["lead"] > LEAD_MAX)
    print("检查 %d 条：tail<%.2f 的 %d 条，lead>%.2f 的 %d 条"
          % (len(rows), TAIL_MIN, n_tail, LEAD_MAX, n_lead))
    for r in rows:
        if r.get("act"):
            print("   %-9s %s" % (r["id"], " | ".join(r["act"])))
    print("%s %d 条" % ("已修" if a.apply else "待修（--apply 才写盘）", fixed))
    json.dump(rows, io.open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
