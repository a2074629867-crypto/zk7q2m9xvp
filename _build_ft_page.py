# -*- coding: utf-8 -*-
"""假尾修复 A/B 试听页：A=修复前（备份），B=修复后（现用）。"""
import os, json, base64
import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
BAK = os.path.join(ROOT, "_bak_falsetail_1124")
NOW = os.path.join(ROOT, "_audio_ch123", "out")
ROWS = json.load(open(os.path.join(ROOT, "_fix_falsetail.json"), encoding="utf-8"))
PLAN = {json.loads(l)["id"]: json.loads(l)
        for l in open(os.path.join(ROOT, "_dlg_plan_v2.jsonl"), encoding="utf-8")}


def wav_b64(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    b = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
    import io as _io
    import wave
    buf = _io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b)
    return base64.b64encode(buf.getvalue()).decode()


def env(y, n=160):
    if len(y) < n:
        return [0.0] * n
    k = len(y) // n
    e = np.array([np.abs(y[i * k:(i + 1) * k]).max() for i in range(n)])
    m = e.max() or 1.0
    return [round(float(x / m), 3) for x in e]


data = []
for r in ROWS:
    rid = r["id"]
    a = os.path.join(BAK, rid + ".wav")
    b = os.path.join(NOW, rid + ".wav")
    if not (os.path.exists(a) and os.path.exists(b)):
        continue
    ya, sr = sf.read(a, dtype="float32")
    yb, _ = sf.read(b, dtype="float32")
    if ya.ndim > 1:
        ya = ya.mean(1)
    if yb.ndim > 1:
        yb = yb.mean(1)
    p = PLAN.get(rid, {})
    data.append({"id": rid, "who": p.get("who", ""), "emo": p.get("emo", ""),
                 "text": p.get("text", ""), "ops": "; ".join(r["ops"]),
                 "da": round(len(ya) / sr, 2), "db": round(len(yb) / sr, 2),
                 "ea": env(ya), "eb": env(yb),
                 "a": wav_b64(a), "b": wav_b64(b)})
print("rows", len(data))
tpl = open(os.path.join(ROOT, "_ft_tpl.html"), encoding="utf-8").read()
html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
open(os.path.join(ROOT, "_ft_page.html"), "w", encoding="utf-8").write(html)
print("wrote _ft_page.html %.2f MB" % (len(html) / 1048576))
