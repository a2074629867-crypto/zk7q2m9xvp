# -*- coding: utf-8 -*-
"""短句补救：把目标句和下一句一起生成，再按最长静音切开取前半。

    G:/Python310/python.exe ch123_cut2.py <key> <who> <前句> <后句>

例：ch123_cut2.py L071 C "I don't know." "To pay off all his debts."
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import bk_resplit as R
from bk_stitch import loud, rd, trim, wr
from ch123_plan import REFS

OUT = "G:/_setup/ch123"
BAK = "G:/_setup/ch123_old"
TMP = "G:/_setup/_fix_parts"
os.makedirs(BAK, exist_ok=True)
os.makedirs(TMP, exist_ok=True)


def main():
    key, who, a_txt, b_txt = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    ref, rtext = REFS[who]
    pf = os.path.join(TMP, key + "_combo.wav")
    full = a_txt + " " + b_txt
    mt = max(260, int(len(full.split()) * 30) + 160)
    ok = R.gen(full, ref, rtext, mt, pf, ["use_xvector=on"])
    if not ok:
        print("gen FAIL")
        return
    a, sr = rd(pf)
    a = trim(a, sr)
    # 帧能量，找中间最长静音
    n = int(0.01 * sr)
    k = len(a) // n
    e = np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])
    db = 20 * np.log10(e + 1e-9)
    voiced = db > -45
    # 只在 30%~75% 区间找静音，避免首尾
    lo, hi = int(k * 0.25), int(k * 0.8)
    best, cur, bs = 0, 0, None
    for i in range(lo, hi):
        if not voiced[i]:
            if cur == 0:
                start = i
            cur += 1
            if cur > best:
                best, bs = cur, start
        else:
            cur = 0
    if bs is None or best < 8:
        print("没找到足够长的静音（最长 %.2fs）" % (best * 0.01))
        return
    cut = int((bs + best / 2) * n)
    head = loud(a[:cut], sr)
    dst = os.path.join(OUT, key + ".wav")
    src = os.path.join(BAK, key + ".wav")
    if os.path.exists(dst) and not os.path.exists(src):
        import shutil
        shutil.copy2(dst, src)
    wr(dst, head, sr)
    print("%s 切出 %.2fs（静音 %.2fs @%.2fs）" % (key, len(head) / sr, best * 0.01, (bs * 0.01)))


if __name__ == "__main__":
    main()
