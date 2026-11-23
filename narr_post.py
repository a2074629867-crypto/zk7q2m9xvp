# -*- coding: utf-8 -*-
"""旁白后处理链：语速对齐 → 电平归一 →（可选）停顿注入。

## 为什么语速不能在生成端做（2026-11-10 实测 + 源码确认）

dots.tts 的 `<rate>` / `<pause>` 只在 **edit 路径**解析：
    session.cpp  known_edit_container_tag() / render_edit_instruction()
而 `/v1/audio/speech` + `template_name=tts` 走的是 generate_latent_patches()，
**不解析任何标签**。实测（同文本同参考音，narr_mc_1，2 核 CPU）：

    plain            7.52s
    <rate, factor=0.80>  7.52s  ← 字节完全相同 721964，标签被整个丢弃
    <rate, factor=0.70>  8.16s  ← 只有 1.085×，期望 1.43×

服务端也没有 `speed` 参数（model_specs/dots_tts.json 无此项）。
⇒ 语速一律后期 rubberband 整体伸缩，绝不在生成端挂标签。

## 目标语速：追相对起伏，不追参考音的绝对速度（2026-11-10 修正）

原设计 `target = REF_WPM * rate / BASE_RATE` 有个致命问题：实测
参考 narr_mc_1 裁剪后 **90.3 wpm**，模型直出裁剪后 **140.5 wpm**，
固有比值 140.5/90.3 = **1.556**。要命中 90 wpm 需要 tempo 0.643，
低于 0.70 地板 ⇒ 每一段都被夹到 0.70 ⇒ 整条 rate 计划塌成常数，
场景起伏（恐惧慢 / 动作快）全部失效。

所以改成 **tempo = rate**：
    rate 0.72 → 101 wpm    rate 0.80 → 112 wpm    rate 0.84 → 118 wpm
全部落在 [0.70, 1.00]，起伏完整保留，绝对语速 100~118 wpm 是有声书正常区间。
麦康纳的"慢"由停顿与韵律承载（见 mt_final_pause.py），不由绝对 wpm 承载。

## 两条硬约束（都是返工过的）

1. 只用 stretch_whole，不用 stretch_segments —— 段长 <0.4s 造伪影。
2. tempo 硬夹 [0.70, 1.00]，|1-tempo| ≤ 0.045 直接不动原文件。

用法：
    python narr_post.py --in out --out post --plan _castle_en_ch123_plan.jsonl
    python narr_post.py --calib                       # 只标定参考音语速
"""
import argparse
import glob
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB
import ch123_clean as CL

FF = "E:/tool/oopz/ffmpeg.exe"      # 只有这个 build 带 rubberband
TMP = "G:/_setup/_tmp/narr_st"

REF_WAV = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_WORDS = 12
REF_WPM_FALLBACK = 87.0

BASE_RATE = 1.00   # 2026-11-16：0.80 → 1.00。缺 rate 的旁白行按原速，不再默认慢 20%
TEMPO_FLOOR = 0.70
TEMPO_MAX = 1.00
TEMPO_EPS = 0.045          # 4.5% 以内不动
HEAD, TAIL = 0.06, 0.10    # 裁掉模型自带的首尾静音，只留这么点气口


def load(p):
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    return a.mean(1).astype(np.float32), sr


def trim(a, sr):
    """裁首尾静音。模型直出带 0.96s 前导静音，不裁会把 wpm 算低。"""
    segs = RB.split_at_silence(a, sr, min_gap=0.10)
    if not segs:
        return a
    s0 = max(0.0, segs[0][0] - HEAD)
    s1 = min(len(a) / sr, segs[-1][1] + TAIL)
    return a[int(s0 * sr):int(s1 * sr)]


def rate_of(a, sr, n):
    """voiced 语速：按有声段总时长算，不用文件时长（否则前导静音会拉低 wpm）。
    与 ch123_slow5.rate_of 口径一致（min_gap=0.22）。"""
    segs = RB.split_at_silence(a, sr, min_gap=0.22)
    v = sum(b - c for c, b in segs)
    return (n / v * 60 if v > 0 else 0.0), v


def meas(a, sr, words):
    wpm, voiced = rate_of(a, sr, words)
    return dict(wpm=wpm, voiced=voiced, dur=len(a) / sr,
                rms=RB.rms_voiced_db(a, sr), peak=float(np.abs(a).max()))


