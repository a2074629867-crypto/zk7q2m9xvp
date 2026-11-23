# -*- coding: utf-8 -*-
"""ann_spec.py —— 韵律标注的**两套**档位常数与提示词（单一来源）。

REQUIREMENTS 32.1b：旁白与对白的档位**不可互搬**。

  旁白 kind ∈ {inner, bound, clause} = 0.51 / 1.135 / 1.695，**同档同长**，没有 drop / beat
  对白 kind ∈ {drop, tight, clause, beat} = 0 / 0.20 / 0.49 / 0.68，上限 0.76，句内可不等长

为什么单独成文件（2026-11-12）：
`annotate_prosody.py` 原先只有一套 `TIER_SEC = 0/0.25/0.45/0.68` —— 那是**对白**尺度。
而 `_pause_plan.jsonl` 的 1085 处停顿**全部属于旁白**（对白从未进过这一层）。
档位模式一把套到 716 条旁白上，bound 1.135 → 0.45，而 `mt_final_pause` 的 LLM 分支
是「比现值短就删静音」，结果是旁白被整体切短 **2~3 倍且不报错**。
"""

# 轨道 → 档位 → 秒数（唯一真来源）
KIND_SEC = {
    "narr": {"inner": 0.51, "bound": 1.135, "clause": 1.695},
    "dlg": {"drop": 0.0, "tight": 0.20, "clause": 0.49, "beat": 0.68},
}

# 档位模式的四档序数 → kind。旁白只有 3 档（没有 drop/beat），所以 zero 不出现。
TIER2KIND = {
    "narr": {"short": "inner", "mid": "bound", "long": "clause"},
    "dlg": {"zero": "drop", "short": "tight", "mid": "clause", "long": "beat"},
}

TIERS = {trk: list(m) for trk, m in TIER2KIND.items()}

DLG_CAP = 0.76          # 对白单处上限（REQUIREMENTS 32.1）


def track_of_speaker(who):
    """speaker → 轨道。旁白只有 narrator 一个。"""
    return "narr" if (who or "") == "narrator" else "dlg"


def kind_of_tier(track, tier):
    """档位 → kind。非法档返回 None（宁可丢这一处，不猜）。"""
    if not tier:
        return None
    return TIER2KIND.get(track, {}).get(str(tier).strip().lower())


def sec_of_kind(track, kind):
    return KIND_SEC.get(track, {}).get(kind)


def sec_of_tier(track, tier):
    k = kind_of_tier(track, tier)
    return None if k is None else sec_of_kind(track, k)


def nearest_kind(track, d):
    """给一个秒数反推最近 kind（秒数模式/老标注兼容用）。"""
    m = KIND_SEC.get(track) or {}
    if not m:
        return None
    try:
        d = float(d)
    except (TypeError, ValueError):
        return None
    return min(m, key=lambda k: abs(m[k] - d))


def coerce_kind(track, kind, d=None):
    """模型给的 kind 不在本轨道词表里就用秒数反推；都没有返回 None。"""
    if kind and kind in (KIND_SEC.get(track) or {}):
        return kind
    if d is not None:
        return nearest_kind(track, d)
    return None


# ---------------------------------------------------------------- 提示词

_TAIL_STRESS_RATE = """
## 二、重读（stress）
挑出必须重读的词，给 `tok`（0 起，对应 `tokens` 下标）、`level`（1=轻 2=中 3=重）、`why`。
优先：重点副词（only / never / even / just / still / already）、否定（not / no / nothing / never）、
数字与时间、专有名词、对比项（A 而不是 B）、情绪落点词。
- 一句最多标 3 个，宁少不滥。
- 虚词、代词、连词不标。

## 三、慢读（rate）
判断这一句要不要放慢，给 `rate`（0.72~0.84，基准 0.80）与 `why`。
- 悲伤 / 告别 / 死亡 / 临终 / 羞辱 / 被拒绝 / 回忆 → 放慢（0.72~0.79）
- 抢话 / 对抗 / 争吵 / 惊叫 → 不动（0.80）
- 平叙 → 0.80，不必特意放慢
- 一句里混合情绪时按**最重的那一拍**定。
- 不需要放慢就返回 null，不要硬凑。

## 输出格式（只输出 JSON，不要解释，不要 markdown 代码块）
{"items":[{"sid":"c1_0001",
  "pause":[{"bid":"c1_0001#1","tier":"mid","why":"完整状语后接主句"}],
  "stress":[{"tok":3,"level":2,"why":"时间对比"}],
  "rate":{"rate":0.78,"why":"祖母去世，回忆段落"}},
 ...]}
每个 sid 必须出现一次；没有停顿就 `"pause":[]`；不需要慢读就 `"rate":null`。
`bid` 必须原样抄任务包里 `slots[].bid`，不许自己编号。

## 待标注
"""

