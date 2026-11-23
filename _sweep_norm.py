# -*- coding: utf-8 -*-
"""_sweep_norm.py —— 候选音频按交付口径归一化后再过闸。

为什么需要这一步（2026-11-15 12:5x 发现）：
  `dialog_gate.audio_stats` 的 `silent` 是**绝对**阈值（10ms 帧 RMS < −45dBFS 即算静音），
  而 dots.tts 直出的候选**没有做响度归一化** —— 实测 `c1_0052__s7.wav` 峰值 −27.7dB，
  按 −45dB 一量「静音占 62%」⇒ 判 `mostly_silence` REGEN；
  同一条按交付口径拉到 voiced RMS −24dBFS 后，静音只占 9%。
  ⇒ 候选必须先归一化，否则「安静」被当成「没说话」，好候选被误杀。

归一化口径与交付完全一致（`mt_final_pause.py` 导出段）：
  voiced RMS → −24dBFS；峰值超过 0.97 时按峰值回退，保证不削波。

用法：
  G:/Python310/python.exe -u _sweep_norm.py --src _sweep/cand3 --dst _sweep/cand3n
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from narr_gate_phys import voiced_db  # noqa: E402

TARGET = -24.0
PEAK_CAP = 0.97


def one(src, dst):
    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y)
    lv, _, _ = voiced_db(y, sr)
    if lv is None or not np.isfinite(lv):
        return None
    g = 10 ** ((TARGET - lv) / 20.0)
    pk = float(np.abs(y).max()) * g
    if pk > PEAK_CAP:
        g = PEAK_CAP / max(1e-9, float(np.abs(y).max()))
    y2 = (y * g).astype("float32")
    sf.write(dst, y2, sr, subtype="PCM_16")
    lv2, _, _ = voiced_db(np.ascontiguousarray(y2), sr)
    return dict(src=os.path.basename(src), lv=round(lv, 2), lv2=round(lv2, 2),
                gain=round(20 * np.log10(g), 2), peak=round(float(np.abs(y2).max()), 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--min-lv", type=float, default=-40.0,
                    help="voiced RMS 低于此值视为「基本没说话」，直接丢弃不归一"
                         "（否则 +47dB 放大把底噪抬成语音）")
    a = ap.parse_args()
    os.makedirs(a.dst, exist_ok=True)
    rows, bad = [], 0
    for p in sorted(glob.glob(os.path.join(a.src, "*.wav"))):
        d = os.path.join(a.dst, os.path.basename(p))
        try:
            r = one(p, d)
        except Exception as e:  # noqa: BLE001
            print("  失败", os.path.basename(p), str(e)[:80])
            bad += 1
            continue
        if r is None:
            bad += 1
            continue
        if r["lv"] < a.min_lv:
            print("  丢弃 %-24s voiced RMS %.1f dB（基本无语音）" % (r["src"], r["lv"]))
            try:
                os.remove(d)
            except OSError:
                pass
            bad += 1
            continue
        rows.append(r)
    print("归一化 %d 条，失败 %d" % (len(rows), bad))
    if rows:
        gs = [r["gain"] for r in rows]
        print("增益 %.1f ~ %.1f dB（中位 %.1f）；归一后 voiced RMS %.1f ~ %.1f" % (
            min(gs), max(gs), sorted(gs)[len(gs) // 2],
            min(r["lv2"] for r in rows), max(r["lv2"] for r in rows)))
    json.dump(rows, open(os.path.join(a.dst, "_norm_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
