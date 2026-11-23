# -*- coding: utf-8 -*-
"""前三章条目修复：换 emo / 拆句重生成 / 修失败条。

    G:/Python310/python.exe ch123_fix.py [key ...]

规则来自 FIX 表（见下方）：
    emo=None 表示不打标签
    parts=[(文本, 句末停顿秒), ...] 给出则逐句生成后拼接（句间插静音）
旧文件备份到 ch123_old/。
"""
import os
import shutil
import sys
import time

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

# key -> dict(emo=..., parts=[(text, gap), ...] 或 None, seed=int)
FIX = {}


def fix(key, emo=None, parts=None, seed=42):
    FIX[key] = dict(emo=emo, parts=parts, seed=seed)


def run(key, who, text):
    job = FIX[key]
    ref, rtext = REFS[who]
    dst = os.path.join(OUT, key + ".wav")
    src = os.path.join(BAK, key + ".wav")
    if os.path.exists(dst) and not os.path.exists(src):
        shutil.copy2(dst, src)
    t0 = time.time()
    if job["parts"]:
        pieces = []
        for i, part in enumerate(job["parts"]):
            txt, gap = part[0], part[1]
            emo = part[2] if len(part) > 2 else None
            body = "<emo, type=%s, level=2>%s</emo>" % (emo, txt) if emo else txt
            pf = os.path.join(TMP, "%s_p%d.wav" % (key, i))
            if os.path.exists(pf):
                os.remove(pf)
            mt = max(160, int(len(txt.split()) * 30) + 140)
            ok = R.gen(body, ref, rtext, mt, pf, ["use_xvector=on"], seed=job["seed"])
            if not ok:
                time.sleep(12)
                ok = R.gen(body, ref, rtext, mt, pf, ["use_xvector=on"], seed=job["seed"])
            if not ok:
                print("   FAIL part %d %s" % (i, txt), flush=True)
                return False
            a, sr = rd(pf)
            a = loud(trim(a, sr), sr)
            pieces.append(a)
            if i < len(job["parts"]) - 1 and gap > 0:
                pieces.append(np.zeros(int(gap * sr), dtype=np.float32))
            time.sleep(9)
        y = np.concatenate(pieces)
        pk = np.max(np.abs(y))
        if pk > 0.92:
            y *= 0.92 / pk
        wr(dst, y, sr)
        print("%-5s 拼接 %.2fs  %d 句  (%.1fs)" % (key, len(y) / sr, len(job["parts"]), time.time() - t0), flush=True)
    else:
        body = "<emo, type=%s, level=2>%s</emo>" % (job["emo"], text) if job["emo"] else text
        mt = max(200, int(len(text.split()) * 26) + 160)
        ok = R.gen(body, ref, rtext, mt, dst, ["use_xvector=on"], seed=job["seed"])
        if not ok:
            time.sleep(14)
            ok = R.gen(body, ref, rtext, mt, dst, ["use_xvector=on"], seed=job["seed"])
        print("%-5s %s %s  (%.1fs)" % (key, "OK" if ok else "FAIL", job["emo"] or "-", time.time() - t0), flush=True)
        if not ok:
            return False
    time.sleep(10)
    return True


def main():
    import ch123_fixlist as L
    L.apply(fix)
    from ch123_plan import INNER, PLAN
    items = {("L%03d" % i): (w, t) for i, w, e, t in PLAN}
    items.update({("I%02d" % i): (w, t) for i, (_, w, e, t) in enumerate(INNER)})
    keys = sys.argv[1:] or list(FIX.keys())
    for k in keys:
        if k not in FIX:
            print("no fix for", k)
            continue
        who, text = items[k]
        run(k, who, text)


if __name__ == "__main__":
    main()
