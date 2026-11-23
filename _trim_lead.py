# -*- coding: utf-8 -*-
"""裁掉「开头多念的参考词」（LEAD_REF）。

问题来源（`_wl_flags_all.jsonl`，11-12 跑的词级体检，之后没人处理）：
  对白 239 条里 **60 条** 开头多念了参考片段的词 —— 例如 `c1_0002`
  原文 "I will not live there again, until it belongs to me, his father had said."
  实际音频是 "**My father was a reserved man** I will not live there again..."，
  多出来的那句正是 `Joseph_normal_1` 参考片段的原文。dots.tts 把参考的文本也念了。

七闸里没有任何一维管这个（`cov` 是 1.00、`sim` 0.83，闸全绿），
所以它一路进了交付。这一维只能靠词级 ASR 比对。

修法：ASR 词序列 vs 原文做序列对齐，找到正文第一个稳定匹配块，
把它之前的词整段裁掉（切点取前缀末词之后最近的静音谷），20ms 淡入。

用法：
  python _trim_lead.py --ids c1_0002,c1_0027 --dry      # 只看切点
  python _trim_lead.py --ids c1_0002,c1_0027 --apply    # 真裁（自动备份）
  python _trim_lead.py --from-ledger --apply            # 全量 LEAD_REF
"""
import argparse
import difflib
import json
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

AUD = os.path.join(HERE, "_audio_ch123", "out")
PLAN = os.path.join(HERE, "_dlg_plan_v2.jsonl")
LEDGER = os.path.join(HERE, "_wl_flags_all.jsonl")


