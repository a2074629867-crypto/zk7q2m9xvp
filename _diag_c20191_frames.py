# -*- coding: utf-8 -*-
"""c2_0191 帧级 F0 轮廓对比（不受词级 p50=None 过滤影响）。

词级那张表被过滤器砍掉一半（old 只剩 10/23 词），不能当整句结论。
这里直接用帧级有声数据，按归一化时间对齐两版，看整条轮廓。

输出：
  1. 有声帧覆盖率（F0 可跟踪比例）—— 气声/噪声比例高的物理指标
  2. 轮廓采样：每 5% 时长取一个中位（st，相对句中位），两版并排
  3. 帧级 rho（时间 vs F0）—— 整句该降还是该升
  4. 分段 rho：前半句 / 后半句，看是整句错还是局部错
"""
import io
import json
import os

import librosa
import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
SID = "c2_0191"
SR16 = 16000
HOP = 160
NBIN = 20          # 每 5% 一个点


def f0_frames(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y16 = librosa.resample(y, orig_sr=sr, target_sr=SR16)
    f0, vflag, _ = librosa.pyin(y16, fmin=60, fmax=400, sr=SR16,
                                frame_length=1024, hop_length=HOP)
    ok = vflag & np.isfinite(f0)
    st = 12.0 * np.log2(np.clip(f0, 1e-6, None) / 100.0)
    return st, ok, len(y) / float(sr)


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d > 0 else 0.0


def profile(path):
    st, ok, dur = f0_frames(path)
    n = len(st)
    cover = float(ok.mean())
    idx = np.flatnonzero(ok)
    if len(idx) < 20:
        return dict(note="有声帧不足", cover=cover, dur=dur)

    base = float(np.median(st[ok]))
    tn = np.arange(n) / float(n - 1)                 # 归一化时间 0..1

    bins = []
    for b in range(NBIN):
        lo, hi = b / NBIN, (b + 1) / NBIN
        m = ok & (tn >= lo) & (tn < hi)
        bins.append(round(float(np.median(st[m]) - base), 2) if m.sum() >= 3 else None)

    rho = spearman(tn[ok], st[ok])
    half = n // 2
    m1 = ok.copy()
    m1[half:] = False
    m2 = ok.copy()
    m2[:half] = False
    r1 = spearman(tn[m1], st[m1]) if m1.sum() > 10 else None
    r2 = spearman(tn[m2], st[m2]) if m2.sum() > 10 else None

    return dict(cover=round(cover, 3), dur=round(dur, 2),
                rho=round(rho, 3),
                rho_first=None if r1 is None else round(r1, 3),
                rho_second=None if r2 is None else round(r2, 3),
                base_hz=round(100 * 2 ** (base / 12.0), 1),
                bins=bins)


def main():
    out = {}
    for tag, p in (("old", "_audio_ch123/out"), ("new", "_regen_final")):
        wav = os.path.join(ROOT, p, SID + ".wav")
        if os.path.exists(wav):
            out[tag] = profile(wav)

    print("=== c2_0191 帧级 F0 轮廓（归一化时间，每 5%% 一点，st 相对句中位）===")
    hdr = "%-6s" % "位置"
    for tag in ("old", "new"):
        hdr += "%9s" % tag
    print(hdr)
    bo = (out.get("old") or {}).get("bins") or []
    bn = (out.get("new") or {}).get("bins") or []
    for i in range(NBIN):
        a = bo[i] if i < len(bo) else None
        b = bn[i] if i < len(bn) else None
        print("%-6s%%%7s %8s"
              % (int(100 * i / NBIN),
                 "—" if a is None else "%+.2f" % a,
                 "—" if b is None else "%+.2f" % b))

    print()
    print("%-10s %8s %8s %8s %8s %8s" % ("版", "覆盖率", "rho全句", "rho前半", "rho后半", "中位Hz"))
    for tag in ("old", "new"):
        r = out.get(tag) or {}
        if not r or "rho" not in r:
            print(tag, r.get("note"))
            continue
        print("%-10s %8.3f %8.3f %8s %8s %8.1f"
              % (tag, r["cover"], r["rho"],
                 "—" if r["rho_first"] is None else "%.3f" % r["rho_first"],
                 "—" if r["rho_second"] is None else "%.3f" % r["rho_second"],
                 r["base_hz"]))

    json.dump(out, io.open(os.path.join(ROOT, "_diag_c20191_frames.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n→ G:/_setup/_diag_c20191_frames.json")


if __name__ == "__main__":
    main()
