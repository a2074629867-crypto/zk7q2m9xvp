# -*- coding: utf-8 -*-
"""python310：跑 probe（时长/语速/F0/句尾）+ 声纹 → _ch123_meta.json

    G:/Python310/python.exe ch123_meta.py
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ch123_probe as P
from ch123_plan import INNER, PLAN

OUT = "G:/_setup/ch123"
PY = "C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
SPK = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/spk_embed.py"
ANCHOR = {"C": "G:/_setup/castle_fr_ref/CH_neutral.wav",
          "E": "G:/_setup/castle_fr_ref/6_hooper_calm.wav"}


def main():
    items = [dict(k="L%03d" % i, who=w, text=t) for i, w, e, t in PLAN]
    items += [dict(k="I%02d" % i, who=it[1], text=it[3]) for i, it in enumerate(INNER)]
    items.sort(key=lambda x: x["k"])

    spk = {}
    for who, anchor in ANCHOR.items():
        files = [os.path.join(OUT, it["k"] + ".wav") for it in items if it["who"] == who]
        files = [f for f in files if os.path.exists(f)]
        if not files:
            continue
        r = subprocess.run([PY, SPK, "--cmn", anchor] + files, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        for line in r.stdout.splitlines():
            mm = re.match(r"^([LI]\d+)\.wav\s+([0-9.]+)", line.strip())
            if mm:
                spk[mm.group(1)] = float(mm.group(2))

    res = {}
    for it in items:
        k = it["k"]
        p = os.path.join(OUT, k + ".wav")
        if not os.path.exists(p):
            continue
        pr = P.probe(p, len(it["text"].split()))
        res[k] = dict(who=it["who"], text=it["text"],
                      dur=round(pr["dur"], 2), wpm=round(pr["wpm"] or 0),
                      vwpm=round(pr["vwpm"] or 0), f0=round(pr["f0"], 1),
                      tail=round(pr["tail"], 1) if pr["tail"] is not None else None,
                      spk=round(spk.get(k, 0), 2))
        print("%-5s %-2s %5.2fs %4d wpm F0 %6.1f 尾 %6.1f 声纹 %.2f" %
              (k, it["who"], pr["dur"], pr["wpm"] or 0, pr["f0"],
               pr["tail"] if pr["tail"] is not None else 0, spk.get(k, 0)), flush=True)

    json.dump(res, open("G:/_setup/_ch123_meta.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("OK", len(res))


if __name__ == "__main__":
    main()
