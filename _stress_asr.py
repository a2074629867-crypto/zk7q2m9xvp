# -*- coding: utf-8 -*-
"""_stress_asr.py —— 导出词级时间戳（重音实验用，asr_venv 跑）。

用法：
  /g/_setup/asr_venv/Scripts/python.exe _stress_asr.py --ch ch1 --seeds 42,1234,rate
输出 _stress_words.json（断点续跑，每 25 条落盘）
"""
import argparse
import json
import os
import sys
import wave

import numpy as np
import onnxruntime as ort
import onnx_asr

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

ROOT = "G:/_setup"
OUT = os.path.join(ROOT, "_stress_words.json")


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
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


def to_words(tokens, ts, dur):
    out = []
    for tk, t in zip(tokens, ts):
        if tk.startswith(" ") or not out:
            out.append([tk.strip(), t])
        elif all(not c.isalnum() for c in tk):
            out.append([tk.strip(), t])
        else:
            out[-1][0] += tk
    for i in range(len(out) - 1):
        out[i].append(out[i + 1][1])
    out[-1].append(dur)
    return [dict(w=w, start=round(s, 3), end=round(e, 3)) for w, s, e in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--seeds", default="42,1234,rate")
    a = ap.parse_args()

    plan = {p["id"]: p for p in json.load(open(os.path.join(ROOT, "mt_plan3b.json"), encoding="utf-8"))
            if p["ch"] == a.ch}
    seeds = [s.strip() for s in a.seeds.split(",")]
    jobs = []
    for uid in plan:
        for s in seeds:
            fp = os.path.join(ROOT, "_mt_raw_s" + s, uid + ".wav")
            if os.path.exists(fp):
                jobs.append((uid, s, fp))

    done = {}
    if os.path.exists(OUT):
        done = json.load(open(OUT, encoding="utf-8"))
    todo = [j for j in jobs if j[2] not in done]
    print("总 %d 条，已完成 %d，待跑 %d" % (len(jobs), len(done), len(todo)), flush=True)
    if not todo:
        return

    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
                            quantization="int8", providers=[("CPUExecutionProvider", {})],
                            sess_options=so)
    tm = m.with_timestamps()

    for k, (uid, s, fp) in enumerate(todo, 1):
        try:
            y, sr = rd(fp)
            dur = len(y) / sr
            r = tm.recognize(r16(y, sr))
            done[fp] = dict(uid=uid, seed=s, dur=round(dur, 3),
                            text=r.text, words=to_words(r.tokens, r.timestamps, dur))
        except Exception as e:
            done[fp] = dict(uid=uid, seed=s, error=str(e))
        if k % 25 == 0:
            json.dump(done, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("  %d/%d" % (k, len(todo)), flush=True)

    json.dump(done, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("完成 %d 条 -> %s" % (len(done), OUT))


if __name__ == "__main__":
    main()
