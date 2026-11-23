# -*- coding: utf-8 -*-
"""声纹诊断：用「角色质心」代替「角色内最好那一格」判归属。

问题
----
dialog_gate 的 role_max(r) = max over 该角色所有情绪格 的 z。但本库各角色
情绪覆盖是**不对等**的：

    Charles : excited / angry / soft / neutral
    Thomas  : loud / calm / scold / begging
    Joseph  : excited / defiant / wronged / wary / nervous / normal
    Helena  : excited / defiant / wronged / wary / nervous
    Fielding: excited / defiant / wronged / wary / nervous

Thomas 没有 nervous/wronged/wary/defiant 四格，Charles 没有 nervous。于是
一句「Thomas 紧张」在 Thomas 侧只能和 loud/calm/scold/begging 比，天然低分；
而 Joseph/Helena/Fielding 恰好都有 nervous 格，天然高分 —— **判错的不是音频，
是库的覆盖**。239 条里 wrong_speaker 63 条，role_top 集中在 soft/nervous 两个
「只有部分角色有」的格上，正是这个机制的指纹。

做法
----
把角色归属降成纯音色问题：每角色取全部参考的平均 embedding 作质心，
cos(音频, 质心) 最高的角色即归属。情绪不参与角色判定（情绪由 gate_emotion 管）。
"""
import os
import sys
import json

import numpy as np

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
sys.path.insert(0, "G:/voice_lib")

from chain_check import EmoVoice, SV

LIB = "G:/_setup/_emo_refs_all.json"
OUT = "G:/_setup/_spk_centroid.json"


def main():
    ev = EmoVoice(lib=LIB, bg="G:/_setup/out_sv/cues_znorm2.json")
    print("库载入 %d 条模板" % len(ev.keys), flush=True)

    # 角色质心（用 ev.mats 已在内存里，不用重新解码）
    roles = list(dict.fromkeys(k[0] for k in ev.keys))
    cent = {}
    for r in roles:
        idx = [i for i, k in enumerate(ev.keys) if k[0] == r]
        v = ev.mats[idx].mean(0)
        cent[r] = v / (np.linalg.norm(v) + 1e-9)

    plan = [json.loads(l) for l in open("G:/_setup/_dlg_plan.jsonl", encoding="utf-8")]
    rows = []
    for p in plan:
        if not os.path.exists(p["path"]):
            continue
        e = ev.m.embed(p["path"])
        e = e / (np.linalg.norm(e) + 1e-9)
        cos = {r: float(cent[r] @ e) for r in roles}
        order = sorted(cos.items(), key=lambda x: -x[1])
        rows.append({"id": p["id"], "who": p["who"],
                     "top": order[0][0], "top_cos": round(order[0][1], 4),
                     "second": order[1][0], "second_cos": round(order[1][1], 4),
                     "gap": round(order[0][1] - order[1][1], 4),
                     "cos": {k: round(v, 4) for k, v in cos.items()}})
        if len(rows) % 40 == 0:
            print("  %d/%d" % (len(rows), len(plan)), flush=True)

    ok = sum(1 for r in rows if r["top"] == r["who"])
    print("\n质心判角色：%d/%d = %.1f%%" % (ok, len(rows), 100.0 * ok / len(rows)))
    import collections
    c = collections.Counter((r["who"], r["top"]) for r in rows if r["top"] != r["who"])
    print("误判去向：", c.most_common(10))
    gaps = sorted(abs(r["gap"]) for r in rows)
    print("|gap| p10/p50/p90 %.3f/%.3f/%.3f" % (
        gaps[len(gaps) // 10], gaps[len(gaps) // 2], gaps[int(len(gaps) * 0.9)]))
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", OUT)


if __name__ == "__main__":
    main()
