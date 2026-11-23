# -*- coding: utf-8 -*-
"""只对有 60 条人工标注的 uid 跑 wpt，一次批量并行，省时间。

用法:
  python _wpt_targeted.py            # 有标注的 uid 全部候选
  python _wpt_targeted.py --all --jobs 6   # 有标注 + 其余(ch1 全量)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

SRC = "G:/_setup/_stress_words.json"
LAB = "G:/_setup/_mt_labels_live.json"
TG = "G:/_setup/_wpt_tg"
BATCH = "G:/_setup/_wpt_batch"
OUT = "G:/_setup/_wpt_out"
PY = "G:/_setup/wpt_venv/Scripts/python.exe"
CFG = "G:/_setup/_wpt/mt.yaml"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()

    stress = json.load(open(SRC, encoding="utf-8"))
    lab = json.load(open(LAB, encoding="utf-8"))
    want = {u for u, v in lab.items() if str(v.get("pick")) not in ("None", "none")}

    os.makedirs(BATCH, exist_ok=True)
    done = {os.path.basename(f)[:-5] for f in os.listdir(OUT) if f.endswith(".prom")}

    n_copy = 0
    missing = []
    for k, v in stress.items():
        uid = v["uid"]
        if not a.all and uid not in want:
            continue
        wav = k.replace("\\", "/")
        tag = os.path.basename(os.path.dirname(wav))
        base = "%s__%s" % (tag, uid)
        tg = os.path.join(TG, base + ".TextGrid")
        if base in done:
            continue
        if not os.path.exists(wav) or not os.path.exists(tg):
            missing.append(base)
            continue
        dst_w = os.path.join(BATCH, base + ".wav")
        dst_t = os.path.join(BATCH, base + ".TextGrid")
        if not os.path.exists(dst_w):
            shutil.copy2(wav, dst_w)
            n_copy += 1
        if not os.path.exists(dst_t):
            shutil.copy2(tg, dst_t)

    print("复制 %d 个 wav 到批量目录，缺 %d" % (n_copy, len(missing)))
    if missing:
        print("  缺失例：", missing[:5])

    files = [f for f in os.listdir(BATCH) if f.endswith(".wav")]
    print("批量目录 %d 个 wav，开始并行分析（jobs=%d）" % (len(files), a.jobs))
    if not files:
        return
    t0 = time.time()
    r = subprocess.run([PY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                        "-j", str(a.jobs), "-c", CFG, "-o", OUT, BATCH],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore", timeout=7200)
    print("耗时 %.1f 分钟" % ((time.time() - t0) / 60))
    if r.returncode != 0:
        print("stderr:", (r.stderr or "")[-1500:])
    n = len([f for f in os.listdir(OUT) if f.endswith(".prom")])
    print("输出目录现有 %d 个 .prom" % n)

    # 清理
    for f in os.listdir(BATCH):
        try:
            os.remove(os.path.join(BATCH, f))
        except OSError:
            pass
    print("已清理批量目录")


if __name__ == "__main__":
    main()
