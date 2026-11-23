# -*- coding: utf-8 -*-
"""合并 meta + asr → _ch123_final.json

    G:/Python310/python.exe ch123_merge.py
"""
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def norm(s):
    s = s.lower().replace("’", "'").replace("‘", "'")
    s = re.sub(r"[^a-z' ]+", " ", s)
    return [w for w in s.split() if w]


def main():
    meta = json.load(open("G:/_setup/_ch123_meta.json", encoding="utf-8"))
    asr = json.load(open("G:/_setup/_ch123_asr.json", encoding="utf-8"))

    import ch123_fixlist as L
    fixmap = {}

    def rec(key, emo=None, parts=None, seed=42):
        fixmap[key] = dict(emo=emo, parts=parts, seed=seed)
    L.apply(rec)

    res = {}
    for k, d in meta.items():
        hyp = asr.get(k, "")
        rw, hw = norm(d["text"]), norm(hyp)
        acc = int(difflib.SequenceMatcher(None, rw, hw).ratio() * 100) if hyp else 0
        fx = fixmap.get(k, {})
        emo = "拆句" if fx.get("parts") else (fx.get("emo") if "emo" in fx else None)
        res[k] = dict(who=d["who"], text=d["text"], emo=emo,
                      fixed=bool(fx), split=bool(fx.get("parts")),
                      dur=d["dur"], wpm=d["wpm"], vwpm=d["vwpm"], f0=d["f0"],
                      tail=d["tail"], spk=d["spk"], acc=acc, asr=hyp)
        print("%-5s %-2s %-9s %5.2fs 声纹 %.2f 词准 %3d%%" %
              (k, d["who"], emo or "-", d["dur"], d["spk"], acc), flush=True)

    json.dump(res, open("G:/_setup/_ch123_final.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    n = len(res)
    low = [k for k, v in res.items() if v["spk"] < 0.5]
    bad = [k for k, v in res.items() if v["acc"] < 80]
    print("OK", n, "声纹<0.5:", low, "词准<80:", bad)


if __name__ == "__main__":
    main()
