# -*- coding: utf-8 -*-
"""film_asr.py —— 给没有可用字幕的片子，用 ASR 生成「逐句时间轴」。

为什么需要它
------------
外部下载的字幕经常对不上：实测 Another Year 的 DVD 版 srt 结束在 2:00:45，
而手里 1080p 蓝光版是 2:09:47（差 9 分钟，不同剪辑）。按 cue 窗口测能量
也证明对不齐（cue 窗 −39.3dB vs 随机窗 −42.0dB，只差 2.7dB，等于没对上）。
这种情况下唯一可靠的做法是**从音频本身生成时间轴**。

模型：nemo-parakeet-tdt-0.6b-v3（本机 int8，RTF≈0.07，2 小时片约 9 分钟）
解释器：G:/_setup/asr_venv/Scripts/python.exe（有 onnx_asr + numpy，无 soundfile，用 wave 读）

产物
----
  <out>.srt    可直接喂 cut_cues.py / emo_cut.py
  <out>.json   每句的 t0/t1/text/词数（给后续筛句用）

用法
----
  python film_asr.py --wav G:/MOVIE_DL/_wav/another_year_fc.wav \
      --out G:/MOVIE_DL/_chk/another_year_asr

注意
----
  - 5.1 音轨要先取中置声道，否则对白被摊薄（实测平均到单声道后 RMS 只有 −42dB，
    取 FC 后 −34dB）。命令：ffmpeg -i in.mp4 -vn -af "pan=mono|c0=FC" -ar 16000 out.wav
  - 分块之间留 2s 重叠，丢弃重叠区的词，避免句首被切
"""
import argparse
import json
import os
import wave

import numpy as np
import onnxruntime as ort

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

MODEL = "G:/_setup/models/parakeet-v3-int8"


def read_wav(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    if sw != 2:
        raise SystemExit("只支持 16bit wav：%s" % p)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def tokens_to_words(tokens, ts):
    """parakeet 输出的是子词 token（' car','b','on'），带前导空格的才是新词开头。"""
    words = []
    cur, cur_t = "", None
    for tk, t in zip(tokens, ts):
        new = tk.startswith(" ")
        piece = tk.strip()
        if new and cur:
            words.append((cur, cur_t, tl))
            cur, cur_t = "", t
        if new:
            cur_t = t
        cur += piece
        tl = t
    if cur:
        words.append((cur, cur_t, tl))
    return words


def group(words, gap=0.55, max_dur=12.0, max_words=42, min_words=1):
    out, cur = [], []
    for w, t0, t1 in words:
        if cur:
            if t0 - cur[-1][2] > gap or (t1 - cur[0][1]) > max_dur or len(cur) >= max_words:
                out.append(cur)
                cur = []
        cur.append((w, t0, t1))
    if cur:
        out.append(cur)
    segs = []
    for ws in out:
        if len(ws) < min_words:
            continue
        txt = " ".join(x[0] for x in ws)
        segs.append({"t0": round(ws[0][1], 3), "t1": round(ws[-1][2] + 0.15, 3),
                     "text": txt, "nw": len(ws)})
    return segs


def fmt(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return "%02d:%02d:%02d,%03d" % (h, m, int(s), int(round((s - int(s)) * 1000)) % 1000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--out", required=True, help="输出前缀（不带扩展名）")
    ap.add_argument("--chunk", type=float, default=300.0)
    ap.add_argument("--overlap", type=float, default=2.0)
    ap.add_argument("--gap", type=float, default=0.55, help="词间静音超过这个就断句")
    ap.add_argument("--max-dur", type=float, default=12.0)
    a = ap.parse_args()

    x, sr = read_wav(a.wav)
    dur = len(x) / sr
    print("音轨 %.1f 分钟 sr=%d" % (dur / 60, sr), flush=True)

    so = ort.SessionOptions()
    so.log_severity_level = 3
    import onnx_asr
    m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", MODEL, quantization="int8",
                            providers=[("CPUExecutionProvider", {})], sess_options=so)
    tm = m.with_timestamps()

    allw = []
    pos = 0.0
    n = 0
    while pos < dur - 0.5:
        n += 1
        t_end = min(pos + a.chunk, dur)
        seg = x[int(pos * sr):int(t_end * sr)]
        r = tm.recognize(seg)
        ws = tokens_to_words(r.tokens, r.timestamps)
        # 丢弃落在重叠区（下一块开头 2s）的词
        keep = []
        for w, t0, t1 in ws:
            at = pos + t0
            if t_end < dur and at > t_end - a.overlap:
                continue
            keep.append((w, at, pos + t1))
        allw.extend(keep)
        print("  块 %d  %.0f-%.0fs  词 %d（保留 %d）" % (n, pos, t_end, len(ws), len(keep)), flush=True)
        pos = t_end - a.overlap if t_end < dur else t_end

    allw.sort(key=lambda z: z[1])
    segs = group(allw, gap=a.gap, max_dur=a.max_dur)
    print("总词 %d -> 句 %d" % (len(allw), len(segs)), flush=True)

    with open(a.out + ".srt", "w", encoding="utf-8") as f:
        for i, s in enumerate(segs, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, fmt(s["t0"]), fmt(s["t1"]), s["text"]))
    json.dump({"wav": a.wav, "dur": round(dur, 2), "segs": segs},
              open(a.out + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("-> %s.srt / %s.json" % (a.out, a.out), flush=True)


if __name__ == "__main__":
    main()
