# -*- coding: utf-8 -*-
"""把 demucs 分离出的 vocals 收成可用的 48k 参考，并做「音色是否被伤」的体检。

demucs 输出 44.1k，而 _ref9 那批是 48k；直接替换会让下游重采样多一次。
这里统一重采样回 48k，再做：
  · 掐掉首尾 <−45dBFS 的静音（分离后边界常有残留）
  · 归一到与原参考相同的 voiced RMS（保证音量不变，否则模型会跟着音量变）
  · 与原参考比对 F0 / tilt / 声纹余弦，量化「分离有没有伤到人声」
"""
import argparse
import glob
import io
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
SR = 48000


def load(p, sr=SR):
    y, s = sf.read(p, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(1)
    if s != sr:
        n = int(round(len(y) * sr / s))
        y = np.interp(np.linspace(0, len(y) - 1, n), np.arange(len(y)), y).astype("float32")
    return y


def frame_db(y, fl=0.025, hop=0.010, sr=SR):
    n = 1 + (len(y) - int(fl * sr)) // int(hop * sr)
    fl_, hop_ = int(fl * sr), int(hop * sr)
    idx = np.arange(fl_)[None, :] + hop_ * np.arange(n)[:, None]
    return 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12), hop_


def voiced_rms(y, sr=SR, thr=-45.0):
    db, _ = frame_db(y, sr=sr)
    v = db > max(thr, db.max() - 40)
    if v.sum() == 0:
        return 20 * np.log10(np.sqrt((y ** 2).mean()) + 1e-12)
    fl_ = int(0.025 * sr)
    hop_ = int(0.010 * sr)
    acc = 0.0
    cnt = 0
    for k in np.where(v)[0]:
        seg = y[k * hop_: k * hop_ + fl_]
        acc += float((seg ** 2).sum())
        cnt += len(seg)
    return 20 * np.log10(np.sqrt(acc / max(1, cnt)) + 1e-12)


def trim_sil(y, sr=SR, keep_db=-45.0, pad=0.03):
    db, hop = frame_db(y, sr=sr)
    thr = max(keep_db, db.max() - 45)
    v = np.where(db > thr)[0]
    if len(v) == 0:
        return y
    a = max(0, v[0] * hop - int(pad * sr))
    b = min(len(y), (v[-1] + 1) * hop + int(pad * sr))
    return y[a:b]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sep", default="_sep2")
    ap.add_argument("--src", default="_ref9")
    ap.add_argument("--out", default="_ref9_clean")
    ap.add_argument("--report", default="_ref9_clean.json")
    ap.add_argument("--no-trim", action="store_true", default=True,
                    help="默认不掐首尾：参考的 --prompt-text 必须与音频逐字对应，"
                         "掐掉开头几个弱音会让文本多出内容（实测 Thomas_scold 时长 9.27→7.65s，"
                         "cps 从 12.8 跳到 15.6，属于异常）")
    a = ap.parse_args()

    sep = os.path.join(ROOT, a.sep)
    src = os.path.join(ROOT, a.src)
    out = os.path.join(ROOT, a.out)
    os.makedirs(out, exist_ok=True)

    sys.path.insert(0, ROOT)
    import _calm_gate as CG

    rows = {}
    for d in sorted(glob.glob(os.path.join(sep, "htdemucs", "*"))):
        name = os.path.basename(d)
        vp = os.path.join(d, "vocals.wav")
        op = os.path.join(d, "no_vocals.wav")
        orig = os.path.join(src, name + ".wav")
        if not os.path.exists(vp):
            continue
        # 这条分离会把音乐当人声留下（F0 158→520、tilt 0.193→0.951），
        # 参考本身就废（12.54s 音频只标了 42 字符），跳过分离用原文件
        if name == "Thomas_begging":
            shutil.copyfile(orig, os.path.join(out, name + ".wav"))
            rows[name] = {"skipped_sep": True}
            print("%-22s 跳过分离（分离失败）" % name)
            continue
        y = load(vp)
        if not a.no_trim:
            y = trim_sil(y)
        # 归一到原参考的 voiced RMS
        ref = load(orig) if os.path.exists(orig) else None
        tgt = voiced_rms(ref) if ref is not None else -24.0
        for _ in range(6):
            cur = voiced_rms(y)
            if abs(cur - tgt) <= 0.05:
                break
            y = y * (10 ** ((tgt - cur) / 20.0))
        if np.abs(y).max() > 0.97:
            y = y * (0.97 / np.abs(y).max())

        dst = os.path.join(out, name + ".wav")
        sf.write(dst, y, SR, subtype="PCM_16")

        rec = {"dur": round(len(y) / SR, 2), "rms": round(voiced_rms(y), 2)}
        if os.path.exists(op):
            yo = load(op)
            rec["sep_db"] = round(voiced_rms(y) - voiced_rms(yo), 1)
        if ref is not None:
            m0 = CG.measure(orig, 10, "")
            m1 = CG.measure(dst, 10, "")
            rec.update({
                "F0_before": m0["F0"], "F0_after": m1["F0"],
                "tilt_before": m0["tilt"], "tilt_after": m1["tilt"],
                "dF0": m1["F0"] - m0["F0"],
                "dtilt": round(m1["tilt"] - m0["tilt"], 3),
                "dur_before": m0["dur"], "dur_after": m1["dur"],
            })
        rows[name] = rec
        print("%-22s %6.2fs  sep=%-5s F0 %-4s→%-4s tilt %.3f→%.3f" % (
            name, rec["dur"], rec.get("sep_db", "-"),
            rec.get("F0_before", "-"), rec.get("F0_after", "-"),
            rec.get("tilt_before", 0), rec.get("tilt_after", 0)))

    # 没分离的组直接用原文件（保证 33 组齐全）
    for f in glob.glob(os.path.join(src, "*.wav")):
        n = os.path.basename(f)
        if n[:-4] in rows:
            continue
        shutil.copyfile(f, os.path.join(out, n))
        rows[n[:-4]] = {"copied": True, "dur": round(load(f).size / SR, 2)}

    json.dump(rows, io.open(os.path.join(ROOT, a.report), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出 %d 组 → %s" % (len(rows), out))
    bad = [(k, v) for k, v in rows.items() if abs(v.get("dF0", 0)) > 12 or abs(v.get("dtilt", 0)) > 0.04]
    print("音色变化偏大（|ΔF0|>12Hz 或 |Δtilt|>0.04）: %d" % len(bad))
    for k, v in bad:
        print("   %-22s ΔF0 %+d  Δtilt %+.3f" % (k, v["dF0"], v["dtilt"]))


if __name__ == "__main__":
    main()
