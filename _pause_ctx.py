# -*- coding: utf-8 -*-
"""_pause_ctx.py —— 情境化停顿标注任务包（对白专用）

用户 2026-11-14 23:2x：
  「对白的停顿，那就得考虑情节当时的情景了，也就是语言自然度。情境比较紧张，
   那就得按当时的情景来，所以这就需要模型自己判断了，它得有很强的判断能力。」
  「还得根据人物性格，有些人物停顿就是短一点，有些就是长一点，
   甚至有些人物不需要停顿，有些人物就要停顿。」

现有问题（`ann_spec._DLG_PAUSE`）
  给的是一条**死阶梯**（右段为空→long / 填充词→zero / that-which→short / …），
  模型只按词表和标点套，等于「按标点类型判」—— 正是需求 19-0 明令禁止的。
  任务包里也没有 `emo`、没有角色画像、没有场景紧张度。

本脚本补三样情境输入，并把判定依据从「阶梯」换成「情境 + 性格」：
  1. `emo`         该条台词的情绪（来自人工台账，已验收）
  2. `scene`       场景紧张度 0~1（相邻 ±2 条里「激动反抗/紧张/警惕」占比）
  3. `role`        角色画像（**从该角色全部台词的情绪分布统计**，不是剧情推断）
                   + 实测停顿倾向（样本不足时如实标 insufficient）

输出 `_ann/tasks_ctx/batch_XXXX.json`，字段与 annotate_prosody 的任务包兼容
（多了 emo/scene/role 三个字段，prompt 换成本文件里的版本）。

用法：
  G:/Python310/python.exe _pause_ctx.py --dry          # 只看统计
  G:/Python310/python.exe _pause_ctx.py --batch 12     # 生成任务包
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
HABIT = "G:/_setup/_role_pause_habit.json"
OUT_DIR = "G:/_setup/_ann/tasks_ctx"

TENSE = {"激动反抗", "紧张", "警惕"}

PROMPT = """你是《The Castle of the King》有声书的**对白导演**。这一批全是人物台词。

你的任务不是套规则，而是**按这一场戏的处境和这个人的性格**，判断每处标点该停多久。

## 你会看到每条台词的这些信息

- `emo`：这句的情绪（平静 / 紧张 / 警惕 / 激动反抗 / 委屈 / 兴奋），已由人工台账验收
- `scene`：场景紧张度 0~1（同一段落前后 ±2 句里「激动反抗/紧张/警惕」的占比）
- `role`：这个角色的画像 —— **依据是他全部台词的情绪分布**，不是剧情猜测
- `prev` / `next`：同一段落里的前后句
- `slots`：要你判的每一处标点（`left` 是标点左侧 6 词，`right` 是右侧 6 词）

## 怎么判

**先定这一句的整体呼吸**，再定每一处：

1. **场景紧 + 情绪冲（scene ≥0.6 或 emo∈{激动反抗,警惕}）**
   整个人在抢话/对峙，句子之间挤在一起。全句基准往短压。
   但如果这处是**把话压给对方**（说完就等着看反应）或**信息揭示**，这一处反而要拉长——
   紧张场景里的沉默比说话更重。

2. **场景松 + 情绪低（scene ≤0.3 且 emo∈{平静,委屈}）**
   有空间。一般短语间可以正常停；情绪落点（委屈、认输、告别）拉长。

3. **性格基线**（看 `role`）
   - 话急的角色：整体再压一档，能连读就连读
   - 话慢的角色：整体抬一档，落点更长
   - `role` 里写 `insufficient` 的（样本太少），按 emo 判，不要猜性格

4. **性格 × 情绪交叉**（这是最容易出错的地方）
   - 强势角色 + 激动：抢话，句中断点大量 `zero`，只在真正换气处给 `short`
   - 弱势角色 + 委屈：哽咽，句子中间会有**不自然的短促停顿**（`short`），句末拉长
   - 强势角色 + 平静：克制，停顿干净利落，`mid` 为主，不用 `long`
   - 任何角色 + 警惕：压低、放慢、句子被切成小段，`short` 多

## 四档（只输出档位，秒数由下游换算）

| tier | 语义 | 秒 |
|---|---|---|
| `zero` | 真连读，一个字都不停 | 0 |
| `short` | 抢话、对抗、急促、从句未完、哽咽的碎停 | 0.20 |
| `mid` | 一般短语之间；一个意思说完但话没完 | 0.49 |
| `long` | 情绪落点、信息揭示、把话压给对方、这段说完 | 0.68 |

## 硬边界（这几条不能破）

- **句末（`right` 为空）不许 `zero`**：`next` 为空 → `long`；`next` 非空 → `mid`
- **`zero` 只给真正连读**：`ago, either` 这种被拆开的词组、口吃重复（`not, not`）、
  单独成段的填充词（Well / Oh / Look / then）。**不许**把情绪停顿、信息落点给成 `zero`
- 一处 `zero` 后面紧跟 `mid`/`long` 是正常的（连读之后停一下），不是断层
- 对白上限 0.68s，不要用旁白的长停顿

## 输出（只输出 JSON，不要解释，不要代码块）

{"items":[{"sid":"c1_0002",
  "pause":[{"bid":"c1_0002#1","tier":"mid","why":"强势角色平静叙述，句中断在从句边界，克制不留白"}],
  "stress":[{"tok":3,"level":2,"why":"否定词"}],
  "rate":null},
 ...]}

`why` 必须写**这一处的具体处境**（谁在压谁、这句话要什么效果），
不要写「从句边界」「一般短语间」这种语法标签 —— 那种理由等于没判。

