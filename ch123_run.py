# -*- coding: utf-8 -*-
"""前三章台词生成（串行，断点续跑）。

    G:/Python310/python.exe ch123_run.py [起始序号] [结束序号]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import INNER, PLAN, REFS

OUT = "G:/_setup/ch123"
LOG = "G:/_setup/_ch123_log.json"
os.makedirs(OUT, exist_ok=True)

ITEMS = [dict(k="L%03d" % i, who=w, emo=e, text=t) for i, w, e, t in PLAN]
ITEMS += [dict(k="I%02d" % i, who=w, emo=e, text=t) for i, (_, w, e, t) in enumerate(INNER)]


def main():
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    b = int(sys.argv[2]) if len(sys.argv) > 2 else len(ITEMS)
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}
    for n, it in enumerate(ITEMS[a:b], start=a):
        out = os.path.join(OUT, it["k"] + ".wav")
        if os.path.exists(out) and os.path.getsize(out) > 60000:
            print("[skip] %s" % it["k"], flush=True)
            continue
        ref, rtext = REFS[it["who"]]
        body = it["text"]
        if it["emo"]:
            body = "<emo, type=%s, level=2>%s</emo>" % (it["emo"], it["text"])
        mt = max(200, int(len(it["text"].split()) * 26) + 160)
        t0 = time.time()
        ok = R.gen(body, ref, rtext, mt, out, ["use_xvector=on"])
        if not ok:
            time.sleep(15)
            ok = R.gen(body, ref, rtext, mt, out, ["use_xvector=on"])
        size = os.path.getsize(out) if os.path.exists(out) else 0
        log[it["k"]] = dict(who=it["who"], emo=it["emo"], text=it["text"],
                            ok=bool(ok), size=size, sec=round(time.time() - t0, 1))
        json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("%3d/%d %-5s %-11s %5.1fs %s  %s" %
              (n + 1, len(ITEMS), it["k"], it["emo"] or "-", time.time() - t0,
               "OK" if ok else "FAIL", it["text"][:58]), flush=True)
        time.sleep(11)
    print("DONE %d items" % (b - a), flush=True)


if __name__ == "__main__":
    main()
