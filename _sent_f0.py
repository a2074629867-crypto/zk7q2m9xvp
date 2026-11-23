# -*- coding: utf-8 -*-
"""句中位置 / 合成实验的测量（G:/Python310，需 parselmouth）

读 _ew_ts.json（由 asr_venv 的 _ew_ts.py 生成）拿词级时间戳，
按固定词索引定位三个区段，比较各区段 F0 中位与时长。

区段（原文 42 词，0-based）：
  HEAD = 0..5   "A tussle of grayish white hair"
  MID  = 10..15 "reading glasses enfolded in his pocket"
  TAIL = 16..24 "and a stack of books sat by his side"
"""
import json
import os

import numpy as np
import parselmouth
import soundfile as sf

D = "G:/_setup/dots_edit2/"
TS = "G:/_setup/_ew_ts.json"

# 用「首词 / 尾词」文本匹配定位，避免固定索引在 ASR 切分差异下整体偏移
# （EP_two_same_sent 实测把 enfolded 切成 "and folded"，索引 +1 全错）
SEGS = {
    "HEAD": ("tussle", "hair"),
    "MID":  ("reading", "pocket"),
    "TAIL": ("stack", "side"),
}


def find_span(ws, w0, w1):
    """在词序列里找 w0..w1 的 (i0, i1)。匹配失败返回 None。"""
    def norm(x):
        return x.strip(".,;:!?\"'").lower()

    i0 = next((i for i, w in enumerate(ws) if norm(w[0]) == w0), None)
    if i0 is None:
        return None
    i1 = next((i for i in range(i0, len(ws)) if norm(ws[i][0]) == w1), None)
    return (i0, i1) if i1 is not None else None


def load(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return a.mean(1), sr


def f0_curve(a, sr):
    s = parselmouth.Sound(a.astype(np.float64), sampling_frequency=sr)
    p = s.to_pitch_ac(time_step=0.01, pitch_floor=50, pitch_ceiling=500)
    return p.xs(), p.selected_array["frequency"]


def seg_stats(t, f, t0, t1):
    m = (t >= t0) & (t <= t1) & (f > 0)
    v = f[m]
    if len(v) == 0:
        return dict(n=0, med=None, p10=None, p90=None, hi=None)
    return dict(n=int(len(v)), med=float(np.median(v)),
                p10=float(np.percentile(v, 10)),
                p90=float(np.percentile(v, 90)),
                hi=float(100.0 * (v > 200).sum() / len(v)))


def main():
    ts = json.load(open(TS, encoding="utf-8"))
    base = ts["ES_base"]
    bw = base["words"]
    order = ["ES_base", "EP_head", "EP_tail", "EP_two_same_sent",
             "EW_emo_clause", "EW_emo_sent", "SEQ_base_rate", "SEQ_emo_rate"]

    print("%-18s %7s %6s %7s %8s %8s %8s" %
          ("变体", "时长", "词数", "wpm", "F0中位", "低频%", "声纹略"))
    rows = {}
    for v in order:
        p = D + "MES_%s.wav" % v
        if not os.path.exists(p):
            continue
        a, sr = load(p)
        dur = len(a) / sr
        t, f = f0_curve(a, sr)
        vv = f[f > 0]
        rec = dict(dur=round(dur, 3),
                   nwords=len(ts.get(v, base)["words"]),
                   wpm=round(len(ts.get(v, base)["words"]) / dur * 60, 1),
                   med=round(float(np.median(vv)), 1),
                   lo=round(100.0 * (vv < 100).sum() / len(vv), 1),
                   hi=round(100.0 * (vv > 200).sum() / len(vv), 1))
        rows[v] = rec
        print("%-18s %6.2fs %6d %7.1f %8.1f %8.1f" %
              (v, rec["dur"], rec["nwords"], rec["wpm"], rec["med"], rec["lo"]))

    # 区段对比：每个变体在 HEAD/MID/TAIL 的 F0 中位与 Δ（相对 base）
    print("\n区段 F0（半音差，相对 ES_base 同区段）")
    print("%-18s %22s %22s %22s" % ("变体", "HEAD 0-5", "MID 10-15", "TAIL 16-24"))
    for v in rows:
        if v not in ts:
            continue
        ws = ts[v]["words"]
        a, sr = load(D + "MES_%s.wav" % v)
        t, f = f0_curve(a, sr)
        cells = []
        for name, (w0, w1) in SEGS.items():
            sp = find_span(ws, w0, w1)
            if sp is None:
                cells.append("-")
                continue
            i0, i1 = sp
            t0, t1 = ws[i0][1], ws[i1][2]
            cur = seg_stats(t, f, t0, t1)
            cells.append("%5.1fHz %5.2fs" % (cur["med"] or 0, t1 - t0))
        print("%-18s %22s %22s %22s" % (v, cells[0], cells[1], cells[2]))

    # 半音差表（用 base 的曲线在同一区段算）
    print("\nΔ 半音（相对 base 同区段，正值=更高）")
    a0, sr0 = load(D + "MES_ES_base.wav")
    t0c, f0c = f0_curve(a0, sr0)
    bws = base["words"]
    bstat = {}
    for name, (w0, w1) in SEGS.items():
        sp = find_span(bws, w0, w1)
        if sp:
            bstat[name] = seg_stats(t0c, f0c, bws[sp[0]][1], bws[sp[1]][2])

    print("%-18s %10s %10s %10s" % ("变体", "HEAD", "MID", "TAIL"))
    for v in rows:
        if v not in ts:
            continue
        ws = ts[v]["words"]
        a, sr = load(D + "MES_%s.wav" % v)
        t, f = f0_curve(a, sr)
        out = []
        for name, (w0, w1) in SEGS.items():
            sp = find_span(ws, w0, w1)
            if sp is None:
                out.append("-")
                continue
            cur = seg_stats(t, f, ws[sp[0]][1], ws[sp[1]][2])
            b = bstat[name]
            if cur["med"] and b["med"]:
                out.append("%+6.2f" % (12 * np.log2(cur["med"] / b["med"])))
            else:
                out.append("-")
        print("%-18s %10s %10s %10s" % (v, out[0], out[1], out[2]))


if __name__ == "__main__":
    main()
