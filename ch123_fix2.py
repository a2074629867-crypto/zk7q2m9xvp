# -*- coding: utf-8 -*-
"""第二批：L050 / L017 / L075 合并口吃（去掉 emo，多 seed 扫）。

L050  Oh, what is it? What have you found?     Charles 好奇一问 → 旧版 surprised 成了"惊讶"，很怪
L017  There's nobody to play cricket with.     Hooper 陈述 → 旧版 melancholic 听着"怪"
L075  口吃合并：I've got... + I've got a picture of him. 用户在听感上认为这是一句，
      拆两条把口吃切断了 ⇒ 整条重生成，三种口吃写法各试一版。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_resplit as R
from ch123_plan import REFS

OUT = "G:/_setup/_fix79"
os.makedirs(OUT, exist_ok=True)

L075_HEAD = "Oh, yes. Well, a bit. He was a pilot, once. He was in the Battle of Britain. "

JOBS = {
    "L050": dict(who="C", mt=320, text="Oh, what is it? What have you found?",
                 seeds=[42, 43, 44, 45, 46, 47]),
    "L017": dict(who="E", mt=280, text="There's nobody to play cricket with.",
                 seeds=[42, 43, 44, 45, 46]),
}

# L075 合并版的三种口吃写法
STUTTER = {
    "a": L075_HEAD + "I've got\u2014 I've got a picture of him.",   # em dash
    "b": L075_HEAD + "I've got, I've got a picture of him.",        # 逗号
    "c": L075_HEAD + "I've got. I've got a picture of him.",        # 句点
}

if __name__ == "__main__":
    keys = sys.argv[1:] or (list(JOBS) + ["L075"])
    for k in keys:
        if k == "L075":
            ref, rtext = REFS["C"]
            for tag, text in STUTTER.items():
                out = os.path.join(OUT, "L075_merge_%s.wav" % tag)
                if os.path.exists(out) and os.path.getsize(out) > 60000:
                    print("[skip]", out, flush=True)
                    continue
                ok = R.gen(text, ref, rtext, 720, out, ["use_xvector=on"], seed=42)
                print("L075_merge_%s     %s %7.1fKB" % (tag, "OK" if ok else "FAIL",
                                                        os.path.getsize(out) / 1e3 if ok else 0), flush=True)
            continue
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
