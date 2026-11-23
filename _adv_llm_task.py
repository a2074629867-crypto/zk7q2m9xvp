# -*- coding: utf-8 -*-
"""生成「副词该不该慢读」的 LLM 盲标任务。

每个单元只出一次（与 seed 无关）。匿名化为 A01..A83，key 单独存。
"""
import json
import os
import random
import re

ROOT = "G:/_setup"
PLAN = "B:/mt-tts/data/plan/mt_plan3b.json"
OUT = os.path.join(ROOT, "_adv_task")
NOT_ADV = set("""
family reply apply supply rely belly jelly fly holy ugly silly lily ally rally
monopoly melancholy assembly anomaly italy july polly nelly billy willy dolly
holly kelly sally tilly emily cecily multiply imply comply deny
body study carry marry worry try dry cry fry pry spy shy sly ply buy guy say
day way may pay lay play stay gray grey they key eye valley alley journey money
honey monkey donkey chimney hockey jockey trolley volley barley bailey parsley
galley early daily weekly monthly yearly hourly friendly lovely lonely likely
unlikely deadly lively elderly orderly cowardly
""".split())


def adverbs(text):
    out = []
    for m in re.finditer(r"[A-Za-z][A-Za-z']*", text):
        w = m.group(0)
        lw = w.lower()
        if lw.endswith("ly") and len(lw) > 4 and lw not in NOT_ADV:
            out.append(w)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    d = json.load(open(PLAN, encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("items", [])

    # 只保留含副词的单元；按章聚合以便取上下文
    by_ch = {}
    for i, it in enumerate(items):
        by_ch.setdefault(it.get("ch"), []).append((i, it))

    tasks = []
    for ch, lst in by_ch.items():
        for k, (gi, it) in enumerate(lst):
            uid = str(it["id"])
            advs = adverbs(it.get("text", ""))
            if not advs:
                continue
            prev = lst[k - 1][1]["text"] if k > 0 else ""
            nxt = lst[k + 1][1]["text"] if k + 1 < len(lst) else ""
            tasks.append({
                "uid": uid,
                "ch": ch,
                "prev": prev,
                "sentence": it["text"],
                "next": nxt,
                "candidates": advs,
            })

    random.seed(20261026)
    order = list(range(len(tasks)))
    random.shuffle(order)
    blind = []
    key = {}
    for n, oi in enumerate(order, 1):
        t = tasks[oi]
        aid = "A%02d" % n
        key[aid] = {"uid": t["uid"], "ch": t["ch"], "candidates": t["candidates"]}
        blind.append({
            "id": aid,
            "prev": (t["prev"] or "")[:220],
            "sentence": t["sentence"],
            "next": (t["next"] or "")[:220],
            "candidates": t["candidates"],
        })

    parts = 3
    sz = (len(blind) + parts - 1) // parts
    for p in range(parts):
        seg = blind[p * sz:(p + 1) * sz]
        if not seg:
            continue
        fn = os.path.join(OUT, "task_p%d.json" % (p + 1))
        json.dump(seg, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("part%d: %d 条  %s..%s" % (p + 1, len(seg), seg[0]["id"], seg[-1]["id"]))

    json.dump(key, open(os.path.join(OUT, "key.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("总单元 %d" % len(blind))
    print("\n示例：")
    print(json.dumps(blind[:2], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
