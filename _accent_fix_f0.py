# -*- coding: utf-8 -*-
"""给逐词特征补第二估计器（pyin），消掉 parselmouth 的八度错。

为什么必须补：
  上一版直接用 parselmouth 的词内 p50 当突出度，跑出 Δ+34.4st（近三个八度）这种值 ——
  真人同一句里不可能，是八度跟踪错。全库 115 条命中基本被这类毛刺支配。
  项目既有判据（第 15 项 F0 复核）已经定过：**双估计器都判突跳才算真**，这里沿用。

做法：
  · 对每个词窗（ASR 词边界）分别跑 parselmouth(已有 p50) 与 pyin
  · 两者相差 ≤ 2st → 记 cons = 两者均值，ok=True
  · 否则 → ok=False，cons 置 None（不参与判决）
  · 另加物理夹：|cons − 句内中位| > 14st 一律判 ok=False（真人一句内做不到）

用法：
  G:/Python310/python.exe -u _accent_fix_f0.py --in _accent_feat_old.jsonl --dir _audio_ch123/out --out _accent_fix_old.jsonl
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf
import librosa

ROOT = r"G:/_setup"
SR16 = 16000
TOL = 2.0          # 两估计器允许的最大差异（半音）
MAX_DEV = 14.0     # 词突出度物理上限（半音），超了判跟踪失败


def semis(f):
    return 12.0 * np.log2(np.asarray(f, dtype=float) / 100.0)


def pyin_word(y16, t0, t1):
    """返回 (p50, p90) 两个半音值；不足则 None。

    2026-11-24 补：原先只返回 p50。但峰高（§5.1）要用 p90 那一档，
    只给 p50 的一致值会导致峰检测仍回落到单估计器的 hi_f0 —— 那正是 Δ34.4st 假命中的来源。
    """
    a, b = int(t0 * SR16), int(t1 * SR16)
    seg = y16[max(0, a):max(1, b)]
    if len(seg) < int(0.08 * SR16):
        return None, None
    try:
        f0, vflag, _ = librosa.pyin(seg, fmin=60, fmax=400, sr=SR16,
                                    frame_length=1024, hop_length=160)
    except Exception:  # noqa: BLE001
        return None, None
    v = f0[vflag & np.isfinite(f0)]
    if len(v) < 3:
        return None, None
    s = semis(v)
    return float(np.median(s)), float(np.percentile(s, 90))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    inp = a.inp if os.path.isabs(a.inp) else os.path.join(ROOT, a.inp)
    outp = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    fh = open(outp, "w", encoding="utf-8")
    n_ok = n_bad = n_sent = n_ok90 = 0

    for ln in open(inp, encoding="utf-8"):
        r = json.loads(ln)
        p = os.path.join(ROOT, a.dir, r["id"] + ".wav")
        if not os.path.exists(p):
            continue
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y16 = librosa.resample(y, orig_sr=sr, target_sr=SR16)
        for w in r["words"]:
            w["p50y"] = None
            w["p90y"] = None
            w["cons"] = None
            w["cons90"] = None
            w["ok"] = False
            if w["p50"] is None:
                continue
            pv, pv90 = pyin_word(y16, w["t0"], w["t1"])
            if pv is None:
                continue
            w["p50y"] = round(pv, 2)
            if pv90 is not None:
                w["p90y"] = round(pv90, 2)
            if abs(pv - w["p50"]) <= TOL:
                c = 0.5 * (pv + w["p50"])
                if abs(c - r["med"]) <= MAX_DEV:
                    w["cons"] = round(c, 2)
                    w["ok"] = True
                    n_ok += 1
                    # 峰高那一档：p90 也要两个估计器互证，才给 cons90
                    if pv90 is not None and w.get("p90") is not None \
                            and abs(pv90 - w["p90"]) <= TOL:
                        c90 = 0.5 * (pv90 + w["p90"])
                        if abs(c90 - r["med"]) <= MAX_DEV:
                            w["cons90"] = round(c90, 2)
                            n_ok90 += 1
                else:
                    n_bad += 1
            else:
                n_bad += 1
        n_sent += 1
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.flush()
        if n_sent % 100 == 0:
            print("... %d 句  一致 %d 词 / 不一致 %d 词 / 峰高可用 %d 词"
                  % (n_sent, n_ok, n_bad, n_ok90), flush=True)
    fh.close()
    print("完成 %d 句；一致 %d 词，判失败 %d 词（%.1f%%）；峰高(cons90)可用 %d 词（%.1f%% of 一致）"
          % (n_sent, n_ok, n_bad, 100.0 * n_bad / max(1, n_ok + n_bad),
             n_ok90, 100.0 * n_ok90 / max(1, n_ok)))


if __name__ == "__main__":
    main()
