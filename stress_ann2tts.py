# -*- coding: utf-8 -*-
"""stress_ann.jsonl → 生成端带标签文本。补上 stress 侧缺的那一跳。

对应 pause 侧的 `pause_ann2llm.py`，但性质完全不同：

    pause 是**后期插静音**（mt_final_pause 吃 pause_llm.json）
    stress 是**生成时注入**（<rate>/<pitch> 必须进 prompt，后期做不出来）

所以本脚本的产物不是给混音用的，是给 `_adv_tts.py` / 任何 `--task tts` 生成器
直接当 text 用的。

## 分派规则（10-14~10-29 实测，STRESS_PLAYBOOK.md §2.4 / §5）

| 位置 | 动作 | 理由 |
|---|---|---|
| 句中 level>=3 | `<rate, factor=0.70>` | 有降调空间，拉慢自然带出重音 |
| 句末 level>=3 | `<pitch, semitones=9>` | 句末天然降调，rate 只会拖成气声 |
| level 2 / 1 | 不打 | 实测打多了音色变、跳词 |

## 三条硬约束（违反任一条都返过工）

1. **句末绝不用 rate** —— N0627 carefully 句末加 rate 后有声音只剩 0.070s（气声）
2. **`<pitch>` 只在 `--task tts` 生效** —— edit 模板下 F0 80.9→80.9Hz 一动不动
3. **rate 与 pitch 永不叠加** —— 叠加数字漂亮但音色变（用户否决：要么 pitch 要么 rate0.7）

## 格式坑（本脚本存在的第二个理由）

`dots_markup.py` §一 写得很清楚：**模型吃的是逗号格式 `<rate, factor=1.20>`**，
`<rate factor="1.20">` 只是 doteBench 的数据契约/人写格式。
手拼 XML 直接喂模型 = 可能静默不生效，所以这里一律经 `dots_markup` 构造，
同时输出 `xml`（人读/评测）与 `model`（真正喂模型）两版。

## 为什么用原文 offset 定位，不拼 tokens+puncts

716 句里 20 句用空格拼接还原不了（原文含 `’` 弯引号，token 里被剥掉）。
按原文顺序 `find` 逐个定位 **716/716 全中**，且原文一个字符都不改。

## 用法

    # 干跑，看对齐率/注入量/位置分布
    G:/Python310/python.exe stress_ann2tts.py --dry

    # 落盘
    G:/Python310/python.exe stress_ann2tts.py --out stress_tts_narr.json

    # 只打最重的那档（更保守）
    G:/Python310/python.exe stress_ann2tts.py --min-level 2.9 --dry

## ⚠️ 何时才用这份产物

按 10-29 定的工作流（REQUIREMENTS.md「零、生成工作流」）：

    ① 每条文本 2 个 seed 无标签各生成一遍
    ② 检测（吞字/声纹/电平/F0/rel_z）→ 两 take 取最佳
    ③ 未达标 → 再生成第 3 个 seed
    ④ 三遍仍不达标 → 才用本文件的 model 文本重新生成

**不要一上来就用带标签版**：10-24 实测 N0167 coldly 在基线里本来就是全句第一，
加标签后掉到第二 —— 模型自己读对了，我们是在帮倒忙。
"""
import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dots_markup as MK          # 单一格式来源，绝不手拼标签

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ANN = os.path.join(ROOT, "_ann", "merged_v3", "stress_ann.jsonl")
DEFAULT_TASKS = os.path.join(ROOT, "_ann", "tasks_v3t")

MID_RATE = 0.70        # 句中：PLAYBOOK §2.2 唯一精确落到词的档
FINAL_PITCH = 9        # 句末：PLAYBOOK §2.3，tts 下实测 loc −2.50→+6.11
MIN_LEVEL = 2.5        # 2 票 3 + 1 票 2 = 2.667 算；1 票 3 + 2 票 2 = 2.333 不算


