# -*- coding: utf-8 -*-
"""_prom_build.py —— 给「交付版音频」重建 prom（ASR → TextGrid → wpt）。

为什么必须做：`_mt_pick/` 里 13 条的 wav 来自 s1234，但 `_wpt_out` 只有 s42 的 prom。
拿 s42 的 prom 去量 s1234 的音频，词区间整体错位 —— N0419 会被测成 loc −4.58、
voiced 0.33（实际正常）。这就是「交付目录血统」那个坑的 mt 版。

产出 prom 命名：`<prefix>__<uid>.prom`，与 `mt_adv_fix.prom_wav` 的优先级
（_mt_pick 最高）对上。

用法：
    G:/Python310/python.exe _prom_build.py --prefix _mt_pick --dir _mt_pick \
        --units N0419,N0829,... --prom-out _wpt_out
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = "G:/_setup"
ASRPY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")
WPTPY = os.path.join(ROOT, "wpt_venv", "Scripts", "python.exe")
CFG = os.path.join(ROOT, "_wpt", "mt.yaml")

sys.path.insert(0, ROOT)
import mt_loop   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="_mt_pick")
    ap.add_argument("--dir", default=os.path.join(ROOT, "_mt_pick"))
    ap.add_argument("--units", default="")
    ap.add_argument("--prom-out", default=os.path.join(ROOT, "_wpt_out"))
    a = ap.parse_args()

    uids = [x.strip() for x in a.units.split(",") if x.strip()]
    if not uids:
        raise SystemExit("需要 --units")
    stage = os.path.join(ROOT, "_prom_stage_" + a.prefix.strip("_"))
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, exist_ok=True)

    srcs = []
    for u in uids:
        s = os.path.join(a.dir, u + ".wav")
        if not os.path.exists(s):
            print("!! 缺音频 %s" % u)
            continue
        d = os.path.join(stage, "%s__%s.wav" % (a.prefix, u))
        shutil.copy2(s, d)
        srcs.append(d)
    if not srcs:
        raise SystemExit("没有可处理的音频")

    asr_json = os.path.join(ROOT, "_prom_asr_%s.json" % a.prefix.strip("_"))
    t0 = time.time()
    r = subprocess.run([ASRPY, os.path.join(ROOT, "_asr_lib.py"), "--out", asr_json] + srcs,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=3600)
    if not os.path.exists(asr_json):
        raise SystemExit("ASR 失败 " + (r.stderr or "")[-400:])
    asr = {os.path.normpath(k): v for k, v in json.load(open(asr_json, encoding="utf-8")).items()}
    print("ASR %d 条，%.1f 秒" % (len(asr), time.time() - t0))

    n = 0
    for p in srcs:
        k = os.path.normpath(p)
        if k not in asr:
            continue
        base = os.path.splitext(os.path.basename(p))[0]
        mt_loop.write_textgrid(os.path.join(stage, base + ".TextGrid"),
                              asr[k]["dur"], asr[k]["words"])
        n += 1
    print("TextGrid %d 条" % n)

    t0 = time.time()
    r = subprocess.run([WPTPY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                        "-j", "4", "-c", CFG, "-o", a.prom_out, stage],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore", timeout=3600)
    print("wpt rc=%d，%.1f 秒" % (r.returncode, time.time() - t0))
    got = [f for f in os.listdir(a.prom_out) if f.startswith(a.prefix + "__")]
    print("prom 现有 %d 条（%s__*）" % (len(got), a.prefix))
    for u in uids:
        p = os.path.join(a.prom_out, "%s__%s.prom" % (a.prefix, u))
        if not os.path.exists(p):
            print("  !! 缺 prom %s" % u)


if __name__ == "__main__":
    main()
