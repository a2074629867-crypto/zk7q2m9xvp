# -*- coding: utf-8 -*-
"""_cov_check.py —— 除噪前后「吃字」验证：同一文本，比 ASR 词覆盖率。

用法：
  G:/Python310/python.exe _cov_check.py --id c2_0299 \
      --text "Oh, yes. Well – a bit. ..." \
      --files a.wav b.wav
"""
import argparse
import difflib
import os
import re
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")

MODEL = "small.en"  # 走 ~/.cache 已有的 CTranslate2 缓存


def words(t):
    return [w.lower() for w in re.findall(r"[A-Za-z']+", t)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--lang", default="en")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    m = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=4)
    ref = words(a.text)
    for f in a.files:
        segs, info = m.transcribe(f, language=a.lang, word_timestamps=False,
                                  vad_filter=False, beam_size=5)
        hyp_t = " ".join(s.text for s in segs)
        hyp = words(hyp_t)
        sm = difflib.SequenceMatcher(a=ref, b=hyp)
        ok, miss, extra = 0, [], []
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                ok += i2 - i1
            else:
                miss += ref[i1:i2]
                extra += hyp[j1:j2]
        cov = ok / max(1, len(ref))
        print("%-46s cov=%.3f (%d/%d) 缺=%s 多=%s" %
              (os.path.basename(os.path.dirname(f)) + "/" + os.path.basename(f),
               cov, ok, len(ref), miss, extra[:6]))
        print("   hyp: %s" % hyp_t.strip()[:200])


if __name__ == "__main__":
    main()
