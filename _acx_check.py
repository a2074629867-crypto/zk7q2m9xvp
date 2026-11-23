# -*- coding: utf-8 -*-
"""按 ACX 音频规范核对交付版，并换算一本 10 万字书的成本/工时对照。"""
import sys
sys.path.insert(0, "D:/py_libs"); sys.path.insert(0, "G:/_setup")
import numpy as np, soundfile as sf
import mt_final_pause as FP

ACX = {"rms_lo": -23.0, "rms_hi": -18.0, "peak_max": -3.0,
       "noise_max": -60.0, "gap_in_sentence": 0.5}

for f in ["_chap_ch1_v4b.wav"]:
    x, sr = sf.read(f, dtype="float32", always_2d=True); x = x.mean(1)
    db, n, hop = FP.frame_db(x, sr)
    on = db > (np.percentile(db, 90) - 25.0)
    seg = [x[i*hop:min(len(x), i*hop+hop)] for i in np.where(on)[0]]
    y = np.concatenate(seg).astype(np.float64)
    rms = 20*np.log10(np.sqrt((y**2).mean())+1e-12)
    peak = 20*np.log10(np.abs(x).max()+1e-12)
    # 底噪：最静的 1% 帧
    nf = 20*np.log10(np.sqrt((x[:len(db)*hop].reshape(len(db), hop)**2).mean(1))+1e-12)
    floor = float(np.percentile(nf, 1))
    # 句内 >0.5s 停顿（单元内部，即模型自带的）
    gaps, run = [], 0
    for v in on:
        if not v: run += 1
        else:
            if run: gaps.append(run*hop/sr)
            run = 0
    gl = np.array([g for g in gaps if g >= 0.3])
    print("=== 交付版 vs ACX 规范 ===")
    print("%-16s %10s %14s %s" % ("项", "实测", "ACX 要求", "判定"))
    print("%-16s %9.1f %14s %s" % ("RMS", rms, "−23 ~ −18 dB",
          "✓" if ACX["rms_lo"] <= rms <= ACX["rms_hi"] else "✗ 偏轻 %.1f dB" % (ACX["rms_lo"]-rms)))
    print("%-16s %9.1f %14s %s" % ("峰值", peak, "≤ −3 dBFS",
          "✓" if peak <= ACX["peak_max"] else "✗ 超 %.1f dB" % (peak-ACX["peak_max"])))
    print("%-16s %9.1f %14s %s" % ("底噪", floor, "< −60 dBFS",
          "✓" if floor < ACX["noise_max"] else "✗"))
    over = int((gl > 0.5).sum())
    print("%-16s %9s %14s %s" % ("句内 >0.5s 停顿", "%d / %d" % (over, len(gl)),
          "≤ 0.5s（禁止）", "✗ %d 处超标" % over if over else "✓"))
    print()
    print("停顿 p50 %.2f  p90 %.2f  max %.2f（单元间，属章节间隔，不受 ACX 句内规则约束）"
          % tuple(float(np.percentile(gl, p)) for p in (50, 90, 100)))

# 成本换算
print("\n=== 一本 10 万词书（≈55 万字符 ≈ 9.2 小时成品）成本对照 ===")
W, CH, HOURS = 100000, 550000, 100000/9300
rows = [
    ("ElevenLabs Pro", 99, "600k credits/月 = 600 分钟", 600000),
    ("MiniMax 2.8 HD", 100/1e6*CH, "$100/1M 字符", None),
    ("Fish Audio S2 Pro", 15/1e6*CH, "$15/1M 字符", None),
    ("Google Chirp", 0.04/1e3*CH, "$0.04/1k 字符", None),
]
for name, cost, note, cap in rows:
    if cap:
        months = max(1, int(np.ceil(CH/cap)))
        print("  %-18s $%7.0f  (%s → 需 %d 个月)" % (name, cost*months, note, months))
    else:
        print("  %-18s $%7.0f  (%s)" % (name, cost, note))
print("  %-18s $%7.0f  (本地推理，电费级)" % ("我们（dots.tts）", 0))
