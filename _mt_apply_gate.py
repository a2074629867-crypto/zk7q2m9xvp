# -*- coding: utf-8 -*-
"""_mt_apply_gate.py —— 把新跑出来的 _mt_gate.json 刷回 state。

为什么需要它：`mt_loop.py --init` 只把「state 里还没有的单元」加进去
（`if uid in st["units"]: continue`），已有单元的 tries 不会更新。
门禁口径一改（2026-10-30 修了缩写 / 粘连数字 / 切词三类假阳性），
就必须把新判定刷进 state，否则回环仍按旧结果去重生成。

保留原有 `round` 字段（第几轮生成的），其余按新 gate 结果覆盖。

用法：
    G:/Python310/python.exe _mt_apply_gate.py            # 预演，只打印差异
    G:/Python310/python.exe _mt_apply_gate.py --write    # 落盘
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mt_loop as L  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", default=os.path.join(ROOT, "_mt_gate.json"))
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    L.load_audit()
    st = L.load_state()
    rows = json.load(open(a.gate, encoding="utf-8"))
    by = defaultdict(list)
    for r in rows:
        by[r["uid"]].append(r)

    diff = Counter()
    changed = []
    for uid, rs in by.items():
        u = st["units"].get(uid)
        if not u:
            continue
        old = {(t["seed"], t["wav"]): t for t in u.get("tries", [])}
        new_tries = []
        for r in rs:
            key = (str(r["seed"]), "_mt_raw_s%s/%s.wav" % (r["seed"], uid))
            prev = old.get(key, {})
            t = dict(seed=str(r["seed"]), wav=key[1], verdict=r["verdict"], code=r["code"],
                     sep=r["sep"], top1=r["top1"], pos=r["pos"], n=r["n"], gap=r["gap"],
                     cov=r.get("cov"), round=prev.get("round", 0))
            if prev and prev.get("verdict") != t["verdict"]:
                diff[(prev["verdict"], t["verdict"])] += 1
                changed.append((uid, t["seed"], prev["verdict"], prev["code"],
                                t["verdict"], t["code"]))
            new_tries.append(t)
        u["tries"] = new_tries
        u["state"] = L.unit_verdict(new_tries, uid)
        u["pick"] = L.pick_best(new_tries, uid)

    print("覆盖单元 %d 个，判定变化 %s" % (len(by), dict(diff)))
    for c in changed[:15]:
        print("  %-6s s%-5s %-9s(%s) -> %-9s(%s)" % c)
    if len(changed) > 15:
        print("  ... 共 %d 条" % len(changed))

    if a.write:
        L.save_state(st)
        print("已写回 state")
    else:
        print("（预演，加 --write 落盘）")


if __name__ == "__main__":
    main()
