# -*- coding: utf-8 -*-
"""_sweep_backfill.py —— 把多 seed 择优胜者回填到交付目录

只做回填，不做判断（判断在 `_sweep_eval.py --pick`）。

纪律（每条都是踩过的）：
  - 先备份原件到 `out_bak_sweep_1115/`，同名已存在就跳过备份而不是覆盖
  - 归一到 −24dBFS（`norm_dlg.vdb`），峰值 >0.891 才 soft_clip，不预削波
  - **候选比原件短于 0.6 倍不收**（残片）
  - 写台账 `_backfill_sweep_log.json`，之后 `_fresh_nat.py` 之类要按它刷缓存

用法：
  G:/Python310/python.exe _sweep_backfill.py --dry
  G:/Python310/python.exe _sweep_backfill.py
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
from norm_dlg import vdb, soft_clip  # noqa: E402

HERE = "G:/_setup"
CAND = os.path.join(HERE, "_sweep", "cand")
PICK = os.path.join(HERE, "_sweep", "pick.json")
DELIV = os.path.join(HERE, "_audio_ch123", "out")
BAK = os.path.join(HERE, "_audio_ch123", "out_bak_sweep_1115")
LOG = os.path.join(HERE, "_backfill_sweep_log.json")
TARGET, PEAK_MAX = -24.0, 0.891


def normalize(src, dst):
    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    r0 = vdb(y, sr)
    g = TARGET - r0 if r0 > -60 else 0.0
    g = max(-12.0, min(12.0, g))
    y = y * (10 ** (g / 20.0))
    if float(np.abs(y).max()) > PEAK_MAX:
        y = soft_clip(y, PEAK_MAX)
    sf.write(dst, y.astype(np.float32), sr, subtype="PCM_16")
    return round(float(vdb(y, sr)), 2), round(float(np.abs(y).max()), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--cand-dir", default="", help="候选目录（默认 _sweep/cand）")
    ap.add_argument("--pick", default="", help="择优表（默认 _sweep/pick.json）")
    a = ap.parse_args()
    global CAND, PICK
    if a.cand_dir:
        CAND = a.cand_dir
    if a.pick:
        PICK = a.pick

    pk = json.load(open(PICK, encoding="utf-8"))
    picks = pk.get("picks") or {}
    os.makedirs(BAK, exist_ok=True)
    done, skip = [], []
    for rid, p in sorted(picks.items()):
        src = os.path.join(CAND, "%s__s%s.wav" % (rid, p["seed"]))
        if not os.path.exists(src):
            skip.append((rid, "候选不存在"))
            continue
        old = os.path.join(DELIV, rid + ".wav")
        d_new = sf.info(src).duration
        d_old = sf.info(old).duration if os.path.exists(old) else 0.0
        if d_old and d_new < 0.6 * d_old:
            skip.append((rid, "残片 %.2f<0.6×%.2f" % (d_new, d_old)))
            continue
        print("%-9s s%-3s %.2fs → %.2fs  [%s/%s/%s]" % (
            rid, p["seed"], d_old, d_new, p.get("emo"), p.get("intra"), p.get("nat")))
        if a.dry:
            continue
        if os.path.exists(old) and not os.path.exists(os.path.join(BAK, rid + ".wav")):
            shutil.copy2(old, os.path.join(BAK, rid + ".wav"))
        rb, pkv = normalize(src, old)
        done.append(dict(id=rid, seed=p["seed"], dur_old=round(d_old, 2),
                         dur_new=round(d_new, 2), rms=rb, peak=pkv,
                         why=p.get("why"), emo=p.get("emo"), intra=p.get("intra"),
                         nat=p.get("nat")))
    if a.dry:
        print("\n（--dry，未写文件）")
        return
    json.dump(dict(backfilled=done, skipped=skip), open(LOG, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n回填 %d 条 / 跳过 %d 条 → 台账 %s" % (len(done), len(skip), LOG))
    if done:
        print("下一步：把这 %d 条重新注入停顿（out_paused 已过期）" % len(done))
        print("  --only " + ",".join(x["id"] for x in done))


if __name__ == "__main__":
    main()
