# -*- coding: utf-8 -*-
"""chapter_repause.py —— 用「按标点」规则重做整章停顿并重新拼接。

不需要重新生成音频：直接用 chapter1/audio/raw/cNN.wav + chunks.json 的文本，
调用 pause_by_punct 的同一套逻辑，再按原方式拼接（块间 1.6s 真人静音，首尾 0.4s）。

用法:
  python chapter_repause.py [--scale 1.0] [--max-gap 2.0] [--tag punct]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 48000
ROOT = Path("G:/_setup/chapter1")
AUD = ROOT / "audio"
DONOR = "E:/tts-models/acpp/out/calmdeep_final/real_trim.wav"
PY = "G:/Python310/python.exe"


def load(p):
    x, sr = sf.read(str(p), dtype="float64", always_2d=True)
    x = x.mean(1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = np.gcd(int(sr), SR)
        x = resample_poly(x, SR // g, sr // g)
    return x


def donor_gap(seconds):
    d = load(DONOR)
    hop = int(SR * 0.010)
    n = len(d) // hop
    db = 20 * np.log10(np.sqrt((d[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() - 35.0)
    best, cur, bs = 0, 0, 0
    for i, v in enumerate(m):
        if not v:
            cur += 1
            if cur > best:
                best, bs = cur, i - cur + 1
        else:
            cur = 0
    a = int((bs + best / 2 - seconds / 2 / 0.01) * 0.01 * SR)
    seg = d[a: a + int(seconds * SR)].copy()
    nf = int(0.008 * SR)
    if len(seg) > nf:
        seg[:nf] *= np.linspace(0, 1, nf)
        seg[-nf:] *= np.linspace(1, 0, nf)
    return seg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--max-gap", type=float, default=2.0)
    ap.add_argument("--tag", default="punct")
    ap.add_argument("--chunk-gap", type=float, default=1.6)
    a = ap.parse_args()

    chunks = json.load(open(AUD / "chunks.json", encoding="utf-8"))
    outdir = AUD / ("fix_" + a.tag)
    outdir.mkdir(parents=True, exist_ok=True)
    txtdir = ROOT / ("txt_" + a.tag)
    txtdir.mkdir(parents=True, exist_ok=True)

    parts, done = [], []
    for c in chunks:
        i = c["idx"]
        raw = AUD / "raw" / ("c%02d.wav" % i)
        if not raw.exists():
            print("MISS raw c%02d" % i)
            continue
        tp = txtdir / ("c%02d.txt" % i)
        tp.write_text(c["text"], encoding="utf-8")
        op = outdir / ("c%02d.wav" % i)
        rp = outdir / ("c%02d.json" % i)
        cmd = [PY, "G:/_setup/pause_by_punct.py", "--gen", str(raw), "--text", str(tp),
               "--donor", DONOR, "--out", str(op), "--report", str(rp),
               "--scale", str(a.scale), "--max-gap", str(a.max_gap)]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = [l for l in (p.stdout or "").splitlines() if l.strip()]
        line = tail[-1] if tail else "(no output)"
        if not op.exists():
            print("FAIL c%02d: %s" % (i, (p.stderr or "")[-200:]))
            continue
        print("c%02d %s" % (i, line))
        parts.append(load(op))
        done.append(dict(idx=i, dur=round(len(parts[-1]) / SR, 2)))

    if not parts:
        raise SystemExit("没有可用块")

    gap = donor_gap(a.chunk_gap)
    seq = []
    for k, x in enumerate(parts):
        seq.append(x)
        if k != len(parts) - 1:
            seq.append(gap.copy())
    full = np.concatenate(seq)
    pad = np.zeros(int(0.4 * SR))
    full = np.concatenate([pad, full, pad])
    dst = AUD / ("chapter1_%s_%.1fs.wav" % (a.tag, len(full) / SR))
    sf.write(str(dst), full.astype(np.float32), SR, subtype="PCM_16")
    print("\n块 %d/%d  →  %s  (%.2fs = %.1f 分钟)" % (
        len(parts), len(chunks), dst.name, len(full) / SR, len(full) / SR / 60))
    json.dump(dict(tag=a.tag, scale=a.scale, max_gap=a.max_gap, out=str(dst),
                   dur=round(len(full) / SR, 2), blocks=done),
              open(AUD / ("chapter_%s.json" % a.tag), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
