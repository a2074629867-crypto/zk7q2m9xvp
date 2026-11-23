# -*- coding: utf-8 -*-
"""从一条长音轨里抽一段转写，用来判断「这个文件到底是不是正片」。

假的全片上传（slideshow / 解说 / 预告循环）音频特征很明显：整段只有一个人念稿、
或者大段数字静音。转写出来一看就知道。

用法:
  python asr_probe.py --wav films/wav/rambow.wav --at 1800 --dur 40
"""
import argparse
import sys

import numpy as np
import soundfile as sf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--at", type=float, nargs="+", default=[1800.0], help="起点（秒），可给多个")
    ap.add_argument("--dur", type=float, default=40.0)
    ap.add_argument("--model", default="small.en")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    m = WhisperModel(a.model, device="cpu", compute_type="int8")

    x, sr = sf.read(a.wav, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    print("%s  总长 %.1f 分钟" % (a.wav, len(x) / sr / 60), flush=True)

    for at in a.at:
        t0 = int(at * sr)
        sub = x[t0:t0 + int(a.dur * sr)]
        if len(sub) < sr:
            continue
        rms = np.sqrt((sub ** 2).mean())
        nz = float((np.abs(sub) > 1e-6).mean())
        segs, info = m.transcribe(sub, language="en", vad_filter=True, beam_size=1)
        txt = " ".join(s.text.strip() for s in segs).strip()
        print("\n[%7.1fs] rms %.4f  非零占比 %.2f" % (at, rms, nz), flush=True)
        print("   " + (txt[:400] if txt else "(无语音)"), flush=True)


if __name__ == "__main__":
    main()
