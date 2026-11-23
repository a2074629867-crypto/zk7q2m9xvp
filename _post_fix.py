# -*- coding: utf-8 -*-
"""_post_fix.py —— 交付前的两步纯剪辑修整（不降速、不插停顿、不改音色）。

用户 2026-11-21：
  「把生成完的语音去掉底噪再加入停顿，就不会很明显了」
  「或者把原来一开始的长停顿去掉，就是无用的长停顿去掉，就是模型自己生成的」

实测发现库里有两类真正的毛病，一步一件事：

1. **数字静音（死寂）**：105/239 条里有 ≥0.10s 的**全零采样**（最长 0.68s）。
   全零是 −inf dBFS，语音段底噪是 −58 dBFS，落差 58 dB —— 耳朵听到的是
   「嘶——/真空/嘶——」，这就是「停顿太空、没有呼吸感」的直接来源。
   ⇒ 用**该文件自己的**底噪（第 10 百分位那段非零帧）循环填进去，电平对齐本地底噪。

2. **模型自己的长停顿**：13 条有 0.65~1.69s 的句内停顿。
   ⇒ 中间整段剪掉、剩 0.38s，两端各留 0.19s；接缝落在噪声里，12ms 等功率交叉淡化。
   （只剪不插 —— 插停顿那版已被用户否掉）

顺序：先填底噪，再剪停顿 —— 反过来剪完会留下新的边界，填不干净。
最后统一归一到 voiced RMS −24 dBFS（跨度 ≤1dB）。

用法：
  G:/Python310/python.exe _post_fix.py --in _audio_ch123/out_paused \
      --out _audio_ch123/out_final --probe
  G:/Python310/python.exe _post_fix.py --in ... --out ... --ids a,b
"""
import argparse
import glob
import json
import os

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
sys_path = os.path.join(ROOT)
import sys
sys.path.insert(0, sys_path)
from _shorten_pause import join_cf, voiced_runs  # noqa: E402


def frame_db(y, sr, hop=0.01, win=0.025):
    h, w = int(hop * sr), int(win * sr)
    n = 1 + max(0, (len(y) - w) // h)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    return 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12), h, w


def zero_runs(y, sr, min_len=0.03):
    z = (y == 0).astype(np.int8)
    d = np.diff(np.concatenate([[0], z, [0]]))
    s, e = np.where(d == 1)[0], np.where(d == -1)[0]
    return [(a, b) for a, b in zip(s, e) if (b - a) / sr >= min_len]


def pick_donor(y, sr, want=0.30):
    """从文件自己身上取一段「最安静的底噪」当填充素材。"""
    db, h, w = frame_db(y, sr)
    nz = [k for k in range(len(db)) if y[k * h:k * h + w].any()]
    if not nz:
        return None
    vals = sorted(db[k] for k in nz)
    lo = vals[max(0, int(0.10 * len(vals)))]
    cand = [k for k in nz if abs(db[k] - lo) < 2.0]
    if not cand:
        cand = nz[: max(1, len(nz) // 20)]
    k0 = cand[len(cand) // 2]
    n = int(want * sr)
    a = k0 * h
    seg = y[a:a + n]
    if len(seg) < n // 2:
        return None
    if not seg.any():
        return None
    return seg.copy()


def fill_zeros(y, sr, min_len=0.03):
    runs = zero_runs(y, sr, min_len)
    if not runs:
        return y, 0, []
    donor = pick_donor(y, sr)
    if donor is None:
        return y, 0, []
    y = y.copy()
    fade = max(8, int(0.008 * sr))
    info = []
    for a, b in runs:
        n = b - a
        rep = int(np.ceil(n / len(donor)))
        seg = np.tile(donor, rep)[:n]
        # 电平对齐：让填充段的 RMS 等于该文件底噪
        tgt = np.sqrt((donor ** 2).mean())
        cur = np.sqrt((seg ** 2).mean()) + 1e-12
        seg = (seg * (tgt / cur)).astype(np.float32)
        if n > 2 * fade:
            seg[:fade] *= np.linspace(0, 1, fade)
            seg[-fade:] *= np.linspace(1, 0, fade)
        y[a:b] = seg
        info.append(round(n / sr, 2))
    return y, len(runs), info


def voiced_rms_db(y, sr):
    runs = voiced_runs(y, sr)
    if not runs:
        return 0.0
    acc, n = 0.0, 0
    for a, b in runs:
        seg = y[a:b]
        acc += float((seg ** 2).sum())
        n += len(seg)
    return 20 * np.log10(np.sqrt(acc / max(1, n)) + 1e-12)


def norm24(y, sr, target=-24.0):
    for _ in range(6):
        lv = voiced_rms_db(y, sr)
        y = (y * 10 ** ((target - lv) / 20.0)).astype(np.float32)
        if abs(voiced_rms_db(y, sr) - target) <= 0.05:
            break
    p = float(np.abs(y).max())
    if p > 0.98:
        y = (y * (0.98 / p)).astype(np.float32)
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(ROOT, "_audio_ch123", "out_paused"))
    ap.add_argument("--out", default=os.path.join(ROOT, "_audio_ch123", "out_final"))
    ap.add_argument("--ids", default="")
    ap.add_argument("--min-gap", type=float, default=0.65)
    ap.add_argument("--target", type=float, default=0.38)
    ap.add_argument("--no-fill", action="store_true")
    ap.add_argument("--no-shorten", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--report", default=os.path.join(ROOT, "_post_fix_report.json"))
    a = ap.parse_args()

    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    files = ([os.path.join(a.inp, i + ".wav") for i in ids] if ids
             else sorted(glob.glob(os.path.join(a.inp, "*.wav"))))
    if not a.probe:
        os.makedirs(a.out, exist_ok=True)

    from _shorten_pause import shorten

    rep, changed = {}, 0
    for f in files:
        if not os.path.exists(f):
            print("缺", os.path.basename(f))
            continue
        y, sr = sf.read(f, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        d0 = len(y) / sr
        zruns = zero_runs(y, sr)
        nf = 0
        # 顺序：先剪、后填。
        # 反过来的话，填充会把静音抬到 −57.5 dBFS，自适应/绝对阈值下量出来的
        # 停顿长度都会变（实测 0.74s 被量成 0.24s），该剪的没剪却显示「变短了」。
        # 先剪：在原始信号上判定停顿边界最干净；再填：把剪完剩下的全零补齐底噪。
        y2, cuts = (y, []) if a.no_shorten else shorten(y, sr, a.min_gap, a.target)
        if not a.no_fill:
            y2, nf, zinfo = fill_zeros(y2, sr)
        d1 = len(y2) / sr
        tag = os.path.basename(f)[:-4]
        rep[tag] = dict(dur_before=round(d0, 2), dur_after=round(d1, 2),
                        zero_runs=len(zruns), filled=nf,
                        cuts=[{"gap": g, "to": t} for _, _, g, t in cuts])
        if not zruns and not cuts:
            continue
        out = norm24(y2, sr) if not a.probe else y2
        changed += 1
        if not a.probe:
            sf.write(os.path.join(a.out, os.path.basename(f)), out, sr, subtype="PCM_16")
        print("%-9s %.2f→%.2f  填 %d 段静音  剪 %d 处 %s" % (
            tag, d0, d1, nf, len(cuts), [c[2] for c in cuts]))

    if a.report:
        json.dump(rep, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n%d 条，需要处理 %d 条%s" % (len(rep), changed,
                                       "（probe 未写文件）" if a.probe else ""))


if __name__ == "__main__":
    main()
