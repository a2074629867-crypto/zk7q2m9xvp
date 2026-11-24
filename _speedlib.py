# -*- coding: utf-8 -*-
"""语速量具（唯一口径）：**句中语速** = 词数 ÷ 句内发声时长，不含逗号/句号的大间隔。

为什么另立一个文件：`_build_narr_ch2.py` 原来用 `词数 / 总时长 × 60`，
把句内停顿（逗号 0.51s、句号 1.135s、段落 1.695s）全算进分母，
同一条音频换个停顿长度就换一个 wpm ⇒ 那个数字既不是「说得快」也不是「停顿多」，
两个变量混在一起，没法判断模型本身的语速。

口径定义（**不依赖 ASR**，这一点很关键）：
  ASR 的词时间戳是首尾相接的（`_asr_lib._to_words` 里 `end = 下一个词的 start`，
  末词 end = 文件尾），所以停顿会被吞进前一个词的时长 ——
  实测同一条 c1_0018：干声版 `jaw` 1.04s，插停顿版 2.16s。拿它算语速必然错。

改用波形：
  1. 20ms 帧 / 20ms 跳，逐帧算 RMS dB
  2. 阈值取 `voiced_p50 − 25dB`（自适应，且不低于 −60dBFS）——软辅音是**短促下陷**，
     不会被切掉；只有**持续**的低能量段才算停顿
  3. 低能量段 ≥ PAUSE_MIN 才算停顿（默认 0.15s：英语塞音闭合 ~0.05–0.10s，
     最小标注停顿 0.51s，0.15 卡在中间，两侧都有余量）
  4. speech = 总时长 − 首静音 − 尾静音 − 句内停顿
  5. wpm_in = 词数 ÷ speech × 60

**不变式（用来验量具对不对）**：同一条句子插停顿前后，`wpm_in` 必须基本不变。
插停顿只改分母里的停顿，不改发声部分。
"""
import numpy as np
import soundfile as sf

FL = 0.02           # 帧长 / 跳距（秒），与 narr_gate_phys 一致
DROP_DB = 20.0      # 阈值 = p90 − 20dB
FLOOR_DB = -60.0    # 阈值下限
PAUSE_MIN = 0.15    # 低能量段 ≥ 此长度才算停顿


def _frames_db(y, sr):
    n = int(FL * sr)
    h = int(FL * sr)
    if len(y) < n:
        return np.array([-200.0]), h
    k = 1 + (len(y) - n) // h
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    seg = y[idx].astype(np.float64)
    return 20 * np.log10(np.sqrt((seg ** 2).mean(1)) + 1e-12), h


def speech_time(y, sr, pause_min=PAUSE_MIN, drop_db=DROP_DB, floor_db=FLOOR_DB):
    """返回 (总时长, 句内发声时长, 停顿总长, 最长停顿, 首静音, 尾静音)。

    发声时长 = 总时长 − 首静音 − 尾静音 − 句内停顿（停顿 = ≥pause_min 的低能量段）。
    """
    dur = len(y) / float(sr)
    db, h = _frames_db(y, sr)
    hop = h / float(sr)
    if len(db) < 5:
        return dur, dur, 0.0, 0.0, 0.0, 0.0

    # 阈值：以 p90（语音主体）下探 20dB。
    # ★ 别用「高于 p50 的帧的中位」——实测 c2_0395 那条算出 −31.8，阈值掉到 −56.8，
    #   正好压在 −58 的底噪上，噪声全被当语音，句内时长虚高 2 倍（wpm 88 → 169）。
    thr = max(floor_db, float(np.percentile(db, 90)) - drop_db)

    low = db < thr
    # 低能量段
    runs = []
    i = 0
    n = len(low)
    while i < n:
        if low[i]:
            j = i
            while j < n and low[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    runs = [(a, b) for a, b in runs if (b - a) * hop >= pause_min]
    if not runs:
        return dur, dur, 0.0, 0.0, 0.0, 0.0

    lead = runs[0][1] * hop if runs[0][0] == 0 else 0.0
    tail = (n - runs[-1][0]) * hop if runs[-1][1] == n else 0.0
    inner = [r for r in runs if not (r[0] == 0 or r[1] == n)]
    gap_sum = sum((b - a) * hop for a, b in inner)
    max_gap = max(((b - a) * hop for a, b in inner), default=0.0)
    speech = max(0.0, dur - lead - tail - gap_sum)
    return dur, speech, gap_sum, max_gap, lead, tail


def word_durs(y, sr, words, drop_db=DROP_DB, floor_db=FLOOR_DB):
    """逐词发声时长：把 ASR span 首尾的低能量段剪掉。

    为什么需要：`_asr_lib._to_words` 里 `end = 下一个词的 start`，末词 `end = 文件尾`
    ⇒ span 里含该词后面的停顿。实测 c1_0018 的 `jaw` 干声 1.04s、插停顿版 2.16s。
    用 span 长度当「词时长」测重音，测到的其实是「词 + 停顿」。

    words: [{"w","start","end"}, ...]；返回与之等长的时长列表（秒）。
    """
    db, h = _frames_db(y, sr)
    hop = h / float(sr)
    thr = max(floor_db, float(np.percentile(db, 90)) - drop_db)
    out = []
    for w in words:
        i0 = max(0, int(float(w["start"]) / hop))
        i1 = min(len(db), int(float(w["end"]) / hop))
        if i1 - i0 < 2:
            out.append(max(1e-3, float(w["end"]) - float(w["start"])))
            continue
        on = np.flatnonzero(db[i0:i1] > thr)
        if len(on) == 0:
            out.append(0.04)
        else:
            out.append(max(1e-3, float(on[-1] - on[0] + 1) * hop))
    return out


def wpm_in(path, words, pause_min=PAUSE_MIN):
    """句中语速（wpm）。读不到/太短返回 None。"""
    try:
        y, sr = sf.read(path, dtype="float32")
    except Exception:  # noqa: BLE001
        return None
    if y.ndim > 1:
        y = y.mean(1)
    if len(y) < int(0.2 * sr):
        return None
    _, speech, _, _, _, _ = speech_time(y, sr, pause_min=pause_min)
    if speech < 0.15:
        return None
    return words / speech * 60.0


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        d, sp, g, mg, ld, tl = speech_time(y, sr)
        print("%-34s 总 %.2fs 句内 %.2fs 停顿 %.2fs(最长 %.2fs) 首 %.2f 尾 %.2f 发声占比 %.0f%%"
              % (p.split("/")[-1], d, sp, g, mg, ld, tl, 100 * sp / max(1e-6, d)))
