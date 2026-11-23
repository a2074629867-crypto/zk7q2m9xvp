# -*- coding: utf-8 -*-
"""_pick52.py —— 候选择优（原速重生成后的选片）

对 `_sweep/cand52` 里每个 id 的多个 seed：
  1. 语气闸（`_calm_gate.judge`，已按用户 2026-11-20 反馈去掉「亮=紧张」）
  2. 内容闸（Parakeet ASR vs plan.text，词级覆盖率 + 序列相似度）
  3. 时长合理性（相对同角色平静语速推算的期望时长，0.75~1.45 倍）
四项全过才进推荐池；否则按「内容 > 语气 > 时长」排劣。

用法：
  G:/Python310/python.exe _pick52.py --ids c2_0246,c2_0279 --cand _sweep/cand52
"""
import argparse
import difflib
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
import _calm_gate as CG

ROOT = "G:/_setup"
ASR_PY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")


def norm_words(t):
    t = (t or "").lower()
    # ASR 会把 O.K. 写成 Okay、把 It's 写成 Its —— 先归一，避免假性缺词
    t = t.replace("o.k.", "okay").replace("o k", "okay")
    t = t.replace("\u2018", " ").replace("\u2019", "'").replace("\u201c", " ").replace("\u201d", " ")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    # 只留含字母数字的 token：plan 文本的 ’ 会被归一成孤立 "'"，不滤掉就凭空多一个词
    return [w for w in t.split() if any(c.isalnum() for c in w)]


_SUF = ("ing", "ed", "es", "s", "e")


def stem(w):
    w = w.replace("'", "")
    if w in ("ok", "okay"):
        return "okay"
    changed = True
    while changed and len(w) > 4:
        changed = False
        for suf in _SUF:
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                changed = True
                break
    return w


def words_match(a, b):
    """词级等价：去撇号 + 后缀归一 + 近似拼写。

    wav2vec2-960h 是字符级 CTC，同一个词不同次解码会给出不同拼法
    （LONDON→LONDAY、THAT→HAT、THERE'S→RE'S、STUFF IT→STUFFIT）。
    只做精确匹配会把这些全判成「丢词」，实测 17 条覆盖率骤降全是这种假警报。
    所以：长度 ≥5 时允许 1 个字符编辑距离，≥8 时允许 2 个；短词仍要求精确。
    """
    if a == b:
        return True
    if stem(a) == stem(b):
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True          # STUFF / STUFFIT
    if abs(len(a) - len(b)) > 2 or min(len(a), len(b)) < 4:
        return False
    # 2026-11-21 二改：门槛从 5 降到 4。
    # PICK→PICG、OKAY→OKI、SEE→SEA 这类单字母偏差在 4 字母词上非常常见，
    # 原来一律不容忍，把 19 条只有拼写偏差的条目误判成 D 档（实测复算：
    # c3_0858 PICK→PICG cov 0.67，放宽后 1.00，音频本身没问题）。
    # 代价是 4 字母词里真的读错会漏判 —— 这类交给 w2v 后验分数（_align_gate 的 issues）。
    lim = 2 if min(len(a), len(b)) >= 7 else 1
    # Levenshtein（限长，代价可忽略）
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= lim


def coverage(gold, hyp):
    """gold 有多少词能在 hyp 里找到（顺序无关的召回）。

    命中规则：单词等价 → 相邻两词拼接后等价（ASR 会把 goodnight 切成 good night）。
    阈值由调用方定；这个量只回答「有没有整词被吞」。
    """
    if not gold:
        return 0.0
    pool = list(hyp)
    hit = 0
    for g in gold:
        k = next((i for i, h in enumerate(pool) if words_match(g, h)), -1)
        if k < 0:
            for i in range(len(pool) - 1):
                if words_match(g, pool[i] + pool[i + 1]):
                    pool.pop(i + 1)
                    k = i
                    break
        if k >= 0:
            hit += 1
            pool.pop(k)
    return hit / len(gold)


