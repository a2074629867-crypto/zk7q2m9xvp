#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按法语字幕时间轴，从电影里切出每个 cue 的音频。

用于找 Charles 的高效价（开心/兴奋）片段当新 ref。
字幕里 '-' 表示换说话人，这类 cue 记 multi=True，后面单独处理。

用法：python castle_cut_cues.py [--only-single]
"""
import argparse, json, os, subprocess
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
MKV = "G:/NEW MOVIE/我是城堡之王/Je.suis.le.seigneur.du.chateau.1989.WEB-DL.1080p.FR.mkv"
HERE = "G:/_setup"
OUT = os.path.join(HERE, "castle_cues")
os.makedirs(OUT, exist_ok=True)


def cut(t0, t1, dst, pad0=0.12, pad1=0.20):
    a = max(0.0, t0 - pad0)
    b = t1 + pad1
    cmd = [FF, "-y", "-v", "quiet", "-ss", "%.3f" % a, "-t", "%.3f" % (b - a),
           "-i", MKV, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst]
    r = subprocess.run(cmd, capture_output=True)
    return os.path.exists(dst) and os.path.getsize(dst) > 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-single", action="store_true")
    ap.add_argument("--min-dur", type=float, default=1.0)
    ap.add_argument("--max-dur", type=float, default=12.0)
    a = ap.parse_args()

    cues = json.load(open(os.path.join(HERE, "castle_srt_cues.json"), encoding="utf-8"))
    todo = [c for c in cues if a.min_dur <= c["dur"] <= a.max_dur]
    if a.only_single:
        todo = [c for c in todo if not c["multi"]]
    print("待切 %d 条" % len(todo), flush=True)

    done = []
    for i, c in enumerate(todo):
        dst = os.path.join(OUT, "c%03d_%05.1f_%05.1f.wav" % (c["i"], c["t0"], c["t1"]))
        if os.path.exists(dst) and os.path.getsize(dst) > 1000:
            done.append(dict(c, path=dst))
            continue
        if cut(c["t0"], c["t1"], dst):
            done.append(dict(c, path=dst))
        if (i + 1) % 50 == 0:
            print("  %d/%d" % (i + 1, len(todo)), flush=True)

    json.dump(done, open(os.path.join(HERE, "castle_cues_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("切出 %d 条 -> castle_cues/" % len(done))


if __name__ == "__main__":
    main()
