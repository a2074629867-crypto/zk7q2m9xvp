# -*- coding: utf-8 -*-
"""annotate_prosody.py —— LLM 韵律标注层（REQUIREMENTS 第 32 条）。

三张表：停顿 pause / 重读 stress / 慢读 rate。
判定依据是**情节与作者意图**，不是词表正则。

为什么单独成层：
  `mk_pause_ctx.py` 只给旁白建了上下文（第一行 `if speaker != narrator: continue`），
  对白 239 条从来没进过这一层；重读与慢读则完全没有产物。
  全量 1085 处停顿 100% 走 `src=tier` 标点兜底 —— 那不是 LLM 判定。

两阶段：
  build  从 plan 生成标注任务包（含前后文、角色、段落、token 下标、标点槽位）
  merge  合并 N 路子 Agent 结果 → 投票 → 仲裁标记 → 输出标注 jsonl（bid 格式）

用法：
  # 1) 生成任务包（默认按 batch=15 切，只取有标点的句）
  G:/Python310/python.exe annotate_prosody.py build --out-dir _ann/tasks --batch 15
  G:/Python310/python.exe annotate_prosody.py build --out-dir _ann/tasks --batch 10 --limit 10 --only dialog

  # 2) 合并三路结果（子 Agent 各自把结果写成 _ann/out/<model>/*.json）
  #    三路固定 hy4 / ds / hy3（2026-11-15 起 glm 换 hy3；旧 glm 目录可保留但不参与投票）
  G:/Python310/python.exe annotate_prosody.py merge \
      --dirs _ann/out/hy4 _ann/out/ds _ann/out/hy3 --out-dir _ann/merged

产物：
  _ann/tasks/batch_0001.json      任务包（喂给子 Agent）
  _ann/tasks/INDEX.json           批次清单
  _ann/merged/pause_ann.jsonl     bid 格式，可直接喂 pause_ann2llm.py
  _ann/merged/stress_ann.jsonl    sid + token 下标
  _ann/merged/rate_ann.jsonl      sid + rate
  _ann/merged/agreement.json      一致率与分歧统计
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mt_pause_rules import parse_text
from ann_spec import (KIND_SEC, TIER2KIND, prompt_for, track_of_speaker,
                      kind_of_tier, sec_of_kind, coerce_kind, nearest_kind)

PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"

# 情节类别 → 慢读倾向（只作为给 LLM 的提示，不代替判定）
RATE_HINT = {
    "grief": "悲伤/告别/死亡/临终 → 慢，rate ≤0.80",
    "shame": "羞辱/被拒绝/屈辱 → 慢，rate ≤0.80",
    "memory": "回忆/往事/时间跨度 → 略慢，0.78~0.82",
    "conflict": "抢话/对抗/争吵 → 语速不动，靠停顿表达",
    "neutral": "平叙 → 0.80 基准，不特意放慢",
}


def tokens_of(text):
    """[(word, punct)] —— 与 pause_ann2llm 的 punct_slots 同源，绝不自建切词。"""
    return parse_text(text)


def build_tasks(rows, batch_size, limit=None, only=None):
    """把 plan 行切成标注任务。只保留有句内标点的句子（无标点则无停顿可标）。"""
    items = []
    for r in rows:
        who = r.get("speaker") or r.get("who") or ""
        if only == "dialog" and who == "narrator":
            continue
        if only == "narr" and who != "narrator":
            continue
        text = (r.get("text") or "").strip()
        if not text:
            continue
        toks = tokens_of(text)
        # 句内标点槽位（bid 从 1 起，与 pause_ann2llm 一致）
        slots = []
        for i, (w, p) in enumerate(toks):
            if p:
                # 句末标点且后面没有词 → 不是句内边界
                if p in ".?!" and i == len(toks) - 1:
                    continue
                slots.append({
                    "bid": "%s#%d" % (r["id"], len(slots) + 1),
                    "tok": i,
                    "punct": p,
                    "left": " ".join(x[0] for x in toks[max(0, i - 6):i + 1]),
                    "right": " ".join(x[0] for x in toks[i + 1:i + 7]),
                })
        items.append({
            "sid": r["id"],
            "who": who,
            "track": track_of_speaker(who),
            "voice": r.get("voice") or "",
            "chapter": r.get("chapter"),
            "para": r.get("para"),
            "text": text,
            "tokens": [w for w, _ in toks],
            "puncts": [p for _, p in toks],
            "slots": slots,
        })
    if limit:
        items = items[:limit]

    # 补前后文（同一 para 内的相邻句）
    by_para = {}
    for it in items:
        by_para.setdefault((it["chapter"], it["para"]), []).append(it)
    for key, group in by_para.items():
        for i, it in enumerate(group):
            it["prev"] = group[i - 1]["text"] if i > 0 else ""
            it["next"] = group[i + 1]["text"] if i + 1 < len(group) else ""
            it["para_n"] = len(group)

    # ★ 两轨必须分开成批：提示词与档位词表不同（REQUIREMENTS 32.1b），
    #   混在一批里模型会把旁白的 inner/bound/clause 和对白的 drop/tight/beat 用错。
    batches = []
    for trk in ("narr", "dlg"):
        sub = [it for it in items if it["track"] == trk]
        batches += [sub[i:i + batch_size] for i in range(0, len(sub), batch_size)]
    return batches


# ⚠️ 下面两段提示词与 TIER_SEC 已被 ann_spec.py 取代（2026-11-12），仅供回溯对比。
#   它们只有**一套** 0/0.25/0.45/0.68 的对白尺度，套到旁白上是错的（REQUIREMENTS 32.1b）。
#   实际生成走 ann_spec.prompt_for(track, tier_mode)。不要改回这里。
PROMPT = """你是《The Castle of the King》有声书的中文韵律标注员。