_HEAD = "你是《The Castle of the King》有声书的中文韵律标注员（**档位模式**）。\n\n任务：给下面每一条{what}标注三件事。判定依据是**情节与作者意图**，不是词表。\n"

_NARR_PAUSE = """
## 一、停顿（pause）—— 只给档位，不给秒数

本批全是**旁白**（叙述者朗读正文）。旁白的三档是**固定时长**的，你只负责判「属于哪一档」：

| tier | 语义 | 实际时长 |
|---|---|---|
| `short` | 短语内部断开：修饰语／插入语／并列形容词，右段**不能独立成小句** | 0.51s |
| `mid` | 分句边界：右段**能独立成小句**（自己的主谓，或承前省略主语但有自己的谓语） | 1.135s |
| `long` | 整句结束、转入新句／新段落／新场景 | 1.695s |

**判定只用一个测试：看逗号右段能不能独立成小句。** 按下面顺序逐条比对，命中第一条就停，不要往下犹瑜：

1. 标点是 `.` `.’` `?` `!` `...`（句末）→ `long`
2. 右段首词是 and / but / or / yet / for / then，且后面**有谓语动词**（主语可承前省略）→ `mid`
3. 右段首词是 when / while / if / though / although / because / till / until / since / after / before / as / unless / whether / where → `mid`
4. 右段首词是 which / who / whom / whose / that（关系从句）→ `mid`
5. 右段是**纯补充成分**（介词短语／分词短语／同位语／并列形容词），整段删掉句子仍成立 → `short`
6. 右段是说话／思考动词的插入（`, he thought,` / `, said Joseph,`）→ `short`
7. 以上都不命中 → `short`

注意：
- **判据是「右段能不能独立成小句」，不是逗号本身，也不是语感上“这里该喘口气”。** 两个模型对同一处给不同档，几乎都是没把右段当句读。
- 旁白没有「不停」这一档：每个标点都要停，最低 `short`。
- 同档同长：不要在某档里暗示「这处长一点」，选对档就行。
- 逗号处基本不给 `long`；`long` 只在句末标点，或叙述真正跳到新时间／地点／人物状态时给。

两个真实例句（照这个方式判，不要另立标准）：
- `Three months ago, his grandmother died, and then they had moved to this house.`
  - `#1` 右段 `his grandmother died` 有主谓 → `mid`
  - `#2` 右段 `and then they had moved…` = and + 主谓 → `mid`
- `Though the old man lay upstairs, after a second stroke, and lingered, giving no trouble.`
  - `#1` 右段 `after a second stroke` 是介词短语、无主谓 → `short`
  - `#2` 右段 `and lingered` = and + 谓语（主语省略）→ `mid`
  - `#3` 右段 `giving no trouble` 是分词短语 → `short`

- 引号内的台词属于人物，不归你判（本批旁白不含台词）。
"""

_DLG_PAUSE = """
## 一、停顿（pause）—— 只给档位，不给秒数

本批全是**对白**（人物台词）。对白四档：

| tier | 语义 | 实际时长 |
|---|---|---|
| `zero` | 连读，不停 | 0s |
| `short` | 抢话、对抗、急促辩解；从句未完 | 0.20s |
| `mid` | 一般短语间；一个意思说完但话没完 | 0.49s |
| `long` | 情绪落点、信息揭示、把话压给对方；一段话收尾 | 0.68s |

**判定阶梯：按顺序逐条比对，命中第一条就停，不要靠语感。**

1. **右段为空**（标点在句末／引语末尾）：
   - `next` 为空 → `long`（这人物这段话说完了，留白）
   - `next` 非空 → `mid`（话没说完，接着往下说）
   - **句末绝对不许给 `zero` 或 `short`**
2. 右段是单独成段的填充词（Well / Look / Oh / then / now）→ `zero`
3. 逗号两侧本来是一个词组被拆开（`ago, either` / 口吃重复 `not, not`）→ `zero`
4. 右段首词是 that / which / when / and then，从句还没说完 → `short`
5. 这一句处于抢话／争吵／急促辩解 → `short`
6. 以上都不命中 → `mid`

注意：
- `zero` 只给「本来就要连读」的地方：**不许把句末、情绪停顿、信息落点给成 zero**。
- **`zero` 是「不停」，不是「很短的停顿」**：一处 zero 后面紧跟 `mid` 或 `long` 是正常的（连读后停一下），不是断层。
- **阶梯只看这一处本身，不看相邻处给了什么档**：不要为了“拉开差异”而改判到别的档，也不要因为邻处是 mid 就把填充词抬成 mid。
- 对白上限 0.68s，**不要用旁白的长停顿**（旁白是 0.51~1.695s 另一套尺子）。
- 同一句里可以不同长，也可以两处同档——按阶梯判出什么就是什么。
"""

