# -*- coding: utf-8 -*-
"""build_narr_rate.py —— 旁白回环第 2 环：给每段叙述定 rate。

为什么需要它
  旁白回环 = 麦康纳母带学来的「语速 + 停顿」两套参数。语速这一侧原本由
  narr_rate_plan.json 驱动（chapter_run.py 读它）。这一轮改成逐句生成后，
  rate 字段整个丢了 —— 716 条叙述会以模型默认语速平推，等于把旁白的
  起伏抹平。本脚本把 rate 重新算出来并按硬约束夹好。

判据来源（不是拍脑袋）
  - 区间 0.72~0.84：narr_slow_llm.py 实测，0.70 会丢整句
  - 相邻段差 ≤0.06：避免突兀跳变
  - 减速段词数 ≤20%：否则整章都慢 = 没有对比
  - rate ≤0.72 最多 1 段/章：极端减速是稀缺资源
  - 段落 25~160 词：低于 25 没有场景可判，高于 160 单次生成会截断

切段规则
  只在「连续的 narrator 行」内切 —— 对白插进来就断段，因为语速上下文断了。

输出
  原地更新 plan jsonl，给叙述行加 rate / narr_seg / narr_why 三个字段。

⛔ 2026-11-16：BASE_RATE 0.80 作废 —— 那是「整本慢 20%」，用户十月已两次否掉
   （10-22「速度你变了吗？感觉不如原速度」/ 10-30「不降速好了，太奇怪了」）。
   默认应是 **1.00 原速**。本脚本用 `rate = BASE_RATE + dr` 建模，正偏移（略快段）
   在 base 1.00 下会撞 RATE_MAX 0.84 夹死，**不要直接把常量改成 1.00 就重跑**：
   要重跑先把 SCENES 的 dr 全改成 ≤0、RATE_MAX 放到 1.00、并重定「入选块最慢值」。
"""
import argparse
import json
import re
from collections import Counter

BASE_RATE = 0.80
RATE_MIN, RATE_MAX = 0.72, 0.84
SEG_MIN, SEG_MAX = 80, 200
DELTA_MAX = 0.06
SLOW_COVER_MAX = 0.22
EXTREME_MAX = 1

# 城堡之王是哥特式心理小说，场景谱跟《Wonder》完全不同：
# 恐惧/屈辱/对峙是主轴，没有温情睡前场景。
# ⚠️ 词表只用「强标记词」：observe 那类 room/door/wall 几乎每段都有，
#    做进去只会让一切都变 -0.010，等于没判。moved/went/came 同理。
SCENES = {
    # 恐惧、压迫、身体不适 —— 这一类必须慢，慢才压得住
    "dread": (["afraid", "frightened", "terrified", "terror", "horror",
               "nightmare", "shuddered", "trembled", "panic", "nausea",
               "dread", "fear", "suffocated", "trapped", "sickened",
               "shrank", "cringed", "shivered"], -0.032),
    # 对峙、敌意、羞辱 —— 慢一点才有重量
    "confront": (["hated", "hate", "glared", "sneered", "mocked", "taunted",
                  "refused", "defiant", "contempt", "disgust", "fury",
                  "furious", "cruel", "spite", "jeered", "bullied"], -0.026),
    # 动作推进 —— 不能拖
    "motion": (["ran", "run", "running", "hurried", "dashed", "rushed",
                "scrambled", "jumped", "grabbed", "slammed", "climbed",
                "pulled", "pushed", "swung", "kicked"], 0.030),
    # 回忆、时间跳跃、内心活动
    "memory": (["remembered", "remember", "wondered", "imagined", "supposed",
                "used to", "had been", "believed", "recalled"], -0.014),
}

CH_ORDER = ["Chapter One", "Chapter Two", "Chapter Three"]

_PAT_CACHE = {}


def _hits(low, k):
    """整词匹配。⛔ 不能用 str.count：'grandmother' 里有 'ran'、'whatever' 里有
    'hate'，子串匹配会把整章都判成 motion/confront。"""
    p = _PAT_CACHE.get(k)
    if p is None:
        p = re.compile(r"\b" + re.escape(k) + r"\b")
        _PAT_CACHE[k] = p
    return len(p.findall(low))


def profile(text):
    """场景 → rate 增量。取「最强场景」不叠加，避免一路压到下限。"""
    low = text.lower()
    best = None
    for name, (kws, dr) in SCENES.items():
        c = sum(_hits(low, k) for k in kws)
        if not c:
            continue
        # 归一：出现 3 次即满强度
        strength = min(c, 3) / 3.0
        score = strength * abs(dr)
        if best is None or score > best[0]:
            best = (score, dr, name, c)
    if best is None:
        rate, tags = BASE_RATE, "neutral"
    else:
        _, dr, name, c = best
        rate, tags = BASE_RATE + dr, "%s×%d" % (name, c)

    # 短句密集（≤6 词占 40% 以上）= 断奏式描写，略放慢
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if len(sents) >= 3:
        shorts = sum(1 for s in sents if len(s.split()) <= 6)
        if shorts / len(sents) >= 0.40:
            rate -= 0.010
            tags += ",staccato"
    return round(max(RATE_MIN, min(RATE_MAX, rate)), 2), tags