def to_std_xml(model_s):
    """模型格式 → 标准 XML（只供人读/评测，不进模型）。

    dots_markup.rate()/pitch() 产出的**就是**模型格式（逗号、无引号），
    反向没有现成函数，所以这里只做这两个标签的展示转换。
    """
    import re as _re
    s = _re.sub(r'<rate, factor=([0-9.]+)>', r'<rate factor="\1">', model_s)
    s = _re.sub(r'<pitch, semitones=(-?[0-9.]+)>', r'<pitch semitones="\1">', s)
    s = _re.sub(r'<pause, act="(\w+)" level="(\d+)"/>', r'<pause act="\1"/>', s)
    return s


def load_tasks(tasks_dir):
    """{sid: {"text": str, "tokens": [...]}}。只认 batch_*.json，INDEX.json 是 list。"""
    out = {}
    files = sorted(glob.glob(os.path.join(tasks_dir, "batch_*.json")))
    for fp in files:
        d = json.load(open(fp, encoding="utf-8"))
        if not isinstance(d, dict) or "items" not in d:
            continue
        for it in d["items"]:
            out[it["sid"]] = {"text": it["text"], "tokens": it["tokens"]}
    return out, len(files)


def load_ann(path):
    """{sid: [ {tok, level, why, vote, n}, ... ]}，同 sid 同 tok 去重取最高 level。"""
    by = {}
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        sid = r["sid"]
        cur = by.setdefault(sid, {})
        tok = int(r["tok"])
        lv = float(r["level"])
        if tok not in cur or lv > cur[tok]["level"]:
            cur[tok] = {"tok": tok, "level": lv, "why": r.get("why", ""),
                        "vote": r.get("vote", ""), "n": r.get("n", 0)}
    return {k: sorted(v.values(), key=lambda x: x["tok"]) for k, v in by.items()}


def locate(text, tokens):
    """token 在原文里的 [start, end) 区间。找不到返回 None（口径漂了，宁可不写）。"""
    pos, spans = 0, []
    for w in tokens:
        i = text.find(w, pos)
        if i < 0:
            return None
        spans.append((i, i + len(w)))
        pos = i + len(w)
    return spans