任务：给下面每一条台词/旁白标注三件事。判定依据是**情节与作者意图**，不是词表。

## 一、停顿（pause）
对 `slots` 里每一处给绝对秒数 `d`，并写 `kind` 与 `why`。
- kind 只能取：inner（句中短语间）/ bound（从句或并列边界）/ clause（完整句后接新句）
- 优先级（用户定的口径）：
  1. 对抗 / 抢话 / 激动 → 短，0.15~0.35
  2. 情绪落点 / 信息揭示 / 把话压给对方 → 长，0.45~0.65
  3. 纯填充词（Well / Look / then / Oh）→ 0
  4. 从句未完（后接 that/which/when/and then）→ 0.20~0.25
- **同一句里每个停顿不一样长**，不许套同一常数。
- 逗号不是都要停：`ago, either` 这种连读中间不许留停顿 → d=0。
- 停顿处不许是数字零以外的「无意义小值」，0 必须是真的连读。

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
  "pause":[{"bid":"c1_0001#1","d":0.7,"kind":"bound","why":"完整状语后接主句"}],
  "stress":[{"tok":3,"level":2,"why":"时间对比"}],
  "rate":{"rate":0.78,"why":"祖母去世，回忆段落"}},
 ...]}
每个 sid 必须出现一次；没有停顿就 `"pause":[]`；不需要慢读就 `"rate":null`。

## 待标注
"""


PROMPT_TIER = """你是《The Castle of the King》有声书的中文韵律标注员（**档位模式**）。

任务：给下面每一条台词/旁白标注三件事。判定依据是**情节与作者意图**，不是词表。

## 一、停顿（pause）—— 只给档位，不给秒数
对 `slots` 里每一处给一个 `tier`，并写 `why`。tier 只能取这四个值：
- `zero`  连读，不停（`ago, either` 这种）
- `short` 0.15~0.35s —— 对抗 / 抢话 / 激动 / 从句未完
- `mid`   0.35~0.55s —— 一般短语间
- `long`  0.55~0.80s —— 情绪落点 / 信息揭示 / 把话压给对方

规则：
- **同一句里相邻停顿不许同档**（全 long 或全 short 都是错的）
- 逗号不是都要停：连读处给 `zero`
- 纯填充词（Well / Look / then / Oh）给 `zero`
- 从句未完（后接 that/which/when/and then）给 `short`

## 二、重读（stress）
挑出必须重读的词，给 `tok`（0 起，对应 `tokens` 下标）、`level`（1=轻 2=中 3=重）、`why`。
优先：重点副词（only / never / even / just / still / already）、否定（not / no / nothing / never）、
数字与时间、专有名词、对比项、情绪落点词。一句最多 3 个，虚词代词连词不标。