def stretch(a, sr, tempo, tag):
    """整体 rubberband 伸缩，保音高。"""
    os.makedirs(TMP, exist_ok=True)
    src = os.path.join(TMP, "%s_in.wav" % tag)
    dst = os.path.join(TMP, "%s_out.wav" % tag)
    sf.write(src, a, sr, subtype="PCM_16")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-af", "rubberband=tempo=%.4f:pitchq=quality" % tempo,
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)
    b, _ = sf.read(dst, dtype="float32", always_2d=True)
    return b.mean(1).astype(np.float32)


def calib():
    """参考音的 voiced 语速，作为全篇基准。"""
    if not os.path.exists(REF_WAV):
        print("参考音不存在，用兜底 %.1f wpm" % REF_WPM_FALLBACK)
        return REF_WPM_FALLBACK
    a, sr = load(REF_WAV)
    a = trim(a, sr)
    m = meas(a, sr, REF_WORDS)
    print("参考 narr_mc_1: %.2fs  voiced %.2fs  %.1f wpm  F0 %.0f" % (
        m["dur"], m["voiced"], m["wpm"],
        float(np.median(__import__("parselmouth").Sound(REF_WAV)
                        .to_pitch(pitch_floor=55, pitch_ceiling=350)
                        .selected_array["frequency"][
                            __import__("parselmouth").Sound(REF_WAV)
                            .to_pitch(pitch_floor=55, pitch_ceiling=350)
                            .selected_array["frequency"] > 0]))))
    return m["wpm"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default="G:/_setup/out")
    ap.add_argument("--out", dest="dst", default="G:/_setup/narr_post")
    ap.add_argument("--plan", default="G:/_setup/_castle_en_ch123_plan.jsonl")
    ap.add_argument("--calib", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    ref = calib()
    if a.calib:
        return
    ref = ref or REF_WPM_FALLBACK

    rows = {}
    if os.path.exists(a.plan):
        for line in open(a.plan, encoding="utf-8"):
            r = json.loads(line)
            rows[r["id"]] = r

    os.makedirs(a.dst, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.src, "*.wav")))
    if a.limit:
        files = files[:a.limit]
    if not files:
        print("源目录没有 wav：%s" % a.src)
        return

    print("参考语速 %.1f wpm  基准 rate %.2f  条数 %d" % (ref, BASE_RATE, len(files)))
    print("%-10s %-5s %5s %5s %6s %6s %6s %6s" % (
        "id", "rate", "words", "tempo", "wpm0", "wpm1", "dur0", "dur1"))
    stat = []
    for f in files:
        k = os.path.basename(f)[:-4]
        r = rows.get(k, {})
        words = len(r.get("text", "").split()) or r.get("words") or 0
        if words < 2:
            print("%-10s 跳过（无词数）" % k)
            continue
        rate = float(r.get("rate") or BASE_RATE) if r.get("speaker") == "narrator" else 1.0
        # tempo 直接取 rate：相对起伏保留，绝对语速交给模型（见文件头说明）
        tempo = max(TEMPO_FLOOR, min(TEMPO_MAX, rate))

        x, sr = load(f)
        x = trim(x, sr)
        m0 = meas(x, sr, words)
        if abs(tempo - 1.0) <= TEMPO_EPS:
            tempo, y = 1.0, x
        else:
            y = stretch(x, sr, tempo, k)

        y = CL.clean(y, sr)
        sf.write(os.path.join(a.dst, k + ".wav"), y, sr, subtype="PCM_16")
        m1 = meas(y, sr, words)
        stat.append((m1["rms"], m1["peak"]))
        print("%-10s %-5.2f %5d %6.3f %6.0f %6.0f %6.2f %6.2f" % (
            k, rate, words, tempo, m0["wpm"], m1["wpm"], m0["dur"], m1["dur"]))

    if stat:
        v = [s[0] for s in stat]
        print("\nvoiced RMS %.2f ~ %.2f dB  跨度 %.2f  peak max %.3f  削波 %s" % (
            min(v), max(v), max(v) - min(v), max(s[1] for s in stat),
            "有" if max(s[1] for s in stat) > 0.99 else "无"))


if __name__ == "__main__":
    main()