def build_one(text, tokens, tags, min_level, mid_rate, final_pitch):
    """返回 (xml_text, model_text, kept_tags, dropped, err)。

    kept_tags 里带 pos=final/mid 与 kind=rate/pitch，便于反查。
    """
    spans = locate(text, tokens)
    if spans is None:
        return None, None, [], [], "原文定位失败"

    last_tok = len(tokens) - 1
    kept, dropped = [], []
    for t in tags:
        tok = t["tok"]
        level = t["level"]
        if tok > last_tok:
            dropped.append(dict(t, drop="tok 越界"))
            continue
        if level < min_level:
            dropped.append(dict(t, drop="level<%.2f" % min_level))
            continue
        word = tokens[tok]
        is_final = (tok == last_tok)
        # 硬约束：句末用 pitch，句中用 rate，二选一，永不叠加
        if is_final:
            span = MK.pitch(word, final_pitch)
            kind, pos = "pitch", "final"
        else:
            span = MK.rate(word, mid_rate)
            kind, pos = "rate", "mid"
        kept.append({"tok": tok, "word": word, "level": level, "kind": kind,
                     "pos": pos, "why": t.get("why", ""),
                     "vote": t.get("vote", ""), "n": t.get("n", 0),
                     "_start": spans[tok][0], "_end": spans[tok][1], "_span": span})

    # 重叠检查：两个标签不能套住同一段字符（Operations cannot nest or cross）
    kept.sort(key=lambda x: x["_start"])
    for a, b in zip(kept, kept[1:]):
        if b["_start"] < a["_end"]:
            return None, None, [], [], "标签重叠 %s/%s" % (a["word"], b["word"])

    # 从后往前插，避免 offset 漂移；原文其余字符一字不改
    marked = text
    for x in sorted(kept, key=lambda y: -y["_start"]):
        s, e = x["_start"], x["_end"]
        marked = marked[:s] + x["_span"] + marked[e:]

    # MK.rate()/pitch() 产出的**已经是模型格式**，to_model_format 在这里幂等；
    # 留着是为了以后若改成标准 XML 构造，这一跳会自动生效。
    model_text = MK.to_model_format(marked)
    clean = [{k: v for k, v in x.items() if not k.startswith("_")} for x in kept]
    return to_std_xml(model_text), model_text, clean, dropped, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ann", default=DEFAULT_ANN)
    ap.add_argument("--tasks", default=DEFAULT_TASKS)
    ap.add_argument("--out", default=os.path.join(ROOT, "stress_tts_narr.json"))
    ap.add_argument("--min-level", type=float, default=MIN_LEVEL)
    ap.add_argument("--mid-rate", type=float, default=MID_RATE)
    ap.add_argument("--final-pitch", type=int, default=FINAL_PITCH)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 句（调试）")
    a = ap.parse_args()

    tasks, nbatch = load_tasks(a.tasks)
    ann = load_ann(a.ann)
    print("任务包 %d 批 / %d 句" % (nbatch, len(tasks)))
    print("stress 标注 %d 条 / %d 句（阈值 level>=%.2f）"
          % (sum(len(v) for v in ann.values()), len(ann), a.min_level))

    items, problems = {}, []
    dropped_all = collections.Counter()
    kinds = collections.Counter()
    sids = sorted(ann)
    if a.limit:
        sids = sids[:a.limit]

    n_tags = 0
    for sid in sids:
        it = tasks.get(sid)
        if not it:
            problems.append("%s 不在任务包" % sid)
            continue
        xml_text, model_text, kept, dropped, err = build_one(
            it["text"], it["tokens"], ann[sid], a.min_level, a.mid_rate, a.final_pitch)
        if err:
            problems.append("%s %s" % (sid, err))
            continue
        for d in dropped:
            dropped_all[d["drop"]] += 1
        for k in kept:
            kinds[(k["pos"], k["kind"])] += 1
        n_tags += len(kept)
        items[sid] = {"text": it["text"], "xml": xml_text,
                      "model": model_text, "tags": kept}

    n_inject_sids = sum(1 for v in items.values() if v["tags"])
    print("\n读过 %d 句 / 其中 %d 句要注入（%.1f%%）共 %d 处"
          % (len(items), n_inject_sids, 100.0 * n_inject_sids / max(1, len(items)), n_tags))
    print("  位置分布：" + ", ".join("%s/%s=%d" % (p, k, n) for (p, k), n in sorted(kinds.items())))
    print("  跳过：" + (", ".join("%s=%d" % kv for kv in sorted(dropped_all.items())) or "无"))
    if problems:
        print("  ⚠ 问题 %d 条：" % len(problems))
        for x in problems[:8]:
            print("    " + x)
        if len(problems) > 8:
            print("    …共 %d" % len(problems))

    # 格式自检：model 版里逗号标签数必须 == 该句 tags 数
    bad_fmt = []
    for sid, v in items.items():
        nm = v["model"].count("<rate,") + v["model"].count("<pitch,")
        if nm != len(v["tags"]):
            bad_fmt.append("%s model标签%d tags%d" % (sid, nm, len(v["tags"])))
    print("  格式自检：标签数不符 %d 句" % len(bad_fmt))
    for x in bad_fmt[:5]:
        print("    " + x)

    # 样例
    for sid in sids:
        if sid in items and items[sid]["tags"]:
            v = items[sid]
            print("\n样例 %s" % sid)
            print("  原：%s" % v["text"])
            print("  xml：%s" % v["xml"])
            print("  model：%s" % v["model"])
            break

    if a.dry:
        print("\n（--dry，未写文件）")
        return 0

    payload = {
        "_meta": {
            "src": os.path.basename(a.ann),
            "tasks": os.path.basename(os.path.normpath(a.tasks)),
            "rule": "句中 level>=%.2f -> <rate factor=%.2f>；句末 -> <pitch semitones=%d>；永不叠加"
                    % (a.min_level, a.mid_rate, a.final_pitch),
            "requires_task": "tts",
            "warn": "pitch 只在 --task tts 生效；edit 模板下无效（F0 80.9→80.9Hz）",
            "use_when": "按 REQUIREMENTS.md 第零节工作流第 ④ 步，前 3 个 seed 都不达标才用",
            "note": "model 字段是真正喂 dots.tts 的文本（逗号格式）；xml 供人读与评测",
            "n_sid": len(items), "n_tag": n_tags,
        },
        "items": items,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print("\n写出 %s（%.1f KB）" % (a.out, os.path.getsize(a.out) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