## 三、慢读（rate）
判断这一句要不要放慢，给 `rate`（0.72~0.84，基准 0.80）与 `why`。
- 悲伤 / 告别 / 死亡 / 临终 / 羞辱 / 被拒绝 / 回忆 → 0.72~0.79
- 抢话 / 对抗 / 争吵 / 惊叫 → 0.80（不动）
- 平叙 → 0.80
- 不需要放慢就返回 null，不要硬凑。

## 输出格式（只输出 JSON，不要解释，不要 markdown 代码块）
{"items":[{"sid":"c1_0001",
  "pause":[{"bid":"c1_0001#1","tier":"mid","why":"完整状语后接主句"}],
  "stress":[{"tok":3,"level":2,"why":"时间对比"}],
  "rate":{"rate":0.78,"why":"祖母去世，回忆段落"}},
 ...]}
每个 sid 必须出现一次；没有停顿就 `"pause":[]`；不需要慢读就 `"rate":null`。

## 待标注
"""

TIER_SEC = {"zero": 0.0, "short": 0.25, "mid": 0.45, "long": 0.68}


def cmd_build(a):
    rows = [json.loads(l) for l in open(a.plan, encoding="utf-8") if l.strip()]
    rows.sort(key=lambda r: r.get("idx", 0))
    batches = build_tasks(rows, a.batch, a.limit, a.only)
    os.makedirs(a.out_dir, exist_ok=True)
    index = []
    for i, b in enumerate(batches, 1):
        name = "batch_%04d.json" % i
        p = os.path.join(a.out_dir, name)
        trk = b[0]["track"]
        payload = {"batch": i, "track": trk,
                   "prompt": prompt_for(trk, a.tier_mode),
                   "mode": "tier" if a.tier_mode else "sec", "items": b}
        json.dump(payload, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        index.append({
            "file": name, "n": len(b), "track": trk,
            "sids": [x["sid"] for x in b],
            "slots": sum(len(x["slots"]) for x in b),
        })
        print("%-16s [%s] %2d 句  %3d 停顿槽位  %s … %s"
              % (name, trk, len(b), sum(len(x["slots"]) for x in b),
                 b[0]["sid"], b[-1]["sid"]))
    json.dump(index, open(os.path.join(a.out_dir, "INDEX.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    tot_slots = sum(x["slots"] for x in index)
    print("\n共 %d 批 / %d 句 / %d 停顿槽位 → %s"
          % (len(index), sum(x["n"] for x in index), tot_slots, a.out_dir))


def _load(dirs):
    """读多路子 Agent 结果。每路返回 {sid: {...}}。"""
    runs = {}
    for d in dirs:
        got = {}
        for fp in sorted(glob.glob(os.path.join(d, "*.json"))):
            try:
                obj = json.load(open(fp, encoding="utf-8"))
            except Exception as e:
                print("  ! %s 解析失败 %s" % (fp, e))
                continue
            items = obj.get("items") if isinstance(obj, dict) else obj
            if not isinstance(items, list):
                continue
            for it in items:
                sid = it.get("sid")
                if sid:
                    got[sid] = it
        runs[os.path.basename(d.rstrip("/\\"))] = got
        print("读 %-16s %d 句" % (os.path.basename(d.rstrip("/\\")), len(got)))
    return runs


def _tier(v, tol):
    """连续值 → 离散档。用档位投票，不用原始数值投票。

    为什么：三路给 0.28 / 0.45 / 0.55 时，若按 0.02 容差判，永远分歧；
    但 0.45 与 0.55 只差一个档边，语义上是一致的。连续值投票是尺子选错了。
    """
    if v is None:
        return None
    return int(round(float(v) / tol))


def _vote(vals, tol=None):
    """三票投票。返回 (值, 状态)。状态：unanimous / split / disputed。

    tol 给定时走「先分档、再取档内中位」；不给则按原值严格比。
    """
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, "empty"
    if len(set(vals)) == 1:
        return vals[0], "unanimous"

    if all(isinstance(v, (int, float)) for v in vals) and tol:
        # 先看极差：整组落在 tol 内直接算一致（窄区间指标如 rate 只有 0.12 宽，
        # 分档会只剩 2 档，反而把 0.76/0.78 这种真一致判成分歧）
        if max(vals) - min(vals) <= tol:
            return round(sum(vals) / len(vals), 3), "unanimous"
        tiers = [_tier(v, tol) for v in vals]
        from collections import Counter
        c = Counter(tiers)
        top, n = c.most_common(1)[0]
        if n == len(vals):
            return round(sum(vals) / len(vals), 3), "unanimous"
        if n >= 2:
            # 取同一档内的中位，避免把两端的极端值揉进去
            same = sorted(v for v, t in zip(vals, tiers) if t == top)
            return round(same[len(same) // 2], 3), "split"
        return round(sorted(vals)[len(vals) // 2], 3), "disputed"

    if all(isinstance(v, (int, float)) for v in vals):
        s = sorted(vals)
        if s[-1] - s[0] <= 0.02:
            return round(sum(vals) / len(vals), 3), "unanimous"
        return round(s[len(s) // 2], 3), "disputed"

    from collections import Counter
    c = Counter(vals)
    top, n = c.most_common(1)[0]
    if n >= 2:
        return top, "split"
    return top, "disputed"


def cmd_merge(a):
    runs = _load(a.dirs)
    names = list(runs)
    # sid → 轨道：秒数要按轨道取（旁白 0.51/1.135/1.695，对白 0/0.20/0.49/0.68）
    spk = {}
    for ln in open(a.texts, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            r = json.loads(ln)
            spk[r["id"]] = r.get("speaker") or ""
    if len(names) < 2:
        print("至少需要 2 路结果才能投票（现在 %d 路）" % len(names))
        return 1
    all_sids = sorted(set().union(*[set(r) for r in runs.values()]))
    os.makedirs(a.out_dir, exist_ok=True)

    pause_out, stress_out, rate_out = [], [], []
    bad_tier = []
    agree = {"pause": {"unanimous": 0, "split": 0, "disputed": 0, "empty": 0},
             "stress": {"unanimous": 0, "split": 0, "disputed": 0, "empty": 0},
             "rate": {"unanimous": 0, "split": 0, "disputed": 0, "empty": 0}}
    disputed = []

    for sid in all_sids:
        per = [runs[n].get(sid) for n in names]
        trk = track_of_speaker(spk.get(sid, ""))
        # ---- 停顿：按 bid 聚合 ----
        by_bid = {}
        for it in per:
            if not it:
                continue
            for p in (it.get("pause") or []):
                bid = p.get("bid")
                if bid:
                    by_bid.setdefault(bid, []).append(p)
        for bid, ps in sorted(by_bid.items()):
            raw = [p.get("tier") if p.get("tier") else p.get("d") for p in ps]
            if raw and isinstance(raw[0], str):
                # 档位模式：先投离散档，再按轨道查秒数（绝不用单一尺度）
                t, st = _vote([str(x).strip().lower() for x in raw if x])
                kind = kind_of_tier(trk, t)
                d = sec_of_kind(trk, kind) if kind else None
                if t and d is None:
                    # 模型给了本轨道没有的档（如旁白给 zero/drop）：不猜，也不当停顿时长
                    bad_tier.append("%s [%s] tier=%s" % (bid, trk, t))
            else:
                d, st = _vote([v for v in raw if v is not None], tol=0.12)
                kind = None
                if d is not None:
                    ks = [p.get("kind") for p in ps if p.get("kind")]
                    kind = coerce_kind(trk, max(set(ks), key=ks.count) if ks else None, d)
            if d is None:
                agree["pause"]["empty"] += 1
                continue
            agree["pause"][st] += 1
            whys = [p.get("why") for p in ps if p.get("why")]
            pause_out.append({
                "bid": bid, "sid": sid, "track": trk, "dur": d,
                "mark": kind or "", "why": whys[0] if whys else "",
                "src": "llm_vote", "vote": st, "n": len(ps),
            })
            if st == "disputed":
                disputed.append({"type": "pause", "bid": bid,
                                 "vals": [p.get("tier") or p.get("d") for p in ps]})

        # ---- 重读：按 tok 聚合 ----
        by_tok = {}
        for it in per:
            if not it:
                continue
            for s in (it.get("stress") or []):
                t = s.get("tok")
                if isinstance(t, int):
                    by_tok.setdefault(t, []).append(s)
        for tok, ss in sorted(by_tok.items()):
            if len(ss) < 2:
                continue            # 只有一路标 → 不算共识
            lv, st = _vote([s.get("level") for s in ss], tol=1)   # level 差 1 级算一致
            agree["stress"][st] += 1
            whys = [s.get("why") for s in ss if s.get("why")]
            stress_out.append({"sid": sid, "tok": tok, "level": lv,
                               "why": whys[0] if whys else "",
                               "src": "llm_vote", "vote": st, "n": len(ss)})
            if st == "disputed":
                disputed.append({"type": "stress", "sid": sid, "tok": tok,
                                 "vals": [s.get("level") for s in ss]})

        # ---- 慢读：句级 ----
        rv = []
        for it in per:
            if not it:
                continue
            r = it.get("rate")
            rv.append(r.get("rate") if isinstance(r, dict) else None)
        rr, st = _vote(rv, tol=0.04)
        agree["rate"][st] += 1
        if rr is not None:
            # ★ 2026-11-15 17:4x：per 里可能有 None（某一路缺该 sid）。
            #   旧代码 it.get("rate") 直接取属性 → None.get 崩，导致「三路不齐就 merge 不了」。
            whys = [(it.get("rate") or {}).get("why") for it in per
                    if isinstance(it, dict) and isinstance(it.get("rate"), dict)]
            whys = [w for w in whys if w]
            rate_out.append({"sid": sid, "rate": rr,
                             "why": whys[0] if whys else "",
                             "src": "llm_vote", "vote": st,
                             "n": sum(1 for v in rv if v is not None)})
            if st == "disputed":
                disputed.append({"type": "rate", "sid": sid, "vals": rv})

    def dump(name, rows):
        p = os.path.join(a.out_dir, name)
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("写出 %-26s %d 条" % (name, len(rows)))

    dump("pause_ann.jsonl", pause_out)
    dump("stress_ann.jsonl", stress_out)
    dump("rate_ann.jsonl", rate_out)
    json.dump({"models": names, "agreement": agree, "disputed": disputed[:200],
               "n_disputed": len(disputed)},
              open(os.path.join(a.out_dir, "agreement.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\n=== 一致率 ===")
    print("  %-7s %5s %5s %5s | %8s %10s"
          % ("维度", "三票", "两票", "分歧", "三票一致率", "至少两票率"))
    for k, v in agree.items():
        tot = sum(v.values()) - v["empty"]
        if tot:
            print("  %-7s %5d %5d %5d | %8.1f%% %9.1f%%"
                  % (k, v["unanimous"], v["split"], v["disputed"],
                     100.0 * v["unanimous"] / tot,
                     100.0 * (v["unanimous"] + v["split"]) / tot))
        else:
            print("  %-7s 无有效标注" % k)
    print("  ⇒ 验收看「至少两票率」（两票即可采纳），不看「三票全同率」")
    print("  分歧条目 %d（已标 _disputed，不取平均）" % len(disputed))

    # 分轨自检：秒数必须落在本轨道档位上，出现中间值就是尺度又混了
    by_trk = {}
    for r in pause_out:
        by_trk.setdefault(r["track"], []).append(r["dur"])
    for trk, ds in sorted(by_trk.items()):
        c = {}
        for x in ds:
            c[x] = c.get(x, 0) + 1
        shot = ", ".join("%s×%d" % (k, v) for k, v in sorted(c.items()))
        print("  [%s] 停顿 %d 处  %s" % (trk, len(ds), shot))
    if bad_tier:
        print("  ⚠ 越轨档位 %d 处（已丢，不计入分母）：%s"
              % (len(bad_tier), "; ".join(bad_tier[:5])))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out-dir", default="_ann/tasks")
    b.add_argument("--plan", default=PLAN, help="默认全库 plan；补标小批时传子集 plan")
    b.add_argument("--batch", type=int, default=15)
    b.add_argument("--limit", type=int, default=0)
    b.add_argument("--only", choices=["narr", "dialog"], default=None)
    b.add_argument("--tier-mode", action="store_true", help="只给档位不给秒数（提高一致率）")
    b.set_defaults(func=cmd_build)

    m = sub.add_parser("merge")
    m.add_argument("--dirs", nargs="+", required=True)
    m.add_argument("--out-dir", default="_ann/merged")
    m.add_argument("--texts", default=PLAN, help="plan jsonl，用来查 sid → speaker/轨道")
    m.set_defaults(func=cmd_merge)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