def sim(gold, hyp):
    return difflib.SequenceMatcher(None, gold, hyp).ratio()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--cand", default="G:/_setup/_sweep/cand52")
    ap.add_argument("--asr-json", default="G:/_setup/_words_cand52.json")
    ap.add_argument("--out", default="G:/_setup/_pick52.json")
    ap.add_argument("--no-asr", action="store_true")
    a = ap.parse_args()

    plan = CG.load_plan()
    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    files = []
    for i in ids:
        files += sorted(glob.glob(os.path.join(a.cand, "%s*__s*.wav" % i)))
    files = sorted(set(files))
    if not files:
        print("没有候选")
        return

    if not a.no_asr:
        r = subprocess.run([ASR_PY, os.path.join(ROOT, "_asr_lib.py"),
                            "--out", a.asr_json, "--append"] + files,
                           cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print((r.stdout or "").strip()[-300:])
        if r.returncode:
            print((r.stderr or "")[-500:])
    asr = {}
    if os.path.exists(a.asr_json):
        asr = json.load(open(a.asr_json, encoding="utf-8"))

    base_cache = {}
    def base_of(role):
        if role not in base_cache:
            base_cache[role] = CG.baseline(plan, role)
        return base_cache[role]

    rows = []
    for f in files:
        tag = os.path.basename(f)[:-4]
        # id 恒为 c[123]_dddd 七字符；后面的 x/e/p/z 是文本变体标记
        rid = tag.split("__")[0][:7]
        p = plan.get(rid) or {}
        text = p.get("text_src") or p.get("text") or ""
        gold = norm_words(text)
        nw = len([w for w in text.split() if any(c.isalnum() for c in w)])
        m = CG.measure(f, nw, text)
        rs, info = CG.judge(m, base_of(p.get("who") or "Charles"), p.get("emo") or "")
        hyp = norm_words((asr.get(f) or {}).get("text") or "")
        cov = coverage(gold, hyp) if hyp else None
        s = sim(gold, hyp) if hyp else None
        bad = []
        if cov is not None and cov < 0.85:
            bad.append("内容缺词 cov=%.2f" % cov)
        if not bad:
            bad = None
        rows.append(dict(tag=tag, id=rid, path=f, m=m, reasons=rs, info=info,
                         cov=cov, sim=s, ratio=None,
                         reject=bad,
                         score=(round(cov or 0, 3), round(s or 0, 3), -len(rs))))

    # 时长离群：同一 id 的多个 seed 互为参照（不用全局语速模型 —— 短句的 wpm_voiced
    # 系统性虚高，拿它推期望时长会把正常渲染全判成「时长异常」，实测 4/4 全误杀）
    by_id = {}
    for r in rows:
        by_id.setdefault(r["id"], []).append(r)
    for rid, grp in by_id.items():
        ds = sorted(g["m"]["dur"] for g in grp)
        med = ds[len(ds) // 2]
        for g in grp:
            ratio = g["m"]["dur"] / med if med else None
            g["ratio"] = round(ratio, 2) if ratio else None
            if ratio is not None and (ratio < 0.75 or ratio > 1.35) and len(ds) >= 2:
                if g["reject"] is None:
                    g["reject"] = ["时长离群 %.2f×同 id 中位" % ratio]
    rows.sort(key=lambda x: (x["reject"] is not None, -x["score"][0], -x["score"][1]))
    best = {}
    for r in rows:
        print("%-16s dur=%.2f wpm=%d F0=%d tilt=%.3f cov=%s sim=%s ratio=%s %s%s" %
              (r["tag"], r["m"]["dur"], r["m"]["wpm_all"], r["m"]["F0"], r["m"]["tilt"],
               "%.2f" % r["cov"] if r["cov"] is not None else "-",
               "%.2f" % r["sim"] if r["sim"] is not None else "-",
               r["ratio"] if r["ratio"] is not None else "-",
               ("REJ:" + ";".join(r["reject"])) if r["reject"] else "OK",
               ("  [" + ";".join(r["reasons"]) + "]") if r["reasons"] else ""))
        if not r["reject"] and not r["reasons"]:
            best.setdefault(r["id"], r["tag"])
    print()
    for k, v in best.items():
        print("推荐 %-9s -> %s" % (k, v))
    json.dump(dict(rows=rows, best=best), open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
