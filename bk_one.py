# -*- coding: utf-8 -*-
"""单句重生成，覆盖 _split 里的指定分句。

    G:/Python310/python.exe bk_one.py <tag> <partIdx> "<text>"

例：bk_one.py 5 4 "I could do anything at all."
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R


def main():
    tag, idx, text = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    gid = R.SPLIT[tag][0]
    ref = os.path.join(R.REF, gid + ".wav")
    rtext = R.REF_TEXT[gid]
    pf = os.path.join(R.TMP, "BK%s_p%d.wav" % (tag, idx))
    mt = max(180, int(len(text.split()) * 22) + 120)
    print("gen BK%s_p%d  mt=%d  %s" % (tag, idx, mt, text), flush=True)
    for attempt in range(3):
        ok = R.gen(text, ref, rtext, mt, pf)
        print("  attempt %d -> %s" % (attempt + 1, "OK" if ok else "FAIL"), flush=True)
        if ok:
            return
        time.sleep(15)
    print("GIVE UP", flush=True)


if __name__ == "__main__":
    main()
