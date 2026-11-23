# -*- coding: utf-8 -*-
"""asr_venv：逐条 ASR → _ch123_asr.json

    ./asr_venv/Scripts/python.exe ch123_asr.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import onnx_asr
import onnxruntime as ort

import bk_asr_check as B
from ch123_plan import INNER, PLAN

OUT = "G:/_setup/ch123"


def main():
    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
                            quantization="int8", providers=[("CPUExecutionProvider", {})],
                            sess_options=so)
    keys = ["L%03d" % i for i, _, _, _ in PLAN]
    keys += ["I%02d" % i for i in range(len(INNER))]
    res = {}
    for k in sorted(keys):
        p = os.path.join(OUT, k + ".wav")
        if not os.path.exists(p):
            continue
        a, sr = B.rd(p)
        hyp = (m.recognize(B.r16(a, sr)) or "").strip()
        res[k] = hyp
        print("%-5s | %s" % (k, hyp), flush=True)
    json.dump(res, open("G:/_setup/_ch123_asr.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("OK", len(res))


if __name__ == "__main__":
    main()