def build_segments(rows):
    """只在连续 narrator 行内切段。返回 [(seg_id, [row_idx...], text)]"""
    segs = []
    cur, cur_w, n = [], 0, 0
    for i, r in enumerate(rows):
        if r["speaker"] != "narrator":
            if cur:
                segs.append((cur, " ".join(rows[j]["text"] for j in cur)))
                cur, cur_w = [], 0
            continue
        w = len(r["text"].split())
        if cur and cur_w + w > SEG_MAX:
            segs.append((cur, " ".join(rows[j]["text"] for j in cur)))
            cur, cur_w = [], 0
        cur.append(i)
        cur_w += w
        if cur_w >= SEG_MIN:
            segs.append((cur, " ".join(rows[j]["text"] for j in cur)))
            cur, cur_w = [], 0
    if cur:
        segs.append((cur, " ".join(rows[j]["text"] for j in cur)))
    return segs


def constrain(segs):
    """硬约束：中值滤波 → 相邻差 ≤0.06 → 减速占比 ≤22% → 极端 ≤1 段/章。

    为什么不做中值滤波：段落本来就切在「叙述连续段」上，恐惧场景常常只有
    一两段，中值滤波会把它们全部抹回 0.80 —— 实测 258 段时 rate 跨度塌到
    0.79~0.83（只有 0.04），等于没有起伏。改回段长 80~200 词，让场景自己
    稳定下来，比事后抹平滑更接近真人朗读。
    """
    # 1) 相邻差限幅
    for k in range(1, len(segs)):
        prev, cur = segs[k - 1]["rate"], segs[k]["rate"]
        if abs(cur - prev) > DELTA_MAX:
            segs[k]["rate"] = round(prev + (DELTA_MAX if cur > prev else -DELTA_MAX), 2)
    # 2) 极端减速名额（按章）
    by_ch = {}
    for s in segs:
        by_ch.setdefault(s["chapter"], []).append(s)
    for ch, lst in by_ch.items():
        ext = [s for s in lst if s["rate"] <= RATE_MIN + 1e-9]
        ext.sort(key=lambda s: s["rate"])
        for s in ext[EXTREME_MAX:]:
            s["rate"] = 0.73
    # 3) 减速段词数占比 —— ⛔ 必须先牺牲「轻微减速」的段，保住深度减速。
    #    升序排会把 0.77 的恐惧段第一个拉回 0.80，等于把最该慢的地方抹平。
    total = sum(s["words"] for s in segs)
    for s in sorted(segs, key=lambda x: -x["rate"]):
        slow = sum(t["words"] for t in segs if t["rate"] < BASE_RATE)
        if total == 0 or slow / total <= SLOW_COVER_MAX:
            break
        if s["rate"] < BASE_RATE:
            s["rate"] = BASE_RATE
    # 4) 限幅后再夹一次
    for s in segs:
        s["rate"] = round(max(RATE_MIN, min(RATE_MAX, s["rate"])), 2)
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="G:/_setup/_castle_en_ch123_plan.jsonl")
    ap.add_argument("--out", default=None, help="默认原地覆盖")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.plan, encoding="utf-8")]
    segs_raw = build_segments(rows)

    segs = []
    for k, (idx_list, text) in enumerate(segs_raw):
        rate, tags = profile(text)
        segs.append(dict(
            k=k, idx=idx_list, text=text,
            chapter=rows[idx_list[0]]["chapter"],
            words=len(text.split()), rate=rate, tags=tags,
        ))
    constrain(segs)

    # 写回
    for s in segs:
        for j in s["idx"]:
            rows[j]["rate"] = s["rate"]
            rows[j]["narr_seg"] = s["k"]
            rows[j]["narr_why"] = s["tags"]

    out = a.out or a.plan
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 报告
    n_narr = sum(1 for r in rows if r["speaker"] == "narrator")
    print("叙述句 %d → 逻辑段 %d（均 %.0f 词/段）"
          % (n_narr, len(segs), sum(s["words"] for s in segs) / max(1, len(segs))))
    print("\nrate 分布：")
    for r, c in sorted(Counter(s["rate"] for s in segs).items()):
        print("  %.2f  %d 段" % (r, c))
    slow_w = sum(s["words"] for s in segs if s["rate"] < BASE_RATE)
    print("减速段词数占比 %.1f%%（上限 %.0f%%）"
          % (100.0 * slow_w / max(1, sum(s["words"] for s in segs)), SLOW_COVER_MAX * 100))
    print("\n标签分布：")
    tags = Counter()
    for s in segs:
        for t in s["tags"].split(","):
            tags[t.split("×")[0]] += 1
    for t, c in tags.most_common():
        print("  %-12s %d" % (t, c))
    print("\n最慢 8 段：")
    for s in sorted(segs, key=lambda x: x["rate"])[:8]:
        print("  %.2f %-10s %3d词 %s" % (s["rate"], s["tags"][:16], s["words"], s["text"][:70]))
    print("\n最快 4 段：")
    for s in sorted(segs, key=lambda x: -x["rate"])[:4]:
        print("  %.2f %-10s %3d词 %s" % (s["rate"], s["tags"][:16], s["words"], s["text"][:70]))


if __name__ == "__main__":
    main()
