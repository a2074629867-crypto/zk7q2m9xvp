# -*- coding: utf-8 -*-
"""按最终情绪档重建生成计划（v2）：voice 不再按后缀规则映射，改为按 LLM 定档选。

对比 v1（make_plan.py）
----------------------
v1 用三条正则：感叹号/辱骂词 → STRONG 档，句首 No/Yes/Well → SOFT 档，其余 BASE 档。
结果 `Thomas_calm_1` 被套在 69/110 条 Thomas 台词上，连 "I am never afraid." 都算平静。
v2 用四方标注（A/B/C/D + 我裁决）的最终档，逐句对到「该角色实际有的那一格」。

音色库的硬约束（必须先暴露，不能假装能满足）
------------------------------------------
本库各角色的情绪格**不对等**：

    Charles : excited / angry / soft / neutral
    Thomas  : loud / calm / scold / begging
    Joseph  : excited / defiant / wronged / wary / nervous / normal
    Helena  : excited / defiant / wronged / wary / nervous

于是：
    · Charles 的「紧张」(26 条) 与「警惕」(5 条) 无对应格
    · Thomas 的「紧张」(1 条) 与「兴奋」(5 条) 无对应格
    · Helena 的「平静」(1 条) 无中性格

这些行不是「标错了」，是**库缺档**。脚本会给它们标 emo_unsupported=true 并退到最近的
可用格（低唤醒→neutral/calm，高唤醒→loud/excited），同时在报告里单独列出 ——
否则这一批会被当成「生成失败」反复重跑，跑多少次都不会对。
"""
import json
import re
import collections

PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
FINAL = "G:/_setup/_emo_vote/_emo_final.jsonl"
SRC = "G:/_setup/_castle_en_ch123_cast.jsonl"
OUT_PLAN = "G:/_setup/_castle_en_ch123_plan_v4.jsonl"
OUT_GATE = "G:/_setup/_dlg_plan_v3.jsonl"

# (角色名, 情绪档) -> 音色档名；None = 该角色没有这一格
# ★ 2026-11-24 用户定调：**「紧张」取消专用档，全部走平静**。
#   依据：「紧张不是小声+停顿多吗？作者没写这种停顿就用平常说话。」
#   实测：39 条紧张里仅 8 条带省略号，25 条 Charles 紧张中 9 条是 1 词短句；
#   紧张 F0 中位 256 vs 平静 246 —— 物理上同一档。
#   旧映射把 Charles 紧张指到 nervous（素材 F0 335 = 喊）→「喊着说话」的根因。
#   V 里填 None + FALLBACK 指向平静档，且标记 tense_flat（不是库缺档）。
V = {
    "Charles": {"平静": "Charles_neutral_1", "兴奋": "Charles_excited_1",
                "激动反抗": "Charles_angry_1", "委屈": "Charles_soft_1",
                "紧张": None, "警惕": None},
    "Thomas": {"平静": "Thomas_calm_1", "兴奋": None,
               "激动反抗": "Thomas_loud_1", "委屈": "Thomas_begging_1",
               "紧张": None, "警惕": "Thomas_scold_1"},
    "Joseph": {"平静": "Joseph_normal_1", "兴奋": "Joseph_excited_1",
               "激动反抗": "Joseph_defiant_1", "委屈": "Joseph_wronged_1",
               "紧张": None, "警惕": "Joseph_wary_1"},
    "Helena": {"平静": None, "兴奋": "Helena_excited_1",
               "激动反抗": "Helena_defiant_1", "委屈": "Helena_wronged_1",
               "紧张": None, "警惕": "Helena_wary_1"},
}
# 缺档时的退路：取该角色**有**的最近格
FALLBACK = {
    "Charles": {"紧张": "Charles_neutral_1", "警惕": "Charles_soft_1"},
    "Thomas": {"兴奋": "Thomas_loud_1", "紧张": "Thomas_calm_1"},
    "Joseph": {"紧张": "Joseph_normal_1"},
    "Helena": {"平静": "Helena_wary_1", "紧张": "Helena_wary_1"},
}
WHO_MAP = {"Edmund": "Thomas", "Other": "Helena"}


