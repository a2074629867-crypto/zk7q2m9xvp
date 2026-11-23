"""全库 239 条对白 ASR 转写落盘（asr_venv 下跑）。"""
import glob
import io
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
import _asr_lib

AUD = "G:/_setup/_audio_ch123/out_paused"
OUT = "G:/_setup/_audit_asr.json"

ps = sorted(glob.glob(os.path.join(AUD, "*.wav")))
print("待转写 %d 条" % len(ps), flush=True)
res = {}
for i in range(0, len(ps), 40):
    chunk = ps[i:i + 40]
    r = _asr_lib.transcribe(chunk)
    for p in chunk:
        d = r.get(p) or {}
        res[os.path.basename(p)[:-4]] = {
            "text": d.get("text") or "",
            "dur": d.get("dur"),
            "words": [(w["w"], round(w["start"], 3), round(w["end"], 3)) for w in (d.get("words") or [])],
        }
    print("  %d/%d" % (min(i + 40, len(ps)), len(ps)), flush=True)
json.dump(res, io.open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("写出", OUT, len(res))
