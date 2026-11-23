# -*- coding: utf-8 -*-
"""verify_lib.py —— 多角色参考库自检：留一法 + 跨角色混淆矩阵。

为什么要单独一个脚本
--------------------
建库脚本（build_cast_refs.py）只看「自己 vs 别的库」，而且一次只建一个角色。
把 5 个角色的库合起来之后，真正要回答的是两件事：
  1. 每条模板拿掉自己，最近的同类模板是不是**同一个人**（留一法）；
  2. 会不会把别的角色吸走（跨角色混淆）——这是加新人最常犯的错，
     法语片那次 L071/L078 两条 Charles 轻声句就是被成年女模板吸走的。

用法
----
  python verify_lib.py --lib _emo_refs_all.json
  python verify_lib.py --lib A.json --lib B.json      # 对比两版
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")


def load(lib_path, sv):
    d = json.load(open(lib_path, encoding="utf-8"))
    rows = []
    for role, slots in d.items():
        for slot, items in slots.items():
            for it in items:
                p = it["path"] if isinstance(it, dict) else it
                if not os.path.exists(p):
                    continue
                rows.append({"role": role, "slot": slot, "path": p,
                             "text": (it.get("text") if isinstance(it, dict) else "") or "",
                             "f0": (it.get("f0") if isinstance(it, dict) else None)})
    E = np.array([sv.embed(r["path"]) for r in rows], dtype=np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    return rows, E


def report(path, sv):
    rows, E = load(path, sv)
    print("\n=== %s ：%d 角色 / %d 条模板" % (os.path.basename(path), len(set(r["role"] for r in rows)), len(rows)))
    cnt = collections.Counter((r["role"], r["slot"]) for r in rows)
    for role in dict.fromkeys(r["role"] for r in rows):
        slots = [(s, n) for (rl, s), n in cnt.items() if rl == role]
        f0s = [r["f0"] for r in rows if r["role"] == role and r["f0"]]
        print("  %-9s %2d 档 %2d 条  %s  F0 %s" % (
            role, len(slots), sum(n for _, n in slots),
            " ".join("%s:%d" % x for x in slots),
            ("%.0f" % np.median(f0s)) if f0s else "?"))

    ok = n = 0
    conf = collections.Counter()
    for i, r in enumerate(rows):
        same = [j for j, o in enumerate(rows) if o["role"] == r["role"] and j != i]
        if not same:
            continue
        s = E @ E[i]
        bs = max(float(s[j]) for j in same)
        best_other = max((j for j in range(len(rows)) if rows[j]["role"] != r["role"]),
                         key=lambda j: s[j], default=None)
        hit = bs >= (float(s[best_other]) if best_other is not None else -1)
        ok += hit
        n += 1
        if not hit:
            conf[(r["role"], rows[best_other]["role"])] += 1
            if sum(conf.values()) <= 10:
                print("  ✗ %-9s %-9s 组内 %.3f < %s %.3f  | %s" % (
                    r["role"], r["slot"], bs, rows[best_other]["role"],
                    s[best_other], r["text"][:38]))
    print("  留一法（组内 >= 跨角色） %d/%d = %.1f%%" % (ok, n, 100.0 * ok / max(1, n)))
    if conf:
        print("  被吸走的方向：%s" % dict(conf))
    return ok, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", action="append", required=True)
    a = ap.parse_args()
    from sv_onnx import SV
    sv = SV(name="r34")
    for p in a.lib:
        report(p, sv)


if __name__ == "__main__":
    main()
