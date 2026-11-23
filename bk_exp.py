# -*- coding: utf-8 -*-
"""实验：中性参考锚音色 + emo 标签控情绪。

    G:/Python310/python.exe bk_exp.py <tag> <refGroup> <suffix> [emoType]

例：bk_exp.py 4 1_charles_normal nref
    bk_exp.py 4 1_charles_normal nrefangry angry
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R

TMP2 = "G:/_setup/dots_edit2/_exp"


def main():
    tag, refg, suffix = sys.argv[1], sys.argv[2], sys.argv[3]
    emo = sys.argv[4] if len(sys.argv) > 4 else None
    gid, full, parts = R.SPLIT[tag]
    ref = os.path.join(R.REF, refg + ".wav")
    rtext = R.REF_TEXT[refg]
    os.makedirs(TMP2, exist_ok=True)
    print("tag=%s ref=%s emo=%s parts=%d" % (tag, refg, emo, len(parts)), flush=True)
    for i, (txt, gap) in enumerate(parts):
        body = txt
        if emo:
            body = "<emo, type=%s, level=2>%s</emo>" % (emo, txt)
        pf = os.path.join(TMP2, "E%s_%s_p%d.wav" % (tag, suffix, i))
        mt = max(200, int(len(txt.split()) * 26) + 160)
        extra = ["use_xvector=on"] if (emo or "xv" in suffix) else None
        ok = R.gen(body, ref, rtext, mt, pf, extra)
        print("  [%d] %-40s %s" % (i, body[:40], "OK" if ok else "FAIL"), flush=True)
        if not ok:
            time.sleep(15)
            ok = R.gen(body, ref, rtext, mt, pf, extra)
            print("       retry ->", "OK" if ok else "FAIL", flush=True)
        time.sleep(12)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
