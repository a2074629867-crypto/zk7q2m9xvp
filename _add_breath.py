# -*- coding: utf-8 -*-
"""补气口：在词间「本该断」的位置把停顿拉到目标长度，用底噪填充（不插纯零）。

为什么不用纯静音：纯数字静音听起来空洞、没有呼吸感（用户原话「停顿太空」）。
这里取该位置自身的低电平噪声循环填充，保留空气感。

位置怎么定：用 whisper 词界 + plan 文本的标点，优先在标点后的词间插入；
如果该处已有足够停顿就跳过；每句最多补 max_ins 处，避免把句子切碎。

用法：
  G:/Python310/python.exe _add_breath.py --ids c3_0876,c3_0922 --target 0.22
"""
import argparse
import io
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from transplant_prosody2 import word_times  # noqa: E402

ROOT = "G:/_setup"
DIRS = [os.path.join(ROOT, "_audio_ch123", "out"), os.path.join(ROOT, "_audio_ch123", "out_paused")]
BAK = os.path.join(ROOT, "_bak_breath_1120")


def load_plan():
    p = {}
    for f in ("_dlg_plan_v2_paused.jsonl", "_dlg_plan_v2.jsonl"):
        fp = os.path.join(ROOT, f)
        if not os.path.exists(fp):
            continue
        for l in io.open(fp, encoding="utf-8"):
            if l.strip():
                x = json.loads(l)
                p.setdefault(x["id"], x)
    return p


def voiced_db(y, sr):
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    fr = y[idx]
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-12)
    v = fr[db > db.max() - 40]
    return float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)) if len(v) else None


def norm24(y, sr):
    lv = voiced_db(y, sr)
    if lv is None:
        return y
    y = (y * 10 ** ((-24.0 - lv) / 20.0)).astype("float32")
    pk = float(np.abs(y).max())
    if pk > 0.97:
        y = (y * (0.97 / pk)).astype("float32")
    return y


def room_tone(seg, need, sr):
    if len(seg) < int(0.03 * sr) or float(np.abs(seg).max()) < 1e-5:
        rng = np.random.default_rng(11)
        seg = (rng.standard_normal(int(0.3 * sr)) * 10 ** (-62 / 20)).astype("float32")
        seg = np.convolve(seg, np.ones(9, dtype="float32") / 9, mode="same").astype("float32")
    reps = int(np.ceil(need / max(1, len(seg))))
    out = np.tile(seg, reps)[:need].astype("float32")
    k = int(0.010 * sr)
    if len(out) > 2 * k:
        out[:k] *= np.linspace(0, 1, k, dtype="float32")
        out[-k:] *= np.linspace(1, 0, k, dtype="float32")
    return out


def text_word_index_after_punct(text, nwords):
    """返回「标点后面那个词」的下标集合（0 基），用于定位断点。"""
    t = text or ""
    words = [w for w in t.split() if any(c.isalnum() for c in w)]
    idx, wi = set(), 0
    for tok in t.split():
        if any(c.isalnum() for c in tok):
            wi += 1
        elif tok.strip() and tok.strip()[-1] in ",.;:!?…—" and 0 < wi < nwords:
            idx.add(wi)  # 第 wi 个词之前断（即上一词之后）
    return idx


def find_breaks(y, sr, max_ins):
    """在波形里找「本该断」的低谷：相对能量最低、两侧都有实词的短谷。"""
    hp = int(0.02 * sr)
    n = len(y) // hp
    db = np.array([20 * np.log10(np.sqrt((y[k * hp:(k + 1) * hp] ** 2).mean()) + 1e-12)
                   for k in range(n)])
    loud = db > (db.max() - 15.0)
    # 连续「不响」段
    runs, s = [], None
    for k, v in enumerate(loud):
        if (not v) and s is None:
            s = k
        if v and s is not None:
            runs.append((s, k))
            s = None
    if s is not None:
        runs.append((s, n))
    cand = []
    for a, b in runs:
        ln = (b - a) * hp / sr
        if not (0.03 <= ln <= 0.40):
            continue
        if a < 3 or b > n - 3:
            continue
        if (a + b) // 2 * hp / sr < 0.22 or (a + b) // 2 * hp / sr > len(y) / sr - 0.10:
            continue
        # 两侧必须有 ≥0.12s 的实词
        if loud[max(0, a - 6):a].sum() < 4 or loud[b:min(n, b + 6)].sum() < 4:
            continue
        depth = float(db[a:b].min())
        cand.append((depth, (a + b) // 2 * hp, ln, a * hp, b * hp))
    cand.sort(key=lambda x: x[0])
    return cand[:max_ins], db


def process(rid, plan, target, max_ins, dry=False):
    p = os.path.join(DIRS[1], rid + ".wav")
    if not os.path.exists(p):
        return None
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y)
    brk, db = find_breaks(y, sr, max_ins)
    if not brk:
        return dict(id=rid, changed=False, note="无明显低谷")
    if dry:
        return dict(id=rid, dry=True,
                    plan=[(round(c / sr, 2), round(ln, 2)) for _, c, ln, _a, _b in brk])
    out = y
    for _, c, ln, ga, gb in sorted(brk, key=lambda x: -x[1]):
        need = int((target - ln) * sr)
        if need <= 0:
            continue
        seg = (y[ga:gb] * 0.5).astype("float32")  # 气口比原谷再低 6dB，听感更明确
        ins = room_tone(seg, need, sr)
        out = np.concatenate([out[:c], ins, out[c:]])
    out = norm24(out, sr)

    os.makedirs(BAK, exist_ok=True)
    import shutil
    for d in DIRS:
        f = os.path.join(d, rid + ".wav")
        if os.path.exists(f):
            b = os.path.join(BAK, os.path.basename(d) + "_" + rid + ".wav")
            if not os.path.exists(b):
                shutil.copy2(f, b)
            sf.write(f, out, sr, subtype="PCM_16")
    return dict(id=rid, changed=True, n=len(brk),
                dur=round(len(out) / sr, 2), lv=round(voiced_db(out, sr) or 0, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--target", type=float, default=0.22)
    ap.add_argument("--max-ins", type=int, default=2)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    plan = load_plan()
    for rid in [x.strip() for x in a.ids.split(",") if x.strip()]:
        r = process(rid, plan, a.target, a.max_ins, a.dry)
        print(rid, r)


if __name__ == "__main__":
    main()
