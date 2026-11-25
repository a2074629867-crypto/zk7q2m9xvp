# -*- coding: utf-8 -*-
"""_dn_demucs.py —— 参考带噪的成品：demucs 剥人声 + 谱减 + 统一底噪。

为什么需要 demucs：dots.tts 会**完整复制参考音频的噪声底纹**。
实测 c2_0299 底噪 −48.2 dBFS，而与它同源的参考 ref SNR 只有 22~29 dB，
成品 SNR 28.4 —— 一模一样。这就是用户「我明显能听出是参考音频」的物理原因：
噪声的谱形指纹跟着搬过来了。纯谱减只能压 11 dB（−48 → −59），不够。

链路：demucs(htdemucs, two-stems=vocals) → 48k → 谱减 → 统一底噪 −72 → voiced RMS −24
验证：cov 1.000 → 1.000（不吃字）；声纹 intra PASS（sep 0.164 → 0.242）

用法：
  G:/Python310/python.exe _dn_demucs.py --ids c2_0299 --out _dn_v2
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


def resample(y, sr_in, sr_out):
    if sr_in == sr_out:
        return y
    n = int(round(len(y) * sr_out / sr_in))
    t_in = np.arange(len(y)) / sr_in
    t_out = np.linspace(0, t_in[-1], n)
    return np.interp(t_out, t_in, y).astype(np.float32)


def run_demucs(path, torch_home="G:/_setup/models/torch"):
    env = dict(os.environ, TORCH_HOME=torch_home)
    cmd = [PY, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
           "-o", WORK, path]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("demucs 失败: " + r.stderr[-800:])
    base = os.path.splitext(os.path.basename(path))[0]
    return os.path.join(WORK, "htdemucs", base, "vocals.wav")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--in", dest="inp", default=SRC)
    ap.add_argument("--out", default="G:/_setup/_dn_v2")
    ap.add_argument("--floor", type=float, default=-72.0)
    ap.add_argument("--over", type=float, default=2.5)
    ap.add_argument("--gmin", type=float, default=-26.0)
    ap.add_argument("--norm", type=float, default=-24.0)
    ap.add_argument("--sr", type=int, default=48000)
    a = ap.parse_args()

    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    files = ([os.path.join(a.inp, i + ".wav") for i in ids] if ids
             else sorted(glob.glob(os.path.join(a.inp, "*.wav"))))
    os.makedirs(a.out, exist_ok=True)

    rep = {}
    for f in files:
        if not os.path.exists(f):
            print("缺", f)
            continue
        tag = os.path.basename(f)[:-4]
        f0, _, _ = DU.floor_db_of(*sf.read(f, dtype="float32"))
        s0 = DU.snr_of(*sf.read(f, dtype="float32"))
        vp = run_demucs(f)
        y, sr = sf.read(vp, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = resample(np.ascontiguousarray(y), sr, a.sr)
        z, _ = DU.denoise(y, a.sr, a.over, a.gmin, floor_db=a.floor, gate_rel_db=38.0)
        z = DU.fill_floor(z, a.sr, floor_db=a.floor, rel_db=42.0)
        if a.norm:
            z = DU.norm_rms(z, a.sr, a.norm)
            pk = float(np.abs(z).max())
            if pk > 0.97:
                z = z * (0.97 / pk)
        f1, _, _ = DU.floor_db_of(z, a.sr)
        s1 = DU.snr_of(z, a.sr)
        rep[tag] = dict(floor_before=round(f0, 1), floor_after=round(f1, 1),
                        snr_before=round(s0, 1), snr_after=round(s1, 1),
                        peak=round(float(np.abs(z).max()), 3), sr=a.sr,
                        dur=round(len(z) / a.sr, 2))
        print("%-10s 底噪 %6.1f → %6.1f dB    SNR %5.1f → %5.1f   峰值 %.2f  dur %.2f"
              % (tag, f0, f1, s0, s1, rep[tag]["peak"], rep[tag]["dur"]))
        sf.write(os.path.join(a.out, tag + ".wav"), z, a.sr, subtype="PCM_24")
    json.dump(rep, open("G:/_setup/_dn_demucs_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("-> %d 条" % len(rep))


if __name__ == "__main__":
    main()
