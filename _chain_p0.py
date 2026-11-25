# -*- coding: utf-8 -*-
"""P0 收尾自动链：等双估计器两版跑齐 → 用 cons90 重跑 3.1 → 跑词间 F0 四量。

不占 GPU，纯 CPU。任何一步失败都停下来打印原因，不硬撑。

用法：G:/Python310/python.exe -u _chain_p0.py
"""
import io
import os
import subprocess
import sys
import time

ROOT = r"G:/_setup"
PY = r"G:/Python310/python.exe"
# 期望条数不能写死 716：`_accent_feat_new.jsonl` 本身只有 715 条（c2_0412 缺特征），
# 写死会导致链条永远等下去（2026-11-24 实际踩到）。
PAIRS = [("_accent_fix_old.jsonl", "_accent_feat_old.jsonl"),
         ("_accent_fix_new.jsonl", "_accent_feat_new.jsonl")]
DEADLINE = 60 * 60          # 最多等 60 分钟


def nlines(p):
    if not os.path.exists(p):
        return 0
    with io.open(p, encoding="utf-8") as f:
        return sum(1 for _ in f)


def run(args, tag):
    print("\n[%s] %s" % (time.strftime("%H:%M:%S"), " ".join(args)), flush=True)
    r = subprocess.run(args, cwd=ROOT)
    if r.returncode != 0:
        print("!! %s 失败 rc=%d，链条停止" % (tag, r.returncode), flush=True)
        sys.exit(r.returncode)


def main():
    t0 = time.time()
    while True:
        got = [nlines(os.path.join(ROOT, f)) for f, _ in PAIRS]
        need = [nlines(os.path.join(ROOT, s)) for _, s in PAIRS]
        print("[%s] fix=%s / need=%s" % (time.strftime("%H:%M:%S"), got, need), flush=True)
        if all(g >= n for g, n in zip(got, need)) and min(need) > 0:
            break
        if time.time() - t0 > DEADLINE:
            print("!! 超时未跑齐，链条停止（已完成的文件保留）", flush=True)
            sys.exit(2)
        time.sleep(30)

    run([PY, "-u", "_accent_rule.py",
         "--a", "_accent_fix_old.jsonl", "--b", "_accent_fix_new.jsonl",
         "--cons90", "--t1", "3.0", "--json", "_accent_viol_cons90.json"], "3.1")

    run([PY, "-u", "_prosody_rel.py",
         "--a", "_accent_fix_old.jsonl", "--b", "_accent_fix_new.jsonl",
         "--out", "_prosody_rel.json"], "prosody")

    print("\n[%s] P0 收尾完成，用时 %.1f 分钟" % (time.strftime("%H:%M:%S"),
                                            (time.time() - t0) / 60.0), flush=True)


if __name__ == "__main__":
    main()
