# -*- coding: utf-8 -*-
"""_pause_ctx_narr.py —— 情境化停顿标注任务包（**旁白专用**）

用户 2026-11-15 01:3x：「下一步三个选项…你自己跑完这三个选项吧」
选项 1 = 旁白 716 条停顿标注（唯一剩下的链路空白）。

与对白版的差别（不是把对白 prompt 改几个字）：

| 维度 | 对白 `_pause_ctx.py` | 旁白（本脚本） |
|---|---|---|
| 档位尺度 | drop/tight/clause/beat = 0/0.20/0.49/0.68 | inner/bound/clause = **0.51/1.135/1.695**（`ann_spec.KIND_SEC["narr"]`） |
| 情境输入 | emo + scene + role（人物性格） | tone(narr_why) + scene + rate + 段落位置（**没有人物性格**） |
| 判定主线 | 谁在压谁 / 性格×情绪 | 叙事节奏：描写/动作/悬疑/回忆，句内层次 |
| 输出 | pause + stress + rate | **只判 pause**（rate 早已定稿在 `_narr_rate_plan_castle.json`，stress 未接线） |

★ 为什么必须单独建包：`annotate_prosody.py merge` 按 `ann_spec` 分轨，
  对白档位（0.20/0.49/0.68）套到旁白上会把 1.135 的 bound 切到 0.49，
  实测过「旁白被整体切短 2~3 倍且不报错」。所以这里 tier 只允许 short/mid/long，
  且包内显式写 `track: "narr"`（`_ann_check_one.check_one` 会按它选自检词表）。

用法：
  G:/Python310/python.exe _pause_ctx_narr.py --dry
  G:/Python310/python.exe _pause_ctx_narr.py --batch 25
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
DLG = "G:/_setup/_dlg_plan_v2.jsonl"
OUT_DIR = "G:/_setup/_ann/tasks_narr_ctx"

TENSE = {"激动反抗", "紧张", "警惕"}

PROMPT = """你是《The Castle of the King》有声书的**旁白导演**。这一批全是叙述文字（不是台词）。

你的任务不是套规则，而是**按这段叙述在故事里的作用**决定每处标点停多久。

## 你会看到每条旁白的这些信息

- `tone`：这段的叙事基调，来自既有标定 ——
  `neutral` 平叙 / `memory` 回忆·回想 / `motion` 动作·移动 / `dread` 悬疑·不祥 /
  `confront` 对峙 / `staccato` 短促断续（可叠加倍数，如 `dread×2` 表示基调更重）
- `rate`：这条的既定语速（0.76~0.83，1.0 为原速）。**不要改它**，但要顺着它判停顿：
  语速慢的句子停顿可以更从容，语速快的句子句内要更紧
- `scene`：场景紧张度 0~1，**章内相对分位**（这一段前后 ±3 条里，台词属于
  「激动反抗/紧张/警惕」的比例在整章里的位置）。`near` 会列出邻近台词的角色与情绪
- `para_pos`：这段在段落里的位置（first / mid / last）与段落长度
- `prev` / `next`：紧邻的前后文（可能是台词）
- `slots`：要你判的每一处标点（`left` 标点左侧 6 词，`right` 右侧 6 词；`right` 为空 = 句末，不判）

## 三档（只输出档位，秒数由下游换算；旁白尺度比对白长得多）

| tier | 语义 | 秒 |
|---|---|---|
| `short` | 意群内部的小顿：并列项之间、短状语之后、长句需要换气处 | 0.51 |
| `mid` | 分句之间、从句与主句之间、插入语两侧、一个意思说完话没完 | 1.135 |
| `long` | 场景切换、悬念悬停、情绪落点、破折号/省略号处、把读者按住的地方 | 1.695 |

## 怎么判

**先定这一段的呼吸，再定每一处：**

1. **基调定基调**（看 `tone`）
   - `motion`：动作在推进，全段往短压，句内多用 `short`，只在动作落点给 `mid`
   - `dread`：悬疑，句子要**按住**——句内反而压短、贴着走，落点（`long`）留给不祥的那一下
   - `memory`：回忆，整体抬一档，`mid` 为主，回忆结束/回到现在处用 `long`
   - `confront`：对峙，短促，`short` 与 `mid` 交替，不要把气口拉平
   - `neutral`：平叙，按句子结构给层次，`mid` 是常态但**不能整段都是 mid**
   - `staccato`：短促断续，句内几乎都用 `short`

