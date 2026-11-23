# -*- coding: utf-8 -*-
"""多 seed 扫（串行，禁并发）。按耗时从短到长排，先出结果。

L084  When did he die, I said.                                  旧版 happy 像吼 → 要冷、压着问
L005  All he looks like, is one of his dead old moths.          旧版 disgusted 过激 → 轻蔑但克制
L079  I don't believe you. You're a liar. The Battle of Britain was in the war.   旧版砖墙压缩"炸"
L088  He's old, I told you. When he was in the Battle of Britain, he was twenty. That was the war.
      拆句声音不稳 → 整句多 seed，挑声纹 + 语调跨度最优
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

OUT = "G:/_setup/_fix79"
os.makedirs(OUT, exist_ok=True)

JOBS = {
    "L084": dict(who="E", mt=260, text="When did he die, I said.",
                 seeds=[42, 43, 44, 45, 46, 47]),
    "L005": dict(who="E", mt=320, text="All he looks like, is one of his dead old moths.",
                 seeds=[42, 43, 44, 45, 46]),
    "L079": dict(who="E", mt=420,
                 text="I don't believe you. You're a liar. The Battle of Britain was in the war.",
                 seeds=[45, 46, 47, 48, 49]),
    "L088": dict(who="C", mt=620,
                 text="He's old, I told you. When he was in the Battle of Britain, he was twenty. That was the war.",
                 seeds=[42, 43, 44, 45, 46, 47, 48]),
}

if __name__ == "__main__":
    keys = sys.argv[1:] or list(JOBS)
    for k in keys:
        j = JOBS[k]
        ref, rtext = REFS[j["who"]]
        for seed in j["seeds"]:
            tag = "%s_none_s%d" % (k, seed)
            out = os.path.join(OUT, tag + ".wav")
            if os.path.exists(out) and os.path.getsize(out) > 60000:
                print("[skip]", tag, flush=True)
                continue
            ok = R.gen(j["text"], ref, rtext, j["mt"], out, ["use_xvector=on"], seed=seed)
            print("%-18s %s %7.1fKB" % (tag, "OK" if ok else "FAIL",
                                        os.path.getsize(out) / 1e3 if ok else 0), flush=True)
    print("DONE", flush=True)
