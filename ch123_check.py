# -*- coding: utf-8 -*-
"""前三章台词 ASR 校对：判吞字 / 错词。

    asr_venv/Scripts/python.exe ch123_check.py [--all]
输出 G:/_setup/_ch123_check.json
"""
import difflib
import json
import os
import re
import sys

import numpy as np
import onnx_asr
import onnxruntime as ort

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ch123_plan import INNER, PLAN

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

OUT = "G:/_setup/ch123"
ITEMS = [dict(k="L%03d" % i, who=w, emo=e, text=t) for i, w, e, t in PLAN]
ITEMS += [dict(k="I%02d" % i, who=w, emo=e, text=t) for i, (_, w, e, t) in enumerate(INNER)]

# 允许的口音/专名偏差（不算错）
SOFT = ("vincent", "vicence", "kingshaw", "king shaw", "scaredy", "scarity",
        "scardy", "mummy", "mommy", "warings", "edmund", "moth", "battle")


def norm(s):
    s = s.lower().replace("’", "'").replace("‘", "'")
    s = re.sub(r"[^a-z' ]+", " ", s)
    return [w for w in s.split() if w]


def rd(p):
    import wave
    with wave.open(p, "rb") as w:
        sr, ch, nf = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def r16(a, sr):
    if sr == 16000:
        return a
    n = int(round(len(a) * 16000 / sr))
    return np.interp(np.linspace(0, len(a) - 1, n),
                     np.arange(len(a), dtype=np.float64), a).astype(np.float32)


def main():
    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
                            quantization="int8",
                            providers=[("CPUExecutionProvider", {})], sess_options=so)
    res = {}
    for it in ITEMS:
        p = os.path.join(OUT, it["k"] + ".wav")
        if not os.path.exists(p):
            continue
        a, sr = rd(p)
        hyp = (m.recognize(r16(a, sr)) or "").strip()
        rw, hw = norm(it["text"]), norm(hyp)
        sm = difflib.SequenceMatcher(None, rw, hw)
        miss = 0
        bad = []
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                continue
            rs, hs = " ".join(rw[i1:i2]), " ".join(hw[j1:j2])
            joined = (rs + " " + hs).lower()
            soft = any(k in joined for k in SOFT)
            # 拼写变体（quarrelled/quarreled、colour/color）不算错
            if not soft and op == "replace" and rs and hs:
                r1, h1 = rs.split(), hs.split()
                if len(r1) == len(h1):
                    sims = [difflib.SequenceMatcher(None, x, y).ratio() for x, y in zip(r1, h1)]
                    if sum(sims) / len(sims) >= 0.78:
                        soft = True
            if op == "delete":
                miss += i2 - i1
            if soft:
                bad.append(dict(op=op, ref=rs, asr=hs, soft=True))
            else:
                bad.append(dict(op=op, ref=rs, asr=hs, soft=False))
        hard = [b for b in bad if not b["soft"]]
        acc = sm.ratio()
        # 判定：缺 2 词以上 / 有硬错 / 词准 < 72%
        need = (miss >= 2) or bool(hard) or acc < 0.72
        res[it["k"]] = dict(who=it["who"], emo=it["emo"], text=it["text"], dur=round(len(a) / sr, 2),
                            acc=round(acc * 100), miss=miss, asr=hyp,
                            bad=bad, need_retry=need)
        flag = "RETRY" if need else "ok   "
        print("%s %-5s %-11s %3d%% miss=%d  %s" %
              (flag, it["k"], it["emo"] or "-", acc * 100, miss,
               "; ".join("%s[%s]->[%s]" % (b["op"][:3], b["ref"], b["asr"]) for b in hard)[:80]),
              flush=True)
    json.dump(res, open("G:/_setup/_ch123_check.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    n = sum(1 for v in res.values() if v["need_retry"])
    print("\n共 %d 条，需重生成 %d 条" % (len(res), n))


if __name__ == "__main__":
    main()
