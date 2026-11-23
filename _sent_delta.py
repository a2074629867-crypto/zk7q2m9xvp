# -*- coding: utf-8 -*-
"""句中位置 / 合成的稳健测量（G:/Python310）

对上一版的两处污染做修正：
1. pitch_ceiling 500 → 250（睡前朗读男声基频不会超 250；500 会大量倍频误判）
2. 按 50ms 小窗算 RMS，只保留 RMS > 0.015 的帧（剔除句尾近乎静音段的乱跳）
3. 同时报 p25/p50/p75 与有效帧数，便于判断可信度

区段用首尾词文本匹配定位（ASR 可能把 enfolded 切成 and folded）。
"""
import json
import os

import numpy as np
import parselmouth
import soundfile as sf

D = "G:/_setup/dots_edit2/"
TS = "G:/_setup/_ew_ts.json"

SEGS = {
    "HEAD": ("tussle", "hair"),
    "MID":  ("reading", "pocket"),
    "TAIL": ("stack", "side"),
}
RMS_GATE = 0.006
CEIL = 250


def load(v):
    a, sr = sf.read(D + "MES_%s.wav" % v, dtype="float32", always_2d=True)
    return a.mean(1), sr


def find_span(ws, w0, w1):
    def norm(x):
        return x.strip(".,;:!?\"'").lower()
    i0 = next((i for i, w in enumerate(ws) if norm(w[0]) == w0), None)
    if i0 is None:
        return None
    i1 = next((i for i in range(i0, len(ws)) if norm(ws[i][0]) == w1), None)
    return (i0, i1) if i1 is not None else None


def seg_f0(a, sr, t0, t1):
    """返回区段内 RMS 门控后的 F0 统计。"""
    s = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    p = s.to_pitch_ac(time_step=0.01, pitch_floor=50, pitch_ceiling=CEIL)
    t = p.xs()
    f = p.selected_array["frequency"]

    step = 0.05
    vals = []
    k = 0
    while t0 + k * step < t1:
        lo, hi = t0 + k * step, min(t0 + (k + 1) * step, t1)
        m = (t >= lo) & (t < hi)
        if m.sum() == 0:
            k += 1
            continue
        idx = np.where(m)[0]
        seg = a[int(lo * sr):int(hi * sr)]
        rms = float(np.sqrt((seg ** 2).mean())) if len(seg) else 0.0
        if rms >= RMS_GATE:
            v = f[idx]
            v = v[v > 0]
            if len(v):
                vals.append(float(np.median(v)))
        k += 1
    if not vals:
        return None
    return dict(n=len(vals),
                p25=float(np.percentile(vals, 25)),
                p50=float(np.median(vals)),
                p75=float(np.percentile(vals, 75)))


def main():
    ts = json.load(open(TS, encoding="utf-8"))
    base_ws = ts["ES_base"]["words"]
    a0, sr0 = load("ES_base")
    bstat = {}
    for name, (w0, w1) in SEGS.items():
        sp = find_span(base_ws, w0, w1)
        bstat[name] = seg_f0(a0, sr0, base_ws[sp[0]][1], base_ws[sp[1]][2])

    order = ["EP_head", "EP_tail", "EP_two_same_sent", "EW_emo_clause",
             "EW_emo_sent", "SEQ_base_rate", "SEQ_emo_rate"]

    print("基准 ES_base（RMS 门控，ceiling=250）")
    for k, v in bstat.items():
        print("  %-5s p25 %5.1f  p50 %5.1f  p75 %5.1f  (有效窗 %d)" %
              (k, v["p25"], v["p50"], v["p75"], v["n"]))

    print("\nΔ 半音（相对 base 同区段 p50；括号内为有效窗数）")
    print("%-18s %18s %18s %18s" % ("变体", "HEAD", "MID", "TAIL"))
    rows = []
    for v in order:
        if v not in ts:
            continue
        a, sr = load(v)
        ws = ts[v]["words"]
        cells = []
        rec = {"v": v}
        for name, (w0, w1) in SEGS.items():
            sp = find_span(ws, w0, w1)
            cur = seg_f0(a, sr, ws[sp[0]][1], ws[sp[1]][2]) if sp else None
            b = bstat[name]
            if cur and b:
                d = 12 * np.log2(cur["p25"] / b["p25"])
                rec[name] = round(float(d), 2)
                cells.append("%+6.2f (%d)" % (d, cur["n"]))
            else:
                rec[name] = None
                cells.append("-")
        rows.append(rec)
        print("%-18s %18s %18s %18s" % (v, cells[0], cells[1], cells[2]))

    json.dump(rows, open("G:/_setup/_sent_delta.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nwritten G:/_setup/_sent_delta.json")


if __name__ == "__main__":
    main()
