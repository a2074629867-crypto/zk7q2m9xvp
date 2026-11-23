# -*- coding: utf-8 -*-
"""_dn_ab.py —— 成品音频「直接除噪」实测：四种方法 vs 原样

目的：用户 2026-11-21 提议「直接全部除噪」。先量清楚：
  ① 底噪能压多少  ② 有声段（气声/齿音/尾音）被削多少  ③ 音量/时长是否漂移

判据（先看数据再决定是否全库推）：
  - floor10 : 帧电平 10 分位（含数字零）
  - sp_rms  : 有声帧（> -45 dBFS）RMS，必须与原样差 ≤0.5 dB（否则等于重新归一化）
  - hf_ratio: 语音帧 6~12 kHz 能量占比变化，跌幅 >15% 说明齿音/气声被吃
  - dur     : 时长变化，>20 ms 说明包络被动过
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

FF = "E:/tool/oopz/ffmpeg.exe"
PY = "G:/Python310/python.exe"
WORK = "G:/_setup"


def load(p):
    y, sr = sf.read(p, dtype="float64", always_2d=True)
    return y.mean(1), sr


def frame_db(y, sr, hop=0.01, win=0.025):
    h, w = int(hop * sr), int(win * sr)
    if len(y) < w:
        return np.array([-120.0])
    n = 1 + (len(y) - w) // h
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    e = np.sqrt((y[idx] ** 2).mean(1)) + 1e-12
    return 20 * np.log10(e)


def band_ratio(y, sr, lo=6000, hi=12000):
    """语音帧上的高频能量占比（用 STFT 近似，整段算）"""
    n = 1024
    if len(y) < n * 2:
        return 0.0
    hop = 256
    frames = 1 + (len(y) - n) // hop
    win = np.hanning(n)
    acc_h = acc_t = 0.0
    f = np.fft.rfftfreq(n, 1 / sr)
    mh = (f >= lo) & (f < hi)
    for i in range(0, frames, 2):
        seg = y[i * hop:i * hop + n] * win
        P = np.abs(np.fft.rfft(seg)) ** 2
        acc_h += P[mh].sum()
        acc_t += P.sum()
    return float(acc_h / max(acc_t, 1e-20))


def stats(p):
    y, sr = load(p)
    db = frame_db(y, sr)
    voiced = db > -45
    sp = db[voiced]
    rms = 20 * np.log10(np.sqrt((y ** 2).mean()) + 1e-12)
    return {
        "dur": round(len(y) / sr, 3),
        "sr": sr,
        "floor10": round(float(np.percentile(db, 10)), 1),
        "floor50": round(float(np.percentile(db, 50)), 1),
        "sp_rms": round(float(np.mean(sp)), 2) if len(sp) else -120.0,
        "peak": round(float(np.abs(y).max()), 3),
        "hf": round(band_ratio(y, sr), 5),
    }


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, (r.stderr or "")[-400:]
    return True, ""


def m_arnndn(src, dst):
    return run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                "-af", "arnndn=m=std.rnnn", "-ar", "48000", dst], cwd=WORK)


def m_afftdn(src, dst):
    return run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                "-af", "afftdn=nr=12:nf=-55:tn=1", "-ar", "48000", dst])


def m_gate(src, dst):
    """_denoise_floor.py 只吃「目录 + ids」，这里临时建单文件目录喂它"""
    import shutil
    import tempfile
    rid = os.path.splitext(os.path.basename(src))[0]
    td = tempfile.mkdtemp(dir=WORK, prefix="_dntmp_")
    od = os.path.join(td, "o")
    shutil.copy2(src, os.path.join(td, rid + ".wav"))
    ok, err = run([PY, "_denoise_floor.py", "--in", td, "--out", od, "--ids", rid,
                   "--mode", "gate", "--report", ""], cwd=WORK)
    if ok:
        got = os.path.join(od, rid + ".wav")
        if os.path.exists(got):
            shutil.move(got, dst)
        else:
            ok, err = False, "no output"
    shutil.rmtree(td, ignore_errors=True)
    return ok, err


def m_demucs(src, dst, outdir):
    ok, err = run([PY, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
                   "--shifts", "3", "--overlap", "0.5", "-o", outdir, src], cwd=WORK)
    if not ok:
        return False, err
    stem = os.path.join(outdir, "htdemucs", os.path.splitext(os.path.basename(src))[0], "vocals.wav")
    if not os.path.exists(stem):
        return False, "no vocals stem"
    y, sr = sf.read(stem, dtype="float64", always_2d=True)
    sf.write(dst, y.mean(1), sr)
    return True, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="c2_0293,c2_0448,c1_0033")
    ap.add_argument("--out", default="G:/_setup/_dn_ab")
    ap.add_argument("--methods", default="arnndn,afftdn,gate,demucs")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    methods = [x.strip() for x in a.methods.split(",") if x.strip()]

    rep = {}
    for rid in ids:
        src = f"G:/_setup/_audio_ch123/out/{rid}.wav"
        if not os.path.exists(src):
            print(f"MISS {rid}", flush=True)
            continue
        base = stats(src)
        rep[rid] = {"src": base, "ver": {}}
        print(f"\n== {rid}  dur {base['dur']} floor10 {base['floor10']} "
              f"sp_rms {base['sp_rms']} hf {base['hf']}", flush=True)
        for m in methods:
            dst = os.path.join(a.out, f"{rid}__{m}.wav")
            if m == "arnndn":
                ok, err = m_arnndn(src, dst)
            elif m == "afftdn":
                ok, err = m_afftdn(src, dst)
            elif m == "gate":
                ok, err = m_gate(src, dst)
            elif m == "demucs":
                ok, err = m_demucs(src, dst, os.path.join(a.out, "_dm"))
            else:
                ok, err = False, "unknown"
            if not ok:
                print(f"  {m:8s} FAIL {err}", flush=True)
                rep[rid]["ver"][m] = {"err": err}
                continue
            s = stats(dst)
            dfloor = s["floor10"] - base["floor10"]
            dsp = s["sp_rms"] - base["sp_rms"]
            dhr = (s["hf"] / base["hf"] - 1) * 100 if base["hf"] else 0
            ddur = (s["dur"] - base["dur"]) * 1000
            rep[rid]["ver"][m] = {**s, "d_floor": round(dfloor, 1), "d_sp": round(dsp, 2),
                                  "d_hf_pct": round(dhr, 1), "d_dur_ms": round(ddur, 1)}
            print(f"  {m:8s} floor10 {s['floor10']:7.1f} ({dfloor:+6.1f})  "
                  f"sp_rms {s['sp_rms']:6.2f} ({dsp:+5.2f})  hf {dhr:+6.1f}%  "
                  f"dur {ddur:+6.1f}ms", flush=True)

    p = os.path.join(WORK, "_dn_ab.json")
    json.dump(rep, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nsaved {p}")


if __name__ == "__main__":
    main()
