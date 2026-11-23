# -*- coding: utf-8 -*-
"""mt_post.py —— 旁白后处理与成章拼接。

链路（按已固化的经验）：
  原始 → 去首尾静音 → 整条 rubberband tempo 0.80（绝不分段拉伸）→ 整体增益 −24dBFS
  → 按 plan 的 gap 拼成整章

用法：
  python mt_post.py --ch ch1          # 只拼第一章
  python mt_post.py --unit _mt_batch/out/line_1.wav   # 单条试处理
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import ch123_rebuild as RB          # split_at_silence / rms_voiced_db

ROOT = "G:/_setup"
FF = "E:/tool/oopz/ffmpeg.exe"
RAW = os.path.join(ROOT, "_mt_pick")
# 人工裁定过的特例：这里列出的 unit 不走 _mt_pick，直接读指定文件。
# 为什么需要：mt_repick.py --apply / mt_score.py 会按"重心最低"重算并覆盖 _mt_pick，
# 手工替换的音频会被无声撤销（2026-10-26 N0419/N0829）。
OVERRIDE = {
    "N0194": os.path.join(ROOT, "_mt_adv_s2041", "N0194.wav"),
    "N0219": os.path.join(ROOT, "_mt_adv_s2031", "N0219.wav"),
    "N0226": os.path.join(ROOT, "_mt_adv_s2043", "N0226.wav"),
    "N0239": os.path.join(ROOT, "_mt_adv_s2043", "N0239.wav"),
    "N0254": os.path.join(ROOT, "_mt_adv_s2041", "N0254.wav"),
    "N0301": os.path.join(ROOT, "_mt_adv_s2031", "N0301.wav"),
    "N0419": os.path.join(ROOT, "_mt_adv_s2025", "N0419.wav"),
    "N0480": os.path.join(ROOT, "_mt_adv_s2031", "N0480.wav"),
    "N0552": os.path.join(ROOT, "_mt_adv_s2043", "N0552.wav"),
    "N0602": os.path.join(ROOT, "_mt_adv_s2031", "N0602.wav"),
    "N0627": os.path.join(ROOT, "_mt_adv_s2051", "N0627.wav"),
    "N0634": os.path.join(ROOT, "_mt_adv_s2041", "N0634.wav"),
    "N0666": os.path.join(ROOT, "_mt_adv_s2031", "N0666.wav"),
    "N0723": os.path.join(ROOT, "_mt_adv_s2043", "N0723.wav"),
    "N0755": os.path.join(ROOT, "_mt_adv_s2043", "N0755.wav"),
    "N0829": os.path.join(ROOT, "_mt_adv_s2029", "N0829.wav"),
}
PROC = os.path.join(ROOT, "_mt_proc")
OUTD = os.path.join(ROOT, "_mt_out")
TEMPO = 0.80
TARGET_RMS = -20.0      # 真 RMS，与 LUFS −19 附近等价
SR = 48000
SLOWEST, FASTEST = 0.70, 1.00     # 用户红线：tempo 硬夹 [0.70, 1.00]
DEADBAND = 0.04                   # 与 0.8 相差 4% 以内不动（微调必吞词）


def trim(a, sr, lead=0.04, tail=0.06):
    w = int(0.005 * sr)
    first, last = 0, len(a)
    for i in range(0, len(a) - w, w):
        if np.sqrt((a[i:i + w] ** 2).mean()) > 10 ** (-45 / 20):
            first = i
            break
    for i in range(len(a) - w, 0, -w):
        if np.sqrt((a[i:i + w] ** 2).mean()) > 10 ** (-45 / 20):
            last = i + w
            break
    s = max(0, first - int(lead * sr))
    e = min(len(a), last + int(tail * sr))
    y = a[s:e].copy()
    # 首尾 8ms 淡入淡出，避免咔哒
    f = min(int(0.008 * sr), len(y) // 2)
    if f > 4:
        t = np.linspace(0, 1, f, dtype=np.float32)
        y[:f] *= 0.5 - 0.5 * np.cos(np.pi * t)
        y[-f:] *= 0.5 + 0.5 * np.cos(np.pi * t)
    return y


def stretch(a, sr, tempo, tag):
    if abs(tempo - 1.0) < 0.005:
        return a
    src = os.path.join(PROC, "_tmp_%s.wav" % tag)
    dst = os.path.join(PROC, "_tmp_%s_r.wav" % tag)
    sf.write(src, a, sr, subtype="PCM_16")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-af", "rubberband=tempo=%.4f:pitchq=quality" % tempo,
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)
    y, _ = sf.read(dst, dtype="float32", always_2d=True)
    os.remove(src)
    os.remove(dst)
    return y.mean(1)


def vrms(y, sr):
    """有声帧真 RMS（20ms 帧，剔除 <−45dB 的静音帧）。"""
    w = int(0.02 * sr)
    vals = []
    for i in range(0, len(y) - w, w):
        r = np.sqrt((y[i:i + w] ** 2).mean())
        if 20 * np.log10(r + 1e-12) > -45:
            vals.append(r)
    return 20 * np.log10(np.sqrt(np.mean(np.square(vals))) + 1e-12) if vals else -120.0


def limit(y, sr):
    """只削峰的限幅（2ms 起控 / 60ms 释放），不做增益包络整形。"""
    src = os.path.join(PROC, "_lim_in.wav")
    dst = os.path.join(PROC, "_lim_out.wav")
    sf.write(src, y, sr, subtype="PCM_16")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-af", "alimiter=limit=0.89:attack=2:release=60:level=0",
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)
    z, _ = sf.read(dst, dtype="float32", always_2d=True)
    return z.mean(1)


def level(y, sr, target=TARGET_RMS):
    """拉到目标真 RMS；峰值超了就削峰，再迭代补增益（最多 3 轮）。"""
    for _ in range(3):
        g = target - vrms(y, sr)
        if abs(g) < 0.3:
            break
        y = limit((y * 10 ** (g / 20.0)).astype(np.float32), sr)
    return y


def process_one(path, tag, tempo=TEMPO):
    os.makedirs(PROC, exist_ok=True)
    a, sr = sf.read(path, dtype="float32", always_2d=True)
    a = a.mean(1)
    if sr != SR:
        sys.exit("采样率不是 48k: %s" % path)
    y = trim(a, sr)
    y = stretch(y, sr, tempo, tag)
    y = level(y, sr)
    return y, sr


def dur_of(path):
    import wave
    w = wave.open(path)
    d = w.getnframes() / float(w.getframerate())
    w.close()
    return d


def voiced_wpm(path, words):
    """voiced wpm：只算有声帧（>−40dB），剔除 TTS 内部停顿。
    用户口径「根据发音时间，去掉间隔时间，来算」。"""
    import wave
    w = wave.open(path)
    sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    raw = w.readframes(n)
    w.close()
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    win = int(0.02 * sr)
    v = sum(win for i in range(0, len(a) - win, win)
            if np.sqrt((a[i:i + win] ** 2).mean()) > 10 ** (-40 / 20))
    sec = v / float(sr)
    if sec < 0.15:
        return 0.0
    return words / sec * 60.0


def line_tempo(wpm, target, base=1.0):
    """残余微调：t = target / wpm，夹 [0.70, 1.00]。
    t>1 表示本来就够慢 ⇒ 不加快（用户规则）。与 1 差 4% 以内不动（微调必吞词）。"""
    if wpm <= 1 or target <= 1:
        return 1.0
    t = target / wpm
    t = min(FASTEST, max(SLOWEST, t))
    if abs(t - 1.0) < DEADBAND:
        return 1.0
    return t


def build(ch, plan, tempo=TEMPO, out_name=None, uniform=False, fixed=None):
    os.makedirs(PROC, exist_ok=True)
    os.makedirs(OUTD, exist_ok=True)
    items = [p for p in plan if p["ch"] == ch]
    miss = [p["id"] for p in items if not os.path.exists(os.path.join(RAW, p["id"] + ".wav"))]
    if miss:
        print("!! %s 缺 %d 条（%s…），先只拼已生成的" % (ch, len(miss), ",".join(miss[:6])))
        ms = set(miss)
        items = [p for p in items if p["id"] not in ms]
    if not items:
        print("没有可拼的片段")
        return

    tf = os.path.join(ROOT, "_mt_target.json")
    tat = json.load(open(tf, encoding="utf-8")) if os.path.exists(tf) else {}
    target = tat.get(ch, 0)
    wpms = []
    for p in items:
        wpms.append(voiced_wpm(os.path.join(RAW, p["id"] + ".wav"),
                               max(1, len(p["text"].split()))))
    if not target:
        target = float(np.median(wpms)) * tempo
    if uniform:
        print("%s: %d 条  voiced wpm 中位 %.0f  —— 原速模式（tempo 1.00，不拉伸）"
              % (ch, len(items), np.median(wpms)))
    else:
        print("%s: %d 条  voiced wpm 中位 %.0f  目标 %.0f"
              % (ch, len(items), np.median(wpms), target))

    pieces, n, used = [], 0, []
    for p, wpm in zip(items, wpms):
        fp = OVERRIDE.get(p["id"]) or os.path.join(RAW, p["id"] + ".wav")
        t = fixed if fixed else (1.0 if uniform else line_tempo(wpm, target, tempo))
        key = "%s_%d_%d_%03d" % (p["id"], os.path.getsize(fp),
                                 int(os.path.getmtime(fp)), round(t * 100))
        cached = os.path.join(PROC, key + ".wav")
        if os.path.exists(cached):
            y, _ = sf.read(cached, dtype="float32", always_2d=True)
            y = y.mean(1)
        else:
            y, sr = process_one(fp, key, t)
            sf.write(cached, y, SR, subtype="PCM_16")
        pieces.append(y)
        pieces.append(np.zeros(int(p["gap"] * SR), dtype=np.float32))
        used.append((p["id"], t, wpm * t))
        n += 1

    y = np.concatenate(pieces)
    y = level(y, SR)
    name = out_name or ("%s.wav" % ch)
    dst = os.path.join(OUTD, name)
    sf.write(dst, y, SR, subtype="PCM_16")

    fin = np.array([w for _, _, w in used])
    tempos = np.array([t for _, t, _ in used])
    words = sum(len(p["text"].split()) for p in items)
    dur = len(y) / SR
    print("%s: %d 单元 %d 词  %.2f 分钟  %.1f dB RMS  peak %.2f"
          % (ch, n, words, dur / 60, vrms(y, SR), np.abs(y).max()))
    print("    成品 voiced wpm 中位 %.0f / 最快 %.0f / 最慢 %.0f   用时序 tempo %.2f~%.2f（%d 条未拉伸）"
          % (np.median(fin), fin.max(), fin.min(), tempos.min(), tempos.max(),
             (tempos > 0.999).sum()))
    print("    → %s" % dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default=None)
    ap.add_argument("--unit", default=None)
    ap.add_argument("--tempo", type=float, default=TEMPO)
    ap.add_argument("--plan", default="G:/_setup/mt_plan2.json")
    ap.add_argument("--uniform", action="store_true",
                    help="所有条一律 tempo=1.00（原速，不拉伸），不做语速微调")
    ap.add_argument("--out", default=None, help="成品文件名（默认 <ch>.wav），用于不覆盖已交付版本")
    ap.add_argument("--fixed", type=float, default=None,
                    help="所有条统一用这个 tempo（如 0.92），不做逐条微调")
    ap.add_argument("--raw", default=None, help="候选目录，默认 _mt_pick")
    a = ap.parse_args()
    global RAW
    if a.raw:
        RAW = os.path.join(ROOT, a.raw) if not os.path.isabs(a.raw) else a.raw
    if a.unit:
        y, sr = process_one(a.unit, "probe", a.tempo)
        dst = os.path.join(ROOT, "_mt_probe_unit.wav")
        sf.write(dst, y, sr, subtype="PCM_16")
        print("%.2fs  %.1f dB RMS  peak %.2f  → %s"
              % (len(y) / sr, vrms(y, sr), np.abs(y).max(), dst))
        return
    plan = json.load(open(a.plan, encoding="utf-8"))
    for ch in ([a.ch] if a.ch else ["ch1", "ch2", "ch3"]):
        build(ch, plan, a.tempo, out_name=a.out, uniform=a.uniform, fixed=a.fixed)


if __name__ == "__main__":
    main()
