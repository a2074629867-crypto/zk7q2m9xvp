# -*- coding: utf-8 -*-
"""_elong_vowel.py —— 省略号/破折号处的「自然拖音」：只拉元音，辅音原速，末尾渐弱。

来源（都是本项目 10 月已解决并留下产物的做法，不是我新编的）：
  · `ch123_l078_natural2.py`（2026-10-19）：**只拉元音段**，用 rubberband 而不是 OLA。
    v1 用 OLA 拉 2.65 倍 → F0 抖动 4.0%→49.4%（电音感）；v2 改 rubberband tempo 0.30
    → 0.132s→0.264s，HNR 6.0→6.1dB、F0 抖动 4.0→4.5%，**无损**。
  · `dots_test/tailfix.py`（2026-10-15）：摩擦音/送气尾音（s、sh、f、th、t）单独用 OLA 拉长。
  · 用户定过的规则（`usermemory` 那条）：**省略号 = 自然拖音，只拉元音、辅音原速、末尾渐弱**。

⚠ 明确否掉的路线：dots.tts 的 `<rate>` 词级标签**在本机无效**。
  2026-11-21 实测：factor 0.70 与 1.40 总长同为 5.48s、被点名的 `died` 一直 0.88~0.96s；
  本轮（11-24 21:1x）在 c2_0368 上复测同样无效：

     无标签  4.32s / THINK 200ms
     rate.80 4.00s / THINK 160ms
     rate.60 4.16s / THINK 180ms   ← 数值不参与计算，方向还反了

  所以延长只能走「音频域只拉元音」，不能靠标签。

用法：
  python _elong_vowel.py --id c2_0368
  python _elong_vowel.py --id c2_0368 --word think --tempo 0.45 --gap 0.60
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _align_gate as AG  # noqa: E402

FF = "E:/tool/oopz/ffmpeg.exe"
SR = 48000


def stretch(x, sr, tempo, tag="tmp"):
    i = "G:/_setup/_elong/_%s_in.wav" % tag
    o = "G:/_setup/_elong/_%s_out.wav" % tag
    sf.write(i, x.astype(np.float32), sr, subtype="PCM_16")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", i,
                    "-af", "rubberband=tempo=%.3f:pitchq=quality" % tempo,
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", o], check=True)
    y, _ = sf.read(o, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    return np.ascontiguousarray(y)


def fade(x, sr, ms_in=8, ms_out=8, out_gain=1.0):
    x = x.copy()
    a, b = int(ms_in / 1000 * sr), int(ms_out / 1000 * sr)
    if a > 0 and a < len(x):
        x[:a] *= np.linspace(0, 1, a)
    if 0 < b < len(x):
        x[-b:] *= np.linspace(1.0, out_gain, b)
    return x


def words_of(proc, model, path, text):
    r = AG.align(proc, model, path, text)
    if not r:
        return []
    words, cur = [], []
    for t in r["tokens"]:
        if t["tok"] == "|":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        words.append(cur)
    out = []
    for w in words:
        k = "".join(x["tok"] for x in w)
        out.append((k, w[0]["start"] * 0.02, w[-1]["end"] * 0.02))
    return out


def voiced_run(y, sr, t0, t1):
    """在 [t0,t1] 内找最长连续 voiced 段（元音/鼻音的稳态区）。"""
    s = parselmouth.Sound(y, sampling_frequency=sr)
    p = s.to_pitch(0.01, 75, 500).selected_array["frequency"]
    i0, i1 = int(t0 / 0.01), int(min(t1 / 0.01, len(p)))
    seg = p[i0:i1]
    best, cur = (0, 0), None
    for i, v in enumerate(seg):
        if v > 0:
            if cur is None:
                cur = i
        else:
            if cur is not None and (i - cur) > (best[1] - best[0]):
                best = (cur, i)
            cur = None
    if cur is not None and (len(seg) - cur) > (best[1] - best[0]):
        best = (cur, len(seg))
    if best[1] - best[0] < 5:      # <50ms 不值得拉
        return None
    return i0 * 0.01 + best[0] * 0.01, i0 * 0.01 + best[1] * 0.01


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="c2_0368")
    ap.add_argument("--src", default="")
    ap.add_argument("--word", default="think")
    ap.add_argument("--tempo", type=float, default=0.45, help="越小拉得越长")
    ap.add_argument("--gap", type=float, default=0.60, help="省略号后的停顿目标秒数，0=不动")
    ap.add_argument("--out", default="G:/_setup/_elong")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    src = a.src or "G:/_setup/_audio_ch123/out/%s.wav" % a.id
    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
    text = rows[a.id]["text"]

    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y)
    proc, model = AG.load_model()
    ws = words_of(proc, model, src, text)
    print("词表:", [(w[0], round(w[1], 2), round(w[2], 2)) for w in ws[:5]])

    idx = next((i for i, w in enumerate(ws) if a.word.lower() in w[0].lower()), None)
    if idx is None:
        print("找不到词 %s" % a.word)
        return
    wname, t0, t1 = ws[idx]
    nxt = ws[idx + 1][1] if idx + 1 < len(ws) else None
    vr = voiced_run(y, sr, t0, t1)
    if not vr:
        print("词内找不到 >=50ms 的 voiced 段")
        return
    v0, v1 = vr
    print("%s [%.2f-%.2f]  元音段 [%.2f-%.2f] = %.0fms  下一个词 @%.2f"
          % (wname, t0, t1, v0, v1, (v1 - v0) * 1000, nxt or -1))

    i0, i1 = int(v0 * sr), int(v1 * sr)
    head, vowel, tail = y[:i0], y[i0:i1], y[i1:]
    vz = stretch(vowel, sr, a.tempo, tag="v")
    vz = fade(vz, sr, 6, 18, out_gain=0.72)     # 末尾渐弱
    out = np.concatenate([head, vz, tail])
    print("  元音 %.0fms → %.0fms（x%.2f）" % (len(vowel) / sr * 1000,
                                             len(vz) / sr * 1000,
                                             len(vz) / max(1, len(vowel))))

    # 省略号后的长停顿收短
    if a.gap > 0 and nxt:
        shift = (len(vz) - len(vowel)) / sr
        vent = t1 + shift
        nstart = nxt + shift
        cur_gap = nstart - vent
        if cur_gap > a.gap + 0.05:
            keep_front = int(0.30 * sr)
            keep_back = int(a.gap * sr) - keep_front
            a0 = int(vent * sr)
            a1 = int(nstart * sr)
            out = np.concatenate([out[:a0 + keep_front],
                                  out[max(a0 + keep_front, a1 - keep_back):]])
            print("  停顿 %.2fs → %.2fs" % (cur_gap, a.gap))

    # 归一 voiced RMS −24
    w = int(0.025 * sr)
    n = len(out) // w
    fr = np.sqrt((out[:n * w].reshape(n, w) ** 2).mean(1)) + 1e-12
    db = 20 * np.log10(fr)
    voiced = db[db > np.percentile(db, 97) - 20]
    cur = float(np.mean(voiced))
    out = out * (10 ** ((-24.0 - cur) / 20.0))
    pk = float(np.abs(out).max())
    if pk > 0.97:
        out = out * (0.97 / pk)
    dst = os.path.join(a.out, "%s_elong.wav" % a.id)
    sf.write(dst, out, sr, subtype="PCM_24")
    print("  输出 %s  %.2fs  voicedRMS %.2f  peak %.2f"
          % (dst, len(out) / sr, cur, float(np.abs(out).max())))


if __name__ == "__main__":
    main()
