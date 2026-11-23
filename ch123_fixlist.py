# -*- coding: utf-8 -*-
"""修复清单：换 emo / 拆句 / 修失败条。由 ch123_fix.py 调用。"""


def apply(fix):
    # ---------- A. 失败/吞字 ----------
    fix("L061", emo="calm", seed=43)          # "In a flat." 空文件
    fix("L071", emo="sad", seed=43)           # "I don't know." 空文件
    fix("L062", emo="calm", seed=43)          # "Your own flat?" → you're all
    fix("L078", emo="sad", seed=43)           # "No. But..." 丢了 but
    fix("I01", emo=None, seed=43)             # 丢 the

    # ---------- B. Hooper 的 angry → disgusted（angry 把音色拉跑，happy 会带笑） ----------
    for k in ("L046", "L052", "L053", "L054", "L079", "L081", "L084"):
        fix(k, emo="disgusted")

    # ---------- C. 语速过快的长句：拆句 + 标点停顿 ----------
    fix("L008", parts=[("That won't be anything new,", 0.30, "calm"),
                       ("will it?", 0.0, "calm")])

    fix("L014", parts=[("Can I have the key now,", 0.26, "calm"),
                       ("then?", 0.0, "calm")])

    fix("L030", parts=[("The butterflies were just a craze last term.", 0.40, "calm"),
                       ("We caught larvae and watched them hatch.", 0.40, "calm"),
                       ("Nobody's interested now.", 0.0, "calm")])

    fix("L055", parts=[("When my father dies, this house will belong to me.", 0.45, "calm"),
                       ("I shall be master.", 0.32, "calm"),
                       ("It'll all be mine.", 0.0, "calm")])

    fix("L059", parts=[("My grandfather died in this room.", 0.45, "calm"),
                       ("Not very long ago, either.", 0.40, "calm"),
                       ("He lay and died in that bed.", 0.42, "calm"),
                       ("Now it's your bed.", 0.0, "calm")])

    fix("L068", parts=[("Well,", 0.24, "sad"),
                       ("my mother can't afford to buy us a house, can she?", 0.40, "sad"),
                       ("We can't help that.", 0.0, "sad")])

    fix("L069", parts=[("Your father should have left you some money, then, shouldn't he?", 0.44, "calm"),
                       ("Didn't he have a house?", 0.0, "calm")])

    fix("L088", parts=[("He's old, I told you.", 0.40, "sad"),
                       ("When he was in the Battle of Britain,", 0.30, "sad"),
                       ("he was twenty.", 0.40, "sad"),
                       ("That was the war.", 0.0, "sad")])

    fix("L091", parts=[("I should think there would be about a hundred schools in Wales.", 0.44, "calm"),
                       ("More than a hundred.", 0.0, "calm")])

    fix("I00", parts=[("His skin is already dead, he thought.", 0.40),
                      ("It is old and dry.", 0.0)])
