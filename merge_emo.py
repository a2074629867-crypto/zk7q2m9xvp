# -*- coding: utf-8 -*-
"""合并四份标注 → 最终情绪档，并检查「档位 → 音色参考」的可实现性。

投票规则
--------
A(r_ds1) / B(r_b2) / C(r_ds3) / D(r_d4) 四人各一票：
  · ≥3 票一致 → 直接采用
  · 二比二 或 二一一 → 由第四方（r_adj，我按场景功能逐条判）定档
强度取四人中与最终档一致者的中位数；无人一致则取 2。

产物
----
_emo_vote/_emo_final.jsonl    id / who / emo / intensity / why / src / votes
_emo_vote/_emo_final.md       分布与冲突摘要
"""
import json
import collections
import statistics as st

VOTE = {
    "A": "G:/_setup/_emo_vote/r_ds1.jsonl",
    "B": "G:/_setup/_emo_vote/r_b2.jsonl",
    "C": "G:/_setup/_emo_vote/r_ds3.jsonl",
    "D": "G:/_setup/_emo_vote/r_d4.jsonl",
}
ADJ = "G:/_setup/_emo_vote/r_adj.jsonl"
CTX = "G:/_setup/_dlg_ctx.jsonl"
SIX = ["平静", "紧张", "激动反抗", "委屈", "兴奋", "警惕"]


def main():
    votes = {k: {json.loads(l)["id"]: json.loads(l)
                 for l in open(p, encoding="utf-8")} for k, p in VOTE.items()}
    adj = {json.loads(l)["id"]: json.loads(l)
           for l in open(ADJ, encoding="utf-8")}
    ctx = {json.loads(l)["id"]: json.loads(l)
           for l in open(CTX, encoding="utf-8")}
    ids = [json.loads(l)["id"] for l in open(VOTE["A"], encoding="utf-8")]

    out, stat = [], collections.Counter()
    for i in ids:
        v = [votes[k][i]["emo"] for k in "ABCD"]
        c = collections.Counter(v)
        top, n = c.most_common(1)[0]
        if n >= 3:
            emo, src = top, "vote%d" % n
        else:
            emo, src = adj[i]["emo"], "adj"
        same = [votes[k][i]["intensity"] for k in "ABCD"
                if votes[k][i]["emo"] == emo]
        inten = int(round(st.median(same))) if same else int(adj.get(i, {}).get("intensity", 2))
        why = adj[i]["why"] if src == "adj" else votes[
            [k for k in "ABCD" if votes[k][i]["emo"] == emo][0]][i]["why"]
        out.append({"id": i, "who": ctx[i]["who"], "emo": emo,
                    "intensity": max(1, min(3, inten)), "why": why,
                    "src": src, "votes": v})
        stat[src] += 1

    with open("G:/_setup/_emo_vote/_emo_final.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    dist = collections.Counter(r["emo"] for r in out)
    print("最终 %d 条" % len(out))
    print("定档来源:", dict(stat))
    print("分布:", {k: dist[k] for k in SIX})
    print("按角色:")
    by = collections.defaultdict(collections.Counter)
    for r in out:
        by[r["who"]][r["emo"]] += 1
    for who in by:
        print("  %-8s %s" % (who, dict(by[who])))

    # 单方标注与最终档的偏离度 —— 衡量哪一份离共识最远
    print("\n与最终档一致率:")
    for k in "ABCD":
        agree = sum(1 for r in out if votes[k][r["id"]]["emo"] == r["emo"])
        print("  %s: %d/%d = %.1f%%" % (k, agree, len(out), 100.0 * agree / len(out)))


if __name__ == "__main__":
    main()
