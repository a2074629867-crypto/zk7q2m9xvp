# -*- coding: utf-8 -*-
"""_unify_all.py —— 全库参数统一（观感连续的根本手段）。

2026-11-24 实测 239 条对白：
  底噪 > −60 dBFS  : 190 条 (79%)
  SNR < 30 dB      :  54 条 (23%)
  含 >=10ms 数字零 :  95 条 (40%)
  段间底噪跨度 >6dB:  227 条 (95%)，p50 = 34.3 dB
→ 用户说的「参数不统一、观感不连续」在数据上就是这四条。

统一目标（写死，不按条调）：
  采样率 48000 / 位深 PCM_24 / voiced RMS −24.0 dBFS / 底噪 −72 dBFS / peak ≤ 0.97

按底噪分档处理（省时间，demucs 是唯一能压掉「人声里混着的环境噪」的手段）：
  floor > −60 或 SNR < 30  → demucs 人声分离 → 谱减 → 统一底噪
  其余                     → 只统一底噪（语音一帧不动）

用法：
  G:/Python310/python.exe _unify_all.py --ids-file _dlg_ids.txt --out G:/_setup/_unify
"""
import argparse
import glob
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _dn_uniform as DU

SRC = "G:/_setup/_audio_ch123/out"
WORK = "G:/_setup/_dn_demucs"
PY = "G:/Python310/python.exe"
TARGET = dict(sr=48000, floor=-72.0, rms=-24.0, peak_max=0.97)


def resample(y, sr_in, sr_out):
    if sr_in == sr_out:
        return y
    n = int(round(len(y) * sr_out / sr_in))
    t_in = np.arange(len(y)) / sr_in
    return np.interp(np.linspace(0, t_in[-1], n), t_in, y).astype(np.float32)


def run_demucs(path):
    done = os.path.join(WORK, "htdemucs", os.path.basename(path)[:-4], "vocals.wav")
    if os.path.exists(done):
        return done
    env = dict(os.environ, TORCH_HOME="G:/_setup/models/torch")
    r = subprocess.run([PY, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
                        "-o", WORK, path], env=env, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(done):
        raise RuntimeError("demucs: " + (r.stderr or "")[-300:])
    return done


def process(p, use_demucs):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y)
    f0, _, _ = DU.floor_db_of(y, sr)
    s0 = DU.snr_of(y, sr)

    if use_demucs:
        vp = run_demucs(p)
        y, sr = sf.read(vp, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        y = resample(y, sr, TARGET["sr"])
        sr = TARGET["sr"]
        y, _ = DU.denoise(y, sr, over=2.5, gmin_db=-26.0,
                          floor_db=TARGET["floor"], gate_rel_db=38.0)
    else:
        y = resample(y, sr, TARGET["sr"])
        sr = TARGET["sr"]

    y = DU.fill_floor(y, sr, floor_db=TARGET["floor"], rel_db=42.0)
    y = DU.norm_rms(y, sr, TARGET["rms"])
    pk = float(np.abs(y).max())
    if pk > TARGET["peak_max"]:
        y = (y * (TARGET["peak_max"] / pk)).astype(np.float32)
    f1, _, _ = DU.floor_db_of(y, sr)
    return y, sr, dict(floor_before=round(f0, 1), floor_after=round(f1, 1),
                       snr_before=round(s0, 1), snr_after=round(DU.snr_of(y, sr), 1),
                       demucs=bool(use_demucs), peak=round(float(np.abs(y).max()), 3),
                       dur=round(len(y) / sr, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=SRC)
    ap.add_argument("--out", default="G:/_setup/_unify")
    ap.add_argument("--ids-file", default="")
    ap.add_argument("--floor-gate", type=float, default=-60.0)
    ap.add_argument("--snr-gate", type=float, default=30.0)
    ap.add_argument("--force-demucs", action="store_true")
    ap.add_argument("--report", default="G:/_setup/_unify_report.json")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.inp, "*.wav")))
    if a.ids_file:
        ids = [x.strip() for x in open(a.ids_file, encoding="utf-8") if x.strip()]
        want = set(ids)
        files = [f for f in files if os.path.basename(f)[:-4] in want]
    os.makedirs(a.out, exist_ok=True)

    rep = json.load(open(a.report, encoding="utf-8")) if os.path.exists(a.report) else {}
    t0 = __import__("time").time()
    for n, f in enumerate(files, 1):
        tag = os.path.basename(f)[:-4]
        outp = os.path.join(a.out, tag + ".wav")
        if os.path.exists(outp) and tag in rep:
            continue
        try:
            y, sr = sf.read(f, dtype="float32")
            if y.ndim > 1:
                y = y.mean(1)
            fl, _, _ = DU.floor_db_of(np.ascontiguousarray(y), sr)
            sn = DU.snr_of(np.ascontiguousarray(y), sr)
        except Exception as e:
            print("%-9s 读失败 %s" % (tag, e), flush=True)
            continue
        use_dm = a.force_demucs or fl > a.floor_gate or sn < a.snr_gate
        try:
            z, sr, info = process(f, use_dm)
        except Exception as e:
            print("%-9s 处理失败 %s" % (tag, str(e)[:120]), flush=True)
            continue
        sf.write(outp, z, sr, subtype="PCM_24")
        rep[tag] = info
        print("[%3d/%3d %5.1fmin] %-9s %s 底噪 %6.1f→%6.1f  SNR %4.1f→%4.1f" %
              (n, len(files), (__import__("time").time() - t0) / 60, tag,
               "dm" if use_dm else "  ", info["floor_before"], info["floor_after"],
               info["snr_before"], info["snr_after"]), flush=True)
        if n % 10 == 0:
            json.dump(rep, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(rep, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("完成 %d 条 -> %s" % (len(rep), a.report))


if __name__ == "__main__":
    main()
