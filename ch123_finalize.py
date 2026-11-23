# -*- coding: utf-8 -*-
"""汇总前三章 60 条的最终状态 → _ch123_final.json

    ./asr_venv/Scripts/python.exe ch123_finalize.py

字段：who / emo / text / dur / wpm / vwpm / f0 / tail / spk / acc / asr / split
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import onnx_asr
import onnxruntime as ort

import ch123_probe as P
from ch123_plan import INNER, PLAN, REFS

OUT = "G:/_setup/ch123"
PY = "C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
SPK = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/spk_embed.py"
ANCHOR = {"C": "G:/_setup/castle_fr_ref/CH_neutral.wav",
          "E": "G:/_setup/castle_fr_ref/6_hooper_calm.wav"}


def norm(s):
    s = s.lower().replace("’", "'").replace("‘", "'")
    s = re.sub(r"[^a-z' ]+", " ", s)
    return [w for w in s.split() if w]


def main():
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import ch123_fixlist as L
    fixmap = {}

    def rec(key, emo=None, parts=None, seed=42):
        fixmap[key] = dict(emo=emo, parts=parts, seed=seed)
    L.apply(rec)

    items = [dict(k="L%03d" % i, who=w, text=t) for i, w, e, t in PLAN]
    items += [dict(k="I%02d" % i, who=it[1], text=it[3]) for i, it in enumerate(INNER)]
    items.sort(key=lambda x: x["k"])

    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
                            quantization="int8", providers=[("CPUExecutionProvider", {})],
                            sess_options=so)

    # 声纹：按角色批量
    spk = {}
    for who, anchor in ANCHOR.items():
        files = [os.path.join(OUT, it["k"] + ".wav") for it in items if it["who"] == who]
        files = [f for f in files if os.path.exists(f)]
        if not files:
            continue
        r = subprocess.run([PY, SPK, "--cmn", anchor] + files, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        for line in r.stdout.splitlines():
            mm = re.match(r"^([LI]\d+)\.wav\s+([0-9.]+)", line.strip())
            if mm:
                spk[mm.group(1)] = float(mm.group(2))

    res = {}
    for it in items:
        k = it["k"]
        p = os.path.join(OUT, k + ".wav")
        if not os.path.exists(p):
            continue
        a, sr = P.read_wav(p)
        words = len(it["text"].split())
        pr = P.probe(p, words)
        hyp = ""
        try:
            import ch123_check as C
            hyp = (m.recognize(C.r16(a, sr)) or "").strip()
        except Exception as e:
            print("asr skip", k, e)
        rw, hw = norm(it["text"]), norm(hyp)
        import difflib
        acc = int(difflib.SequenceMatcher(None, rw, hw).ratio() * 100) if hyp else 0
        fx = fixmap.get(k, {})
        emo = "拆句" if fx.get("parts") else (fx.get("emo") if "emo" in fx else None)
        res[k] = dict(who=it["who"], text=it["text"],
                      emo=emo, fixed=bool(fx), split=bool(fx.get("parts")),
                      dur=round(pr["dur"], 2), wpm=round(pr["wpm"] or 0),
                      vwpm=round(pr["vwpm"] or 0), f0=round(pr["f0"], 1),
                      tail=round(pr["tail"], 1) if pr["tail"] is not None else None,
                      spk=round(spk.get(k, 0), 2), acc=acc, asr=hyp)
        print("%-5s %-6s %-11s %5.2fs %4d wpm  声纹 %.2f  词准 %d%%" %
              (k, it["who"], emo or "-", pr["dur"], pr["wpm"] or 0, spk.get(k, 0), acc), flush=True)

    json.dump(res, open("G:/_setup/_ch123_final.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("OK", len(res))


if __name__ == "__main__":
    main()