def norm_words(s):
    import re
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[^A-Za-z']+", " ", s)
    return [w.lower().strip("'") for w in s.split() if w.strip("'")]


def recall(ref, hyp):
    if not ref:
        return 0.0
    i = hit = 0
    for w in hyp:
        while i < len(ref):
            if ref[i] == w or ref[i] in w or w in ref[i]:
                hit += 1
                i += 1
                break
            i += 1
        else:
            break
    return hit / float(len(ref))


def find_lead(ref, hyp):
    """返回 hyp 里属于「正文之前」的词数。找不到稳定匹配块时返回 None。"""
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    for blk in sm.get_matching_blocks():
        if blk.size < 3:
            continue
        # ★ 正文开头若在 ASR 里被漏掉（blk.a > 0），那 blk.a 个词其实还在前缀尾部，
        #   直接返回 blk.b 会把正文前几个词一起切掉。实测 c2_0447（ref "edmund you are
        #   behaving..." → ASR 从 "behaving" 起匹配，blk.a=2/blk.b=11）切掉 "edmund you"；
        #   c2_0438 切掉 "they will"；c1_0158 切掉 "i have seen you"。
        #   ⇒ 前缀长度应为 blk.b - blk.a。
        return max(0, blk.b - blk.a)
    return None


def cut_point(y, sr, t_end, win=0.22):
    """从 t_end 起在 win 秒内找能量最低点（静音谷）；找不到合适的就直接用词尾 +30ms。

    ★ win 原来是 0.45，会吃到下一个词：c2_0438 前缀末词止 1.76，谷在 2.20，
      而正文首词 "they" 从 ~1.9 就开始 ⇒ 切掉了 "they will" 两个词（召回 1.00→0.83）。
      词尾之后 30ms 一定还在本词的衰减里，配 20ms 淡入不会有爆音，比"找谷"稳。
    """
    a = int(t_end * sr)
    b = min(len(y), int((t_end + win) * sr))
    if b - a < int(0.02 * sr):
        return t_end + 0.03
    fr = int(0.01 * sr)
    n = max(1, (b - a) // fr)
    e = np.array([np.sqrt((y[a + i * fr:a + (i + 1) * fr] ** 2).mean()) for i in range(n)])
    i = int(np.argmin(e))
    t_gap = (a + i * fr) / float(sr)
    # 谷离词尾太远 ⇒ 那是下一个词之间的空档，别用它
    return t_gap if (t_gap - t_end) <= 0.14 else t_end + 0.03


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--from-ledger", action="store_true",
                    help="取 _wl_flags_all.jsonl 里 flags 含 LEAD_REF 的对白条")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--backup", default="G:/_setup/_bak_trimlead_1115")
    ap.add_argument("--fade", type=float, default=0.020)
    ap.add_argument("--min-lead", type=int, default=1)
    ap.add_argument("--verify", action="store_true",
                    help="裁完用 ASR 复验召回，退化就自动从备份恢复（推荐开）")
    a = ap.parse_args()

    import soundfile as sf
    from transplant_prosody2 import word_times

    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l)
            plan[o["id"]] = o

    ids = []
    if a.from_ledger:
        for l in open(LEDGER, encoding="utf-8"):
            l = l.strip()
            if not l:
                continue
            o = json.loads(l)
            if o.get("spk") != "narrator" and "LEAD_REF" in (o.get("flags") or []):
                ids.append(o["tid"])
    if a.ids:
        ids += [x.strip() for x in a.ids.split(",") if x.strip()]
    ids = sorted(set(ids))
    if not ids:
        print("没有要处理的条")
        return 1
    print("处理 %d 条%s" % (len(ids), "" if a.apply else "（dry）"), flush=True)

    os.makedirs(a.backup, exist_ok=True) if a.apply else None
    rows = []
    for n, rid in enumerate(ids, 1):
        p = os.path.join(AUD, rid + ".wav")
        if not os.path.exists(p):
            print("  跳过（缺文件）", rid)
            continue
        ref = norm_words(plan[rid].get("text") or "")
        wt = word_times(p)
        hyp = norm_words(" ".join(t for _a, _b, t in wt))
        before_recall = recall(ref, hyp)
        lead = find_lead(ref, hyp)
        if lead is None or lead < a.min_lead:
            print("  %-9s 无前缀（lead=%s，ASR %d 词）" % (rid, lead, len(hyp)))
            continue
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        t_end = wt[lead - 1][1]
        t_cut = cut_point(y, sr, t_end)
        lead_txt = " ".join(hyp[:lead])
        rest = len(y) / sr - t_cut
        # 合理性：切完剩下的时长要装得下原文（允许念快，但不许 <0.20s/词）
        if ref and rest / len(ref) < 0.20:
            print("  %-9s 跳过：切完只剩 %.2fs 装 %d 词（%.2fs/词），前缀判定可疑"
                  % (rid, rest, len(ref), rest / len(ref)))
            continue
        print("  %-9s 前缀 %d 词「%s」 末词止 %.2f → 切点 %.2f（原长 %.2f，剩 %.2f）"
              % (rid, lead, lead_txt[:46], t_end, t_cut, len(y) / sr, rest), flush=True)
        rows.append(dict(id=rid, lead=lead, lead_txt=lead_txt, t_cut=round(t_cut, 3),
                         dur=round(len(y) / sr, 3)))
        if not a.apply:
            continue
        if t_cut < 0.15:
            print("    切点太靠前，跳过")
            continue
        bak = os.path.join(a.backup, rid + ".wav")
        shutil.copy2(p, bak)
        y2 = y[int(t_cut * sr):].copy()
        nf = int(a.fade * sr)
        if nf > 1 and len(y2) > nf:
            y2[:nf] *= np.linspace(0.0, 1.0, nf, dtype="float32")
        sf.write(p, y2.astype("float32"), sr, subtype="PCM_16")
        print("    已裁 → 新长 %.2f" % (len(y2) / sr), flush=True)

        if a.verify:
            # ★ 裁完必须复验：ASR 召回没变好就说明切错了（把正文当成了前缀）
            hyp2 = norm_words(" ".join(t for _a, _b, t in word_times(p)))
            r2 = recall(ref, hyp2)
            if r2 < before_recall - 1e-6:
                shutil.copy2(bak, p)
                print("    ★ 复验退化（召回 %.2f→%.2f），已恢复" % (before_recall, r2), flush=True)
                rows[-1]["reverted"] = True
            else:
                print("    复验召回 %.2f → %.2f，保留" % (before_recall, r2), flush=True)
                rows[-1]["recall_after"] = round(r2, 3)
        if n % 15 == 0:
            print("    …%d/%d" % (n, len(ids)), flush=True)

    out = os.path.join(HERE, "_trim_lead_log.json")
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