2. **场景紧**（`scene` ≥0.6 或 `near` 里全是紧张台词）
   叙述者也在被推着走：句内压短，但**段落收尾**要停住（`long`），把镜头交出去。

3. **句内必须有层次**（最容易做错的地方）
   - 一处 `long` 后面紧跟 `mid` 是正常的；**整句三处以上同档**基本就是没判
   - 并列列举（`A, B, and C`）：前几项 `short`，最后一项之前给 `mid`
   - 插入语（`, he said,` / `, as if,`）两侧用 `short`，不要用 `mid`（会把句子劈断）
   - 同位语、称呼、时间状语后：`short`

4. **段落位置**
   - `first`：这一段起头，前面的标点通常要 `mid`（承接上一段的余味）
   - `last`：段末的句内标点可以 `long`，给下一段留白
   - 段落很长时（>5 条），中间不要连续 `long`，会拖垮

## 硬边界（不能破）

- **旁白没有 `zero` 档**。最轻就是 `short`。
- 句末（`right` 为空）不在槽位里，不用判。
- 破折号、省略号、分号 → `long`（这是作者留的空白）
- 不要按标点类型一刀切：同样一个逗号，在列举里是 `short`，在悬念落点可以是 `long`。
- 全书旁白是**同一个朗读者**（`narr_mc_1`），不要编造人物性格差异。

## 输出（只输出 JSON，不要解释、不要代码块、不要多余文字）

{"items":[{"sid":"c1_0001",
  "pause":[{"bid":"c1_0001#1","tier":"short","why":"列举里第一项，一口气带过"},
           {"bid":"c1_0001#2","tier":"mid","why":"转折落在搬家这件事上，停一下再交代新房子"}],
  "stress":[], "rate":null},
 ...]}

- 每个 sid 必须出现一次；没有槽位就 `"pause":[]`
- `stress` 一律空数组，`rate` 一律 null（本层只判停顿）
- `why` 必须写**这一处在这个故事里的作用**（在交代什么、给读者留什么、镜头在哪），
  不许写「从句边界」「一般短语间」这类语法标签 —— 那种理由等于没判

