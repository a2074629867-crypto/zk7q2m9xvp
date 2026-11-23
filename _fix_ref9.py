# -*- coding: utf-8 -*-
"""_fix_ref9.py —— 重建「去掉借用段」的净化参考（只针对 Joseph_normal / Joseph_nervous）

为什么
------
`_sweep/clean118` 用 `_ref9_clean` 重生成后：
  · w2v 覆盖率中位 1.000 → **0.829**，60 条变差、54 条差 >0.1
  · **17 条 lead（把参考里的话念进正文），全部是 Joseph**
诊断：`_index_srt.json` 里 Joseph_normal / Joseph_nervous 各借了 4.96s 的
`Joseph_wronged_c042.wav`（"She was looking at me as if she was sorry for me."）。
原来参考带配乐、模型听不清；demucs 净化后人声变清晰，模型就把这段借来的话也复读了。

修法：只用「本档自有」的 parts 重拼，并补足时长（nervous 还有 c092/c157/c191 未用）。

用法：
  G:/Python310/python.exe _fix_ref9.py --emo normal
  G:/Python310/python.exe _fix_ref9.py --emo nervous
输出：`_ref9_fix/<Joseph_normal|Joseph_nervous>.wav` + `_ref9_fix/_text.json`
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
SR = 48000
FF = "E:/tool/oopz/ffmpeg.exe"
PY = "G:/Python310/python.exe"
OUTD = os.path.join(ROOT, "_ref9_fix")


def load(p, sr=SR):
    y, s = sf.read(p, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(1)
    if s != sr:
        n = int(round(len(y) * sr / s))
        x = np.arange(n) * (len(y) - 1) / max(n - 1, 1)
        y = np.interp(x, np.arange(len(y)), y).astype(np.float32)
    return y


def voiced_rms(y, sr=SR, hop=0.01, win=0.025):
    h, w = int(hop * sr), int(win * sr)
    n = 1 + max(0, (len(y) - w) // h)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    seg = y[idx]
    e = np.sqrt((seg ** 2).mean(1)) + 1e-12
    db = 20 * np.log10(e)
    v = db[db > -45]
    return float(np.sqrt((y ** 2).mean()) * 10 ** ((-24.0 - (20 * np.log10(np.sqrt((y ** 2).mean()) + 1e-12))) / 20)), db, v


def voiced_mean(y):
    db, _ = frame(y)
    v = db[db > -45]
    return float(np.mean(v)) if len(v) else -120.0


def match_level(y, target_db=(-30.0), peak_cap=0.95):
    """把 voiced RMS 对齐到 target_db（**原参考自己的电平**）。

    2026-11-22 踩过的坑：原来固定归一到 −24 dBFS（那是成品的响度目标），
    但电影原声参考本身是 −30 dBFS，放大 6 dB 后 peak 冲到 1.000、42 个样本 >0.98（削顶），
    模型拿到削顶参考直接失控：11s 参考生成 23.68s、把参考文本念进正文。
    参考只需要**和原参考同电平**，绝不能按成品标准拉。
    """
    cur = voiced_mean(y)
    g = 10 ** ((target_db - cur) / 20.0)
    y = (y * g).astype(np.float32)
    if np.abs(y).max() > peak_cap:
        y = (y * (peak_cap / np.abs(y).max())).astype(np.float32)
    return y


def frame(y, hop=0.01, win=0.025, sr=SR):
    h, w = int(hop * sr), int(win * sr)
    n = 1 + max(0, (len(y) - w) // h)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    seg = y[idx]
    e = np.sqrt((seg ** 2).mean(1)) + 1e-12
    return 20 * np.log10(e), seg


def demucs_vocals(src, workdir):
    """跑 demucs 拿 vocals，返回路径；失败返回 None"""
    tmp = os.path.join(workdir, "dm")
    os.makedirs(tmp, exist_ok=True)
    r = subprocess.run([PY, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
                        "--shifts", "3", "--overlap", "0.5", "-o", tmp, src],
                       cwd=ROOT, capture_output=True, text=True)
    stem = os.path.join(tmp, "htdemucs", os.path.splitext(os.path.basename(src))[0], "vocals.wav")
    if r.returncode != 0 or not os.path.exists(stem):
        return None, (r.stderr or "")[-300:]
    return stem, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emo", required=True, choices=["normal", "nervous"])
    ap.add_argument("--target", type=float, default=9.5, help="目标时长秒")
    ap.add_argument("--noise-gap", type=float, default=0.05, help="段间静音")
    a = ap.parse_args()

    role = "Joseph"
    key = "%s_%s" % (role, a.emo)
    # 目标电平 = 原参考的 voiced RMS（不是成品标准的 −24）
    orig = os.path.join(ROOT, "_ref9", key + ".wav")
    tgt = voiced_mean(load(orig)) if os.path.exists(orig) else -30.0
    print("%s 原参考电平 %.1f dBFS（作为目标）" % (key, tgt))
    idx = json.load(open(os.path.join(ROOT, "_ref9", "_index_srt.json"), encoding="utf-8"))
    parts = [p for p in idx[key]["parts"] if not p.get("borrowed")]
    used = {os.path.basename(p["path"]) for p in parts}

    # 补足时长：同档未使用的素材
    extra_pool = sorted(glob.glob(os.path.join(ROOT, "refs_cast", "%s_%s_c*.wav" % (role, a.emo))))
    cur = sum(p["dur"] for p in parts)
    for p in extra_pool:
        if cur >= a.target:
            break
        if os.path.basename(p) in used:
            continue
        y = load(p)
        d = len(y) / SR
        parts.append({"path": p, "dur": d, "text": "", "extra": True})
        cur += d
    print("%s：自有 %d 段，合计 %.2fs（目标 %.1fs）" % (key, len(parts), cur, a.target))

    os.makedirs(OUTD, exist_ok=True)
    wd = os.path.join(OUTD, "_work_" + a.emo)
    os.makedirs(wd, exist_ok=True)
    segs, texts = [], []
    for i, p in enumerate(parts):
        src = p["path"]
        if not os.path.exists(src):
            print("  缺 %s" % src)
            continue
        stem, err = demucs_vocals(src, wd)
        if not stem:
            print("  demucs 失败 %s: %s" % (os.path.basename(src), err[-120:]))
            continue
        y = load(stem)
        y = match_level(y, tgt)
        segs.append(y)
        if p.get("text"):
            texts.append(p["text"])
        print("  [%d] %-28s %.2fs  净化后 %.2fs" % (
            i + 1, os.path.basename(src), p["dur"], len(y) / SR))

    if not segs:
        sys.exit("没有可用段")
    # 段间不能填数字零：全零占 29% 时模型在 DiT cache 分配阶段就失败
    # （deepseek 2026-11-22：11.03s 参考 + 1.6s 全零间隔 → failed to allocate SOAR DiT cache，
    #  而 13.39s 原参考能跑，差别就是这 29% 的 −inf 段）。改填 −72 dBFS 的极低噪声。
    ng = int(a.noise_gap * SR)
    rng = np.random.default_rng(42)
    gap = (rng.standard_normal(ng) * 10 ** (-72 / 20.0)).astype(np.float32)
    out = []
    for i, y in enumerate(segs):
        if i:
            out.append(gap)
        out.append(y)
    z = np.concatenate(out)
    z = match_level(z, tgt)
    dst = os.path.join(OUTD, key + ".wav")
    sf.write(dst, z, SR, subtype="PCM_16")
    print("\n→ %s  %.2fs" % (dst, len(z) / SR))

    tp = os.path.join(OUTD, "_text.json")
    d = json.load(open(tp, encoding="utf-8")) if os.path.exists(tp) else {}
    d[key] = " ".join(texts)
    json.dump(d, open(tp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("文本（%d 段）：%s" % (len(texts), d[key][:160]))
    shutil.rmtree(wd, ignore_errors=True)


if __name__ == "__main__":
    main()
