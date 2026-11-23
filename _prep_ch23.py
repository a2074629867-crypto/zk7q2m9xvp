# -*- coding: utf-8 -*-
"""把 ch2 / ch3 已有音频补做韵律分析（ASR → TextGrid → wpt）。

这两章 682 个单元早就有 wav，但从没跑过门禁 —— 之前只检验了 ch1 的 180 个。
只跑 seed 42 一个候选：门禁判 PASS 只需要一条就够。

    python _prep_ch23.py            # ch2+ch3
    python _prep_ch23.py --ch ch2
"""
import argparse
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
import mt_loop as L

ROOT = "G:/_setup"
SEED = 42


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch2,ch3")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    chs = {c.strip() for c in a.ch.split(",") if c.strip()}
    plan = None
    for p in ["B:/mt-tts/data/plan/mt_plan3b.json", os.path.join(ROOT, "_mt_plan3b.json")]:
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            plan = d if isinstance(d, list) else d.get("items", [])
            break
    if not plan:
        raise SystemExit("找不到 plan")

    have = {f[:-4] for f in os.listdir(os.path.join(ROOT, "_mt_raw_s%d" % a.seed))
            if f.endswith(".wav")}
    made = {}
    for it in plan:
        if it.get("ch") not in chs:
            continue
        uid = str(it.get("id"))
        if uid not in have:
            continue
        pf = os.path.join(ROOT, "_wpt_out", "_mt_raw_s%d__%s.prom" % (a.seed, uid))
        if os.path.exists(pf):
            continue
        made[uid] = (a.seed, os.path.join(ROOT, "_mt_raw_s%d" % a.seed, uid + ".wav"))
        if a.limit and len(made) >= a.limit:
            break

    print("待分析 %d 条（ch=%s, seed=%d）" % (len(made), ",".join(sorted(chs)), a.seed), flush=True)
    if not made:
        return
    staged = L.build_prom(made)
    print("完成 %d/%d，下一步：python _gate.py --json _mt_gate.json" % (len(staged), len(made)))


if __name__ == "__main__":
    main()
