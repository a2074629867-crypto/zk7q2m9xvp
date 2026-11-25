# -*- coding: utf-8 -*-
"""_clean_refs_v3.py —— 参考库净化：底噪统一 + 参数统一。

现状（2026-11-24 _ref_audit.py 实测 _ref9_clean 33 条）：
  底噪  −77.3 ~ −37.4 dB  **跨度 39.9 dB**
  SNR    20.4 ~  51.2 dB  **跨度 30.8 dB**
  12/33 条 SNR < 30（不该当参考）
  全部 PCM_16（成品是 PCM_24，位深也不统一）
而 dots.tts 会把参考的噪声底纹一并搬进成品（实测成品 SNR 与参考 SNR 一致），
所以「统一参考」比事后除噪更根本。

目标（与成品同一套标准）：48 kHz / PCM_24 / voiced RMS −24 / 底噪 −72 / peak ≤0.97
红线：**F0 漂移 > 5% 即弃**（改了音高就不是这个角色了）

用法：
  G:/Python310/python.exe _clean_refs_v3.py --in _ref9_clean --out _refs_v3
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _dn_uniform as DU

SR = 48000
FLOOR = -72.0
RMS = -24.0
PEAK = 0.97


def f0med(y, sr):
    if sr != 16000:
        n = int(round(len(y) * 16000 / sr))
        yy = np.interp(np.linspace(0, len(y) - 1, n), np.arange(len(y)), y).astype(np.float32)
    else:
        yy = y
    s = parselmouth.Sound(yy, sampling_frequency=16000)
    f = s.to_pitch(0.01, 75, 600).selected_array["frequency"]
    v = f[f > 0]
    return float(np.median(v)) if len(v) > 5 else 0.0


def resample(y, sr_in, sr_out):
    if sr_in == sr_out:
        return y
    n = int(round(len(y) * sr_out / sr_in))
    t_in = np.arange(len(y)) / sr_in
    return np.interp(np.linspace(0, t_in[-1], n), t_in, y).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="G:/_setup/_ref9_clean")
    ap.add_argument("--out", default="G:/_setup/_refs_v3")
    ap.add_argument("--over", type=float, default=2.0)
    ap.add_argument("--gmin", type=float, default=-24.0)
    ap.add_argument("--f0-tol", type=float, default=0.05)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rep = {}
    print("%-24s %6s %7s %7s %5s %5s %6s %s" %
          ("name", "snr", "floor→", "snr→", "F0", "ΔF0", "peak", "verdict"))
    for p in sorted(glob.glob(os.path.join(a.inp, "*.wav"))):
        name = os.path.basename(p)[:-4]
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        f_before, _, _ = DU.floor_db_of(y, sr)
        s_before = DU.snr_of(y, sr)
        f0_before = f0med(y, sr)

        z, _ = DU.denoise(y, sr, over=a.over, gmin_db=a.gmin, floor_db=FLOOR, gate_rel_db=38.0)
        z = resample(z, sr, SR)
        z = DU.fill_floor(z, SR, floor_db=FLOOR, rel_db=42.0)
        z = DU.norm_rms(z, SR, RMS)
        pk = float(np.abs(z).max())
        if pk > PEAK:
            z = (z * (PEAK / pk)).astype(np.float32)

        f_after, _, _ = DU.floor_db_of(z, SR)
        s_after = DU.snr_of(z, SR)
        f0_after = f0med(z, SR)
        d = abs(f0_after - f0_before) / max(f0_before, 1)
        ok = d <= a.f0_tol and s_after >= 25.0
        verdict = "OK" if ok else ("F0_DRIFT" if d > a.f0_tol else "LOW_SNR")
        print("%-24s %6.1f %7.1f %7.1f %5.0f %4.0f%% %6.2f %s" %
              (name, s_before, f_after, s_after, f0_after, 100 * d,
               float(np.abs(z).max()), verdict))
        if ok:
            sf.write(os.path.join(a.out, name + ".wav"), z, SR, subtype="PCM_24")
        rep[name] = dict(floor_before=round(f_before, 1), floor_after=round(f_after, 1),
                         snr_before=round(s_before, 1), snr_after=round(s_after, 1),
                         f0_before=int(f0_before), f0_after=int(f0_after),
                         f0_drift=round(d, 4), verdict=verdict,
                         dur=round(len(z) / SR, 2))
    json.dump(rep, open("G:/_setup/_refs_v3_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = sum(1 for v in rep.values() if v["verdict"] == "OK")
    print("\n可用 %d / %d  ->  %s" % (ok, len(rep), a.out))


if __name__ == "__main__":
    main()