# ★ 2026-11-24 用户定调（精确版）：
#   「紧张不是那种小声说话、停顿比较多的吗？如果说作者没有写到这种比较多停顿的话，
#    就不用啊，那就平常说话就行了。」
#   ⇒ **按文本分流**，不是一刀切：
#     带停顿标记（省略号 / 破折号）→ 该角色的小声档（只有 Charles 有 soft 可用）
#     没有停顿标记                → 该角色平静档（平常说话）
#   旧做法（固定指 Charles_nervous 素材 F0 335）生成出「喊着说话」，被用户当场否掉。
_TENSE_MARK = re.compile(r"(\.\.\.|\u2026|\u2014|\u2013)")


def tense_pick(who, text):
    """返回 (voice, 是否带停顿标记)。"""
    marked = bool(_TENSE_MARK.search(text or ""))
    calm = {"Charles": "Charles_neutral_1", "Thomas": "Thomas_calm_1",
            "Joseph": "Joseph_normal_1", "Helena": "Helena_wary_1"}[who]
    soft = {"Charles": "Charles_soft_1"}      # 只有 Charles 库里有小声档
    if marked and who in soft:
        return soft[who], True
    return calm, marked



def main():
    fin = {json.loads(l)["id"]: json.loads(l) for l in open(FINAL, encoding="utf-8")}
    rows = [json.loads(l) for l in open(PLAN, encoding="utf-8")]
    cast = {json.loads(l)["id"]: json.loads(l) for l in open(SRC, encoding="utf-8")}

    out, gate, uns, tense = [], [], [], []
    for r in rows:
        sp = r["speaker"]
        if sp == "narrator":
            out.append(r)
            continue
        fid = fin.get(r["id"])
        if not fid:
            out.append(r)
            continue
        who = WHO_MAP.get(sp, sp)
        emo = fid["emo"]
        name = V[who].get(emo)
        flag = False
        if emo == "紧张":
            name, marked = tense_pick(who, r.get("text", ""))
            tense.append((r["id"], who, name, marked))
            r = dict(r)
            r.update({"voice": name, "emo": emo, "emo_intensity": fid["intensity"],
                      "emo_src": fid["src"], "emo_why": fid["why"],
                      "emo_unsupported": False, "tense_flat": True,
                      "tense_marked": marked,
                      "text_src": cast.get(r["id"], {}).get("text", r["text"])})
            out.append(r)
            gate.append({"path": "G:/_setup/_audio_ch123/out/%s.wav" % r["id"],
                         "who": who, "emo": emo, "id": r["id"], "text": r["text_src"]})
            continue
        if not name:
            name = FALLBACK.get(who, {}).get(emo) or V[who]["平静"] or "Joseph_normal_1"
            # 「紧张」不是库缺档，是刻意走平静（2026-11-24 用户定调）
            flag = (emo != "紧张")
            if emo == "紧张":
                tense.append((r["id"], who, name))
            else:
                uns.append((r["id"], who, emo, name))
        r = dict(r)
        r.update({"voice": name, "emo": emo, "emo_intensity": fid["intensity"],
                  "emo_src": fid["src"], "emo_why": fid["why"],
                  "emo_unsupported": flag,
                  "tense_flat": (emo == "紧张"),
                  "text_src": cast.get(r["id"], {}).get("text", r["text"])})
        out.append(r)
        gate.append({"path": "G:/_setup/_audio_ch123/out/%s.wav" % r["id"],
                     "who": who, "emo": emo, "id": r["id"], "text": r["text_src"]})

    with open(OUT_PLAN, "w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_GATE, "w", encoding="utf-8", newline="\n") as f:
        for r in gate:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("计划 %d 行 → %s" % (len(out), OUT_PLAN))
    print("对白 %d 条 → %s" % (len(gate), OUT_GATE))
    print("voice 分布:")
    for k, v in collections.Counter(r["voice"] for r in out if r["speaker"] != "narrator").most_common():
        print("   %-22s %d" % (k, v))
    print("库缺档 %d 条（%.1f%%）:" % (len(uns), 100.0 * len(uns) / max(1, len(gate))))
    for k, v in collections.Counter((w, e) for _, w, e, _ in uns).most_common():
        print("   %-8s %-6s %d" % (k[0], k[1], v))
    print("紧张→平静 %d 条（tense_flat，非缺档）:" % len(tense))
    for k, v in collections.Counter((w, n, m) for _, w, n, m in tense).most_common():
        print("   %-8s -> %-20s 停顿标记=%-5s %d" % (k[0], k[1], k[2], v))


if __name__ == "__main__":
    main()