_SEC_NARR = """
## 一、停顿（pause）—— 给绝对秒数 `d` 与 `kind`
**本批全是旁白。** kind 只能取：
- `inner` = 0.51s（句中短语之间）
- `bound` = 1.135s（从句或并列边界）
- `clause` = 1.695s（完整句后接新句）
旁白**同档同长**：给了 kind 就按上表给 d，不要自创 0.7 / 1.4 这种中间值。
旁白每个标点都要停（没有「不停」这一档），旁白停顿比对白长 2~3 倍是正常的。
"""

_SEC_DLG = """
## 一、停顿（pause）—— 给绝对秒数 `d` 与 `kind`
**本批全是对白。** kind 只能取：
- `drop` = 0（连读 / 口吃中间 / 纯填充词）
- `tight` = 0.20（对抗、抢话、激动；从句未完）
- `clause` = 0.49（一般短语间）
- `beat` = 0.68（情绪落点、信息揭示、把话压给对方）
单处上限 0.76s。同一句里每个停顿可以不一样长；相邻两处不许同档。
"""

_SEC_FORMAT_TAIL = """
## 输出格式（只输出 JSON，不要解释，不要 markdown 代码块）
{"items":[{"sid":"c1_0001",
  "pause":[{"bid":"c1_0001#1","d":0.51,"kind":"inner","why":"修饰语与中心词之间"}],
  "stress":[{"tok":3,"level":2,"why":"时间对比"}],
  "rate":{"rate":0.78,"why":"祖母去世，回忆段落"}},
 ...]}
每个 sid 必须出现一次；没有停顿就 `"pause":[]`；不需要慢读就 `"rate":null`。
`bid` 必须原样抄任务包里 `slots[].bid`，不许自己编号。

## 待标注
"""


def prompt_for(track, tier_mode=True):
    """按轨道返回提示词。track ∈ {narr, dlg}。"""
    trk = "narr" if track == "narr" else "dlg"
    what = "旁白" if trk == "narr" else "台词"
    head = _HEAD.format(what=what)
    if tier_mode:
        body = _NARR_PAUSE if trk == "narr" else _DLG_PAUSE
        return head + body + _TAIL_STRESS_RATE
    body = _SEC_NARR if trk == "narr" else _SEC_DLG
    return head.replace("（**档位模式**）", "") + body + _TAIL_STRESS_RATE.replace(
        '"tier":"mid"', '"d":0.51,"kind":"inner"') + _SEC_FORMAT_TAIL


if __name__ == "__main__":
    # 自检：两套尺子必须对得上 REQUIREMENTS 32.1
    assert KIND_SEC["narr"]["bound"] == 1.135
    assert KIND_SEC["dlg"]["beat"] == 0.68
    assert sec_of_tier("narr", "mid") == 1.135
    assert sec_of_tier("dlg", "mid") == 0.49
    assert kind_of_tier("narr", "zero") is None     # 旁白没有 drop
    assert nearest_kind("narr", 0.45) == "inner"
    assert nearest_kind("dlg", 0.45) == "clause"
    assert track_of_speaker("narrator") == "narr"
    assert track_of_speaker("Joseph") == "dlg"
    p = prompt_for("narr", True)
    assert "1.695s" in p and "0.68s" not in p.split("## 二")[0]
    q = prompt_for("dlg", True)
    assert "0.68s" in q and "1.135s" not in q.split("## 二")[0]
    print("ann_spec 自检通过")
    print("  narr:", KIND_SEC["narr"])
    print("  dlg :", KIND_SEC["dlg"])