每个 sid 必须出现一次；没有槽位就 `"pause":[]`。

## 待标注
"""


def load():
    plan = [json.loads(l) for l in open(PLAN, encoding="utf-8")]
    habit = {}
    if os.path.exists(HABIT):
        habit = (json.load(open(HABIT, encoding="utf-8")) or {}).get("roles") or {}
    return plan, habit


def role_profiles(plan, habit):
    """角色画像：情绪分布（数据）+ 实测停顿倾向（样本不足如实标）"""
    dist = collections.defaultdict(collections.Counter)
    for r in plan:
        dist[r["who"]][r["emo"]] += 1
    out = {}
    for who, c in dist.items():
        n = sum(c.values())
        top = c.most_common()
        parts = ["%s %d/%d（%.0f%%）" % (e, k, n, 100.0 * k / n) for e, k in top]
        h = habit.get(who) or {}
        if h.get("n_pause") and h["n_pause"] >= 8 and h.get("med") is not None:
            # 实测中位只能给「基线」，不能给「性格」—— 因为现有音频几乎没有真停顿
            base = ("实测停顿中位 %.2fs（%d 处，但现有音频几乎没有真停顿，"
                    "这个数只能当下限，不能当性格依据）" % (h["med"], h["n_pause"]))
            lab = "insufficient"
        else:
            base = "实测停顿样本 %d 处，不足以刻画习惯" % (h.get("n_pause") or 0)
            lab = "insufficient"
        out[who] = dict(
            n=n, emo_mix=dict(c), summary="；".join(parts),
            pause_base=base, habit_confidence=lab,
        )
    return out


def scene_tension(plan, win=3):
    """场景紧张度：**章内相对分位**，0~1。

    ★ 第一版用绝对占比（相邻 ±2 句里紧张类情绪的比例），结果 179/239（75%）
      都落进「高 ≥0.6」—— 整部戏本来就偏激烈，绝对值没有区分度。
      改用章内分位：同一个人的不同场景之间比，才回答得了「这一场比平常更紧吗」。
    """
    # 章 = id 前缀（c1/c2/c3）
    def chap(sid):
        return sid.split("_")[0]

    raw = {}
    for i, r in enumerate(plan):
        lo, hi = max(0, i - win), min(len(plan), i + win + 1)
        seg = plan[lo:hi]
        t = sum(1 for x in seg if x["emo"] in TENSE)
        raw[r["id"]] = t / max(1, len(seg))

    by_chap = collections.defaultdict(list)
    for r in plan:
        by_chap[chap(r["id"])].append(raw[r["id"]])

    out = {}
    for cid, vals in by_chap.items():
        vs = sorted(vals)
        n = len(vs)
        for r in plan:
            if chap(r["id"]) != cid:
                continue
            v = raw[r["id"]]
            # 秩 → 0~1 分位（同值取中位秩，避免并列全压到一头）
            lo = sum(1 for x in vs if x < v)
            eq = sum(1 for x in vs if x == v)
            out[r["id"]] = round((lo + eq / 2.0) / max(1, n), 2)
    return out


def tokens_of(text):
    # 单一实现：与 annotate_prosody / pause_ann2llm 同源，绝不自建切词
    from mt_pause_rules import parse_text
    return parse_text(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    plan, habit = load()
    prof = role_profiles(plan, habit)
    tense = scene_tension(plan)

    print("=== 角色画像（依据：全部台词的情绪分布）===")
    for who, p in sorted(prof.items(), key=lambda kv: -kv[1]["n"]):
        print("  %-8s n=%-3d %s" % (who, p["n"], p["summary"]))
        print("           %s" % p["pause_base"])
    print()
    print("=== 场景紧张度分布 ===")
    c = collections.Counter()
    for v in tense.values():
        c["高 ≥0.6" if v >= 0.6 else ("中 0.3~0.6" if v >= 0.3 else "低 <0.3")] += 1
    print(" ", dict(c))

    items = []
    for r in plan:
        text = (r.get("text") or "").strip()
        if not text:
            continue
        toks = tokens_of(text)
        slots = []
        for i, (w, p) in enumerate(toks):
            if not p:
                continue
            if p in ".?!" and i == len(toks) - 1:
                continue
            slots.append(dict(bid="%s#%d" % (r["id"], len(slots) + 1), tok=i, punct=p,
                              left=" ".join(x[0] for x in toks[max(0, i - 6):i + 1]),
                              right=" ".join(x[0] for x in toks[i + 1:i + 7])))
        if not slots:
            continue
        items.append(dict(
            sid=r["id"], who=r["who"], voice=r.get("voice") or "",
            emo=r["emo"], scene=tense[r["id"]],
            role=prof.get(r["who"]) or {},
            text=text,
            tokens=[w for w, _ in toks], puncts=[p for _, p in toks],
            slots=slots,
        ))

    if a.limit:
        items = items[:a.limit]
    print()
    print("有槽位的对白 %d 条，槽位 %d 处" % (len(items), sum(len(x["slots"]) for x in items)))
    if a.dry:
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    for i in range(0, len(items), a.batch):
        seg = items[i:i + a.batch]
        fn = os.path.join(OUT_DIR, "batch_%04d.json" % (i // a.batch + 1))
        json.dump(dict(batch=i // a.batch + 1, prompt=PROMPT, mode="tier_ctx",
                       items=seg), open(fn, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print("写出 %d 个任务包 -> %s" % ((len(items) + a.batch - 1) // a.batch, OUT_DIR))


if __name__ == "__main__":
    main()
