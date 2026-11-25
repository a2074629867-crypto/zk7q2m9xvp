# -*- coding: utf-8 -*-
"""_asr_check_edit.py —— 转写几条短音频，确认 edit 重渲染后文本没被改坏。

只依赖 faster_whisper（asr_venv 里已装），音频直接传路径给它解码。
用法：
  G:/_setup/asr_venv/Scripts/python.exe _asr_check_edit.py a.wav b.wav
"""
import sys
import difflib
import re
import wave

REF = "The third week of term, he had to be ill."


def norm(t):
    return " ".join(re.findall(r"[a-z']+", t.lower()))


def dur(p):
    try:
        w = wave.open(p)
        d = w.getnframes() / float(w.getframerate())
        w.close()
        return d
    except Exception:
        return 0.0


def main():
    from faster_whisper import WhisperModel
    m = WhisperModel("small.en", device="cpu", compute_type="int8")
    ref = norm(REF)
    for p in sys.argv[1:]:
        segs, _ = m.transcribe(p, language="en", vad_filter=False, beam_size=1)
        txt = norm(" ".join(s.text.strip() for s in segs))
        r = difflib.SequenceMatcher(None, ref.split(), txt.split()).ratio()
        print("%-40s %5.2fs  %2d词  sim=%.3f | %s"
              % (p.replace("\\", "/").split("/")[-1], dur(p),
                 len(txt.split()), r, txt), flush=True)


if __name__ == "__main__":
    main()
