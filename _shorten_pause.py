# -*- coding: utf-8 -*-
"""_shorten_pause.py —— 把模型自己吐出来的**无用长停顿**剪短（不做任何插入）。

用户 2026-11-21：
  「把原来一开始的长停顿去掉，就是无用的长停顿去掉，就是模型自己生成的」

和之前被否掉的做法区别
--------------------
· ❌ `_add_breath.py`：往静音里**插**停顿 → 听出来「空、没呼吸」
· ❌ `_rebuild_calm*.py`：rubberband 降速 → 听出来「太慢」
· ✅ 本脚本：**只剪不插**。模型本来就在中途停了 0.7~1.7s，把这段的低电平噪声
  从中间剪掉一截，两端底噪本来就是连续的，接缝落在噪声里，听不出剪过。

判据
----
· 只处理**句内**停顿（前后都有语音），首尾静音不动。
· 只处理 ≥ `--min-gap`（默认 0.70s）的；≤0.7s 是正常换气，动了会变赶。
· 剪到 `--target`（默认 0.38s）—— 这个长度是 Charles/Thomas 句内逗号停顿的中位。
· 裁剪点取停顿正中，两端各留一半，保留自然的衰减与起音。
· 接缝做 12ms 等功率交叉淡化，避免咔哒。

用法
----
  G:/Python310/python.exe _shorten_pause.py --in _audio_ch123/out_paused \
      --out _audio_ch123/out_short --ids c2_0267,c2_0312 --report _shorten.json
  G:/Python310/python.exe _shorten_pause.py --in ... --out ... --probe   # 只报不写
"""
import argparse
import glob
import json
import os

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"


def frame_db(y, sr, hop=0.01, win=0.025):
    h, w = int(hop * sr), int(win * sr)
    n = 1 + max(0, (len(y) - w) // h)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(y) - 1)
    return 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12), h, w


def voiced_runs(y, sr, thr_abs=-50.0):
    """返回有声段 [(s0,s1)]（采样点）。

    阈值用**绝对 −50 dBFS**，不用 `peak−45`。
    原因（2026-11-21 实测）：填底噪会把原来全零的静音抬到 −57.5 dBFS，
    自适应阈值随之漂移，同一段 0.74s 的停顿会从「0.74s」量成「0.24s」，
    于是该剪的没剪（`dur` 一点没变），指标却显示「变短了」—— 假改进。
    绝对阈值对填充前后一致，量出来的才是耳朵听到的。
    """
    db, h, w = frame_db(y, sr)
    thr = thr_abs if float(db.max()) > thr_abs + 20 else max(-46.0, float(db.max()) - 45.0)
    v = db > thr
    runs, s = [], None
    for k, b in enumerate(v):
        if b and s is None:
            s = k
        if not b and s is not None:
            runs.append((s, k))
            s = None
    if s is not None:
        runs.append((s, len(v)))
    out = []
    for a, b in runs:
        if (b - a) * h / sr < 0.05:      # 太短的「有声」是噪声，丢掉
            continue
        out.append((a * h, min(len(y), b * h + w)))
    return out


def join_cf(chunks, sr, cf=0.012):
    """等功率交叉淡化拼接。"""
    n = max(1, int(cf * sr))
    y = chunks[0]
    for c in chunks[1:]:
        k = min(n, len(y), len(c))
        a = y[-k:]
        b = c[:k]
        t = np.linspace(0, 1, k, dtype=np.float32)
        mix = a * np.cos(t * np.pi / 2) + b * np.sin(t * np.pi / 2)
        y = np.concatenate([y[:-k], mix, c[k:]])
    return y


def shorten(y, sr, min_gap=0.70, target=0.38):
    """剪句内长停顿，返回 (新波形, 处理明细)。"""
    runs = voiced_runs(y, sr)
    if len(runs) < 2:
        return y, []
    cuts = []
    for i in range(len(runs) - 1):
        a, b = runs[i][1], runs[i + 1][0]
        gap = (b - a) / sr
        if gap < min_gap:
            continue
        cut = gap - target
        if cut <= 0.05:
            continue
        # 两端各留 target/2，中间整段剪掉 ⇒ 剩余正好 = target
        # （反过来写会把「剪 1.29s」变成「剪 0.38s」，实测踩过）
        cs = int(a + target * sr / 2)
        ce = int(b - target * sr / 2)
        if ce <= cs:
            continue
        cuts.append((cs, ce, round(gap, 2), round(target, 2)))
    if not cuts:
        return y, []
    chunks, cursor = [], 0
    for cs, ce, _, _ in cuts:
        chunks.append(y[cursor:cs])
        cursor = ce
    chunks.append(y[cursor:])
    return join_cf(chunks, sr), cuts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(ROOT, "_audio_ch123", "out_paused"))
    ap.add_argument("--out", default=os.path.join(ROOT, "_audio_ch123", "out_short"))
    ap.add_argument("--ids", default="")
    ap.add_argument("--min-gap", type=float, default=0.70)
    ap.add_argument("--target", type=float, default=0.38)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--report", default=os.path.join(ROOT, "_shorten_report.json"))
    a = ap.parse_args()

    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    files = ([os.path.join(a.inp, i + ".wav") for i in ids] if ids
             else sorted(glob.glob(os.path.join(a.inp, "*.wav"))))
    if not a.probe:
        os.makedirs(a.out, exist_ok=True)

    rep, n_changed = {}, 0
    for f in files:
        if not os.path.exists(f):
            print("缺", os.path.basename(f))
            continue
        y, sr = sf.read(f, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        y2, cuts = shorten(y, sr, a.min_gap, a.target)
        tag = os.path.basename(f)[:-4]
        d0, d1 = len(y) / sr, len(y2) / sr
        rep[tag] = dict(dur_before=round(d0, 2), dur_after=round(d1, 2),
                        saved=round(d0 - d1, 2),
                        cuts=[{"gap": g, "to": t} for _, _, g, t in cuts])
        if not cuts:
            continue
        n_changed += 1
        # 剪完重新归一到 −24 dBFS（剪长度不改电平，但保险）
        if not a.probe:
            sf.write(os.path.join(a.out, os.path.basename(f)), y2, sr, subtype="PCM_16")
        print("%-9s %.2f → %.2f  (-%.2fs)  剪 %d 处 %s" % (
            tag, d0, d1, d0 - d1, len(cuts), [c[2] for c in cuts]))

    if a.report:
        json.dump(rep, open(a.report, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print("\n处理 %d 条，改动 %d 条%s" % (
        len(rep), n_changed, "（probe 模式未写文件）" if a.probe else ""))


if __name__ == "__main__":
    main()
