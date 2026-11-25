# -*- coding: utf-8 -*-
"""_adjacent_slots.py —— 检查「两个槽位夹住一个短词」的情形（碎点的真机制）。

`_pause_fix2` 剩余 9 处「注入新引入」的 A 类碎点，形态都是
  洞(长) + 0.22~0.34s 有声 + 洞(长)
不是切点漂了 20ms，而是**两个相邻槽位各自插了静音，把中间那个短词夹住了**。

用法：G:/Python310/python.exe -u _adjacent_slots.py
"""
import json
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def load_report():
    return json.load(open(os.path.join(HERE, "_pause_fix2_report.json"), encoding="utf-8"))


def words_of(sid):
    FA = json.load(open(os.path.join(HERE, "_wt_fa_cache.json"), encoding="utf-8"))
    p = os.path.join(HERE, "_regen_1123_norm", sid + ".wav")
    st = os.stat(p)
    key = "%s|%d|%d" % (os.path.basename(p), st.st_size, int(st.st_mtime))
    return FA.get(key)


def main():
    R = {r["k"]: r for r in load_report()}
    attr = json.load(open(os.path.join(HERE, "_frag_attr.json"), encoding="utf-8"))
    sids = sorted(set(attr["intro"]))
    print("注入新引入碎点的 %d 句，各句槽位相邻性：" % len(sids))
    for sid in sids:
        r = R.get(sid)
        if not r:
            print("  ", sid, "无报告")
            continue
        bs = sorted([b for b in (r.get("bounds") or []) if b.get("op") == "ins"], key=lambda b: b["t"])
        w = words_of(sid) or []
        print("  %-9s 槽位 %d 个" % (sid, len(bs)))
        for i, b in enumerate(bs):
            nxt = bs[i + 1]["t"] - b["t"] if i + 1 < len(bs) else None
            # 槽位之间有哪些词
            between = [x[2] for x in w if b["t"] < x[0] < (bs[i + 1]["t"] if nxt else b["t"] + 2)]
            print("     @%6.2f (%-10s) cur=%.2f tgt=%.2f %s  →下一个槽位 %s  夹住词 %s"
                  % (b["t"], b.get("w", ""), b.get("cur") or 0, b.get("tgt") or 0,
                     "", ("%.2fs" % nxt) if nxt else "—", between))


if __name__ == "__main__":
    main()