## 待标注
"""


def load():
    plan = [json.loads(l) for l in open(PLAN, encoding="utf-8")]
    # 只取有音频的旁白
    out = []
    for r in plan:
        if r.get("dialog"):
            continue
        wav = "G:/_setup/_audio_ch123/out/%s.wav" % r["id"]
        if not os.path.exists(wav):
            continue
        out.append(r)
    return out


def dlg_index():
    """邻近台词的情绪，用来给旁白场景定紧张度。"""
    idx = {}
    for ln in open(DLG, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        idx[r["id"]] = (r.get("who") or "", r.get("emo") or "")
    return idx


TONE_W = {"dread": 1.0, "confront": 0.9, "motion": 0.6, "memory": 0.25, "neutral": 0.0}


def _tone_int(tone):
    """narr_why → 0~1 强度。`dread×2` 记 2 倍（封顶 1.4 再归一）。"""
    if not tone:
        return 0.0
    head = tone.split(",")[0].strip()
    base, mult = head, 1.0
    if "×" in head:
        base, _, m = head.partition("×")
        try:
            mult = float(m)
        except ValueError:
            mult = 1.0
    v = TONE_W.get(base, 0.0) * mult
    if "staccato" in tone:
        v += 0.15
    return min(1.4, v) / 1.4


def scene_tension(narr, didx, win=3):
    """场景紧张度（章内相对分位）。

    ★ 第一版只数「邻近紧张台词占比」→ 旁白附近常常根本没有台词，
      480/499 挤在「中」档、0 条「低」档，等于没分档（和对白第一版同样的坑）。
      改成三路加权连续分：
        0.55 邻近台词紧张度（距离加权）
      + 0.35 邻近旁白基调强度（dread/confront/motion/memory）
      + 0.10 邻近台词密度（戏在不在打）
      再按章取秩。
    """
    def chap(sid):
        return sid.split("_")[0]

    raw, near = {}, {}
    for i, r in enumerate(narr):
        lo, hi = max(0, i - win), min(len(narr), i + win + 1)
        tsum = tw = 0.0
        dsum = dw = 0.0
        names = []
        for j in range(lo, hi):
            if j == i:
                continue
            w = 1.0 / (1 + abs(j - i))
            x = narr[j]
            e = didx.get(x["id"])
            if e:
                t = 1.0 if e[1] in TENSE else 0.0
                tsum += w * t
                dw += w
                if t:
                    names.append("%s/%s" % e)
            dsum += w * _tone_int(x.get("narr_why"))
            tw += w
        tense_ratio = tsum / max(1e-6, tw) if tw else 0.0
        tone_near = dsum / max(1e-6, tw)
        dlg_dens = dw / max(1e-6, tw)
        raw[r["id"]] = 0.55 * tense_ratio + 0.35 * tone_near + 0.10 * dlg_dens
        near[r["id"]] = names[:4]

    by_chap = collections.defaultdict(list)
    for r in narr:
        by_chap[chap(r["id"])].append(raw[r["id"]])
    out = {}
    for cid, vals in by_chap.items():
        vs = sorted(vals)
        n = len(vs)
        for r in narr:
            if chap(r["id"]) != cid:
                continue
            v = raw[r["id"]]
            lo = sum(1 for x in vs if x < v)
            eq = sum(1 for x in vs if x == v)
            out[r["id"]] = round((lo + eq / 2.0) / max(1, n), 2)
    return out, near


def tokens_of(text):
    from mt_pause_rules import parse_text
    return parse_text(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--skip-dirs", nargs="*", default=[],
                    help="已经标过的任务包目录：这些目录里出现过的 sid 不再打包")
    a = ap.parse_args()

    narr = load()
    didx = dlg_index()
    tense, near = scene_tension(narr, didx)

    # 段落位置
    para_n = collections.Counter((r["chapter"], r["para"]) for r in narr)
    seen = collections.Counter()

    items, no_slot = [], 0
    for i, r in enumerate(narr):
        text = (r.get("text") or "").strip()
        if not text:
            continue
        toks = tokens_of(text)
        slots = []
        for k, (w, p) in enumerate(toks):
            if not p:
                continue
            if p in ".?!" and k == len(toks) - 1:
                continue
            slots.append(dict(bid="%s#%d" % (r["id"], len(slots) + 1), tok=k, punct=p,
                              left=" ".join(x[0] for x in toks[max(0, k - 6):k + 1]),
                              right=" ".join(x[0] for x in toks[k + 1:k + 7])))
        key = (r["chapter"], r["para"])
        n_para = para_n[key]
        pos_i = seen[key]
        seen[key] += 1
        para_pos = "first" if pos_i == 0 else ("last" if pos_i == n_para - 1 else "mid")
        if not slots:
            no_slot += 1
            continue
        items.append(dict(
            sid=r["id"], who="narrator", voice=r.get("voice") or "narr_mc_1",
            tone=r.get("narr_why") or "neutral",
            rate=r.get("rate"),
            scene=tense[r["id"]],
            near=near[r["id"]],
            para_pos=para_pos, para_len=n_para,
            prev=(narr[i - 1]["text"][:160] if i > 0 else ""),
            next=(narr[i + 1]["text"][:160] if i + 1 < len(narr) else ""),
            text=text,
            tokens=[w for w, _ in toks], puncts=[p for _, p in toks],
            slots=slots,
        ))

    if a.skip_dirs:
        import glob as _g
        done = set()
        for d in a.skip_dirs:
            for f in _g.glob(os.path.join(d, "batch_*.json")):
                try:
                    for it in json.load(open(f, encoding="utf-8"))["items"]:
                        done.add(it["sid"])
                except Exception:  # noqa: BLE001
                    pass
        before = len(items)
        items = [x for x in items if x["sid"] not in done]
        print("  跳过已标注 %d 条，剩 %d 条" % (before - len(items), len(items)))

    if a.limit:
        items = items[:a.limit]

    print("旁白有音频 %d 条；有槽位 %d 条，无槽位跳过 %d 条；槽位 %d 处"
          % (len(narr), len(items), no_slot, sum(len(x["slots"]) for x in items)))
    c = collections.Counter()
    for x in items:
        c["高 ≥0.6" if x["scene"] >= 0.6 else ("中 0.3~0.6" if x["scene"] >= 0.3 else "低 <0.3")] += 1
    print("  场景分档", dict(c))
    print("  基调分布", dict(collections.Counter(x["tone"].split(",")[0] for x in items)))
    if a.dry:
        return

    out_dir = a.out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    n_b = 0
    for i in range(0, len(items), a.batch):
        seg = items[i:i + a.batch]
        n_b += 1
        fn = os.path.join(out_dir, "batch_%04d.json" % n_b)
        json.dump(dict(batch=n_b, track="narr", mode="tier_narr_ctx", prompt=PROMPT,
                       items=seg), open(fn, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print("写出 %d 个任务包 -> %s" % (n_b, out_dir))


if __name__ == "__main__":
    main()
