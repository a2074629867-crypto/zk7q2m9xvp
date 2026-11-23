# -*- coding: utf-8 -*-
"""验证 wrong_speaker 是真错还是判据失效：比对生成音频 f0 与各角色参考 f0 分布。"""
import json, io, sys, os
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/voice_lib")

import wave

def load(p):
    with wave.open(p, "rb") as w:
        sr = w.getframerate(); n = w.getnframes(); ch = w.getnchannels()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32)
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    return x / 32768.0, sr

def f0med(x, sr, fmin=70, fmax=420):
    hop = int(0.02 * sr); win = int(0.04 * sr)
    vals = []
    for i in range(0, len(x) - win, hop):
        f = x[i:i + win]
        if np.sqrt((f ** 2).mean()) < 0.01:
            continue
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[win - 1:]
        lo, hi = int(sr / fmax), int(sr / fmin)
        if hi >= len(ac):
            continue
        seg = ac[lo:hi]
        k = int(np.argmax(seg)) + lo
        if ac[k] <= 0.25 * ac[0]:
            continue
        vals.append(sr / k)
    return float(np.median(vals)) if vals else 0.0

lib = json.load(open("G:/_setup/_emo_refs_all.json", encoding="utf-8"))
print("=== 各角色参考 f0 ===")
rolef0 = {}
for role, emos in lib.items():
    for emo, lst in emos.items():
        for it in lst:
            p = it["path"].replace("\\", "/")
            if not os.path.exists(p):
                print("  MISSING", p); continue
            x, sr = load(p)
            v = f0med(x, sr)
            rolef0.setdefault(role, []).append(v)
for role, vs in rolef0.items():
    vs = [v for v in vs if v > 0]
    print("  %-9s n=%-3d f0 p10=%.0f med=%.0f p90=%.0f" % (
        role, len(vs), np.percentile(vs, 10), np.median(vs), np.percentile(vs, 90)))

gate = json.load(open("G:/_setup/_gate_dlg.json", encoding="utf-8"))
rows = gate if isinstance(gate, list) else gate["rows"]
print("\n=== 被判 wrong_speaker 的生成音频 f0 vs 声明角色 ===")
bad = []
for r in rows:
    if any(isinstance(x, dict) and x.get("code") == "wrong_speaker" for x in (r.get("reasons") or [])):
        p = os.path.join(r"G:/_setup/_audio_ch123/out", r["wav"]).replace("\\", "/")
        if not os.path.exists(p):
            bad.append((r, None)); continue
        x, sr = load(p)
        bad.append((r, f0med(x, sr)))

ok = [(r, f) for r, f in bad if f]
print("可测 %d / %d" % (len(ok), len(bad)))
for role in ("Charles", "Thomas", "Joseph", "Helena"):
    vs = [f for r, f in ok if r["who"] == role]
    if vs:
        print("  声明 %-8s n=%-3d f0 med=%.0f   (该角色参考 med=%.0f)" % (
            role, len(vs), np.median(vs), np.median([v for v in rolef0[role] if v > 0])))
print("\n逐条（声明角色 f0 / 质心判成谁）:")
for r, f in ok[:60]:
    s = r.get("spk") or {}
    print("  %-9s who=%-8s f0=%5.0f  cen_top=%-8s gap=%.3f" % (
        r["id"], r["who"], f, s.get("cen_top"), float(s.get("cen_gap") or 0)))
