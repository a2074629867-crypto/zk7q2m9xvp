# -*- coding: utf-8 -*-
"""_anchor_build.py —— 把真人母带切片对齐成 prom，用来当「真人锚点」。

母带：G:/GPT-SoVITS/_dataset/wonder_train.wav（1615s / 32kHz）
切片：sliced/*.wav + wonder.list 里的文本（302 条 / 2553 词 / 119 wpm）

流程与 _prom_build.py 完全一致（ASR → TextGrid → wpt），这样测出来的
loc / sps / 时长跟我们的 take 同口径，才能比。

用法：
    G:/Python310/python.exe _anchor_build.py --limit 20     # 试跑
    G:/Python310/python.exe _anchor_build.py                # 全量
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = "G:/_setup"
ASRPY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")
WPTPY = os.path.join(ROOT, "wpt_venv", "Scripts", "python.exe")
CFG = os.path.join(ROOT, "_wpt", "mt.yaml")
LIST = "G:/GPT-SoVITS/_dataset/wonder.list"
PREFIX = "_anchor"

sys.path.insert(0, ROOT)
import mt_loop   # noqa: E402


def load_list():
    rows = []
    for line in io.open(LIST, encoding="utf-8").read().splitlines():
        p = line.split("|")
        if len(p) < 4:
            continue
        m = re.search(r"_(\d+)_(\d+)\.wav$", p[0])
        if not m:
            continue
        rows.append((int(m.group(1)), int(m.group(2)), p[0], p[3].strip()))
    rows.sort()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-asr", action="store_true")
    a = ap.parse_args()

    rows = load_list()
    if a.limit:
        rows = rows[:a.limit]
    print("母带切片 %d 条" % len(rows))

    stage = os.path.join(ROOT, "_anchor_stage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, exist_ok=True)

    meta = {}
    for i, (s, e, path, text) in enumerate(rows):
        wid = "w%04d" % i
        dst = os.path.join(stage, "%s__%s.wav" % (PREFIX, wid))
        shutil.copy2(path, dst)
        meta[wid] = dict(idx=i, start=s / 32000.0, end=e / 32000.0,
                         src=path, text=text)
    json.dump(meta, open(os.path.join(ROOT, "_anchor_meta.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)

    asr_json = os.path.join(ROOT, "_anchor_asr.json")
    if not (a.skip_asr and os.path.exists(asr_json)):
        t0 = time.time()
        srcs = sorted(os.path.join(stage, f) for f in os.listdir(stage))
        r = subprocess.run([ASRPY, os.path.join(ROOT, "_asr_lib.py"),
                            "--out", asr_json] + srcs,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=7200)
        if not os.path.exists(asr_json):
            raise SystemExit("ASR 失败 " + (r.stderr or "")[-600:])
        print("ASR 完成 %.1f 秒" % (time.time() - t0))

    asr = {os.path.normpath(k): v for k, v in
           json.load(open(asr_json, encoding="utf-8")).items()}
    n = 0
    for f in sorted(os.listdir(stage)):
        if not f.endswith(".wav"):
            continue
        p = os.path.join(stage, f)
        k = os.path.normpath(p)
        if k not in asr:
            print("  !! ASR 缺 %s" % f)
            continue
        base = os.path.splitext(f)[0]
        mt_loop.write_textgrid(os.path.join(stage, base + ".TextGrid"),
                               asr[k]["dur"], asr[k]["words"])
        n += 1
    print("TextGrid %d 条" % n)

    t0 = time.time()
    r = subprocess.run([WPTPY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                        "-j", "4", "-c", CFG, "-o", os.path.join(ROOT, "_wpt_out"),
                        stage],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore", timeout=10800)
    print("wpt rc=%d  %.1f 秒" % (r.returncode, time.time() - t0))
    got = [f for f in os.listdir(os.path.join(ROOT, "_wpt_out"))
           if f.startswith(PREFIX + "__")]
    print("prom 现有 %d 条" % len(got))
    if len(got) < len(rows):
        print("  缺 %d 条" % (len(rows) - len(got)))


if __name__ == "__main__":
    main()
