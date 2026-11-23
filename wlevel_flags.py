# -*- coding: utf-8 -*-
"""wlevel_flags.py —— 词级表 → take 级旗标（POC-A 判定层）。

为什么用字符级覆盖率做「内容对不对」的主判据：
  词级精确匹配对写法差异太脆：`O.K.` → whisper 输出 `Okay.` 会判成完全不匹配。
  字符级 SequenceMatcher 对同义写法宽容，对「整句换掉」依旧敏感。

五类旗（都是现有闸门看不见的）：
  NO_TARGET  音频里根本没有目标台词（覆盖率 < 45%）—— 语声再好也是废件
  LEAD_REF   目标在，但开头先念了音色参考句（>=3 词）
  TRUNC      目标只在一半（45%~75%）—— 尾部被切 / 中途丢词
  FLAT_RUN   连续 >=3 词 f0_std 低于本批中位一半，且跨度 >=1.0s —— 只能词级才看得见
  LOW_PROB   单词置信度 < 0.35 且真有能量 —— 吞字候选

参系一律用**本批中位数**，不用外部预测器（centroid trick）。
"""
import argparse
import csv
import difflib
import glob
import io
import json
import os
import re
import statistics as st
from collections import Counter

ROOT = "G:/_setup"
PLAN = os.path.join(ROOT, "_castle_en_ch123_plan.jsonl")


def collect_ref_texts():
    out = set()
    for p in glob.glob(os.path.join(ROOT, "_cloud_pkg", "*", "pt.txt")):
        for line in io.open(p, encoding="utf-8"):
            if "|" in line:
                out.add(line.split("|", 1)[1].strip())
    for p in (os.path.join(ROOT, "_emo_refs_all.json"),
              os.path.join(ROOT, "_cloud_backup", "_emo_refs_cloud.json")):
        if not os.path.exists(p):
            continue
        try:
            d = json.load(io.open(p, encoding="utf-8"))
        except Exception:
            continue
        for spk, byemo in d.items():
            if not isinstance(byemo, dict):
                continue
            for emo, lst in byemo.items():
                for it in (lst or []):
                    t = (it or {}).get("text") if isinstance(it, dict) else None
                    if t and len(t) > 12:
                        out.add(t.strip())
    return [t for t in out if t]


def alnum(s):
    s = s.lower().replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"[^a-z0-9]+", "", s)


def coverage(expected, said):
    """expected 的字有多少被 said 命中（0~1）。"""
    a, b = alnum(expected), alnum(said)
    if not a:
        return 0.0, 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    hit = sum(bl.size for bl in sm.get_matching_blocks())
    return hit / float(len(a)), sm.ratio()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--words", default=os.path.join(ROOT, "_wl_all.csv"))
    ap.add_argument("--takes", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "_wl_flags.jsonl"))
    ap.add_argument("--md", default=os.path.join(ROOT, "_wl_flags.md"))
    a = ap.parse_args()
    takes_csv = a.takes or a.words.replace(".csv", "_takes.csv")

    plan = {json.loads(l)["id"]: json.loads(l) for l in io.open(PLAN, encoding="utf-8") if l.strip()}
    W = list(csv.DictReader(io.open(a.words, encoding="utf-8-sig")))
    T = {r["tid"]: r for r in csv.DictReader(io.open(takes_csv, encoding="utf-8-sig"))}
    by = {}
    for r in W:
        by.setdefault(r["tid"], []).append(r)

    fstd = [float(r["f0_std_st"]) for r in W if r["f0_std_st"]]
    edb = [float(r["energy_db"]) for r in W if r["energy_db"]]
    thr_f = 0.5 * st.median(fstd)
    med_e = st.median(edb)
    thr_take = 0.5 * st.median([float(x["f0_std_med"]) for x in T.values() if x.get("f0_std_med")])
    print("参系：词级 f0_std 中位 %.2f st → 词级塔平阈 %.2f | 整条塔平阈 %.2f | 能量中位 %.1f dB"
          % (st.median(fstd), thr_f, thr_take, med_e))

    flags = []
    for tid in T:
        rs = by.get(tid, [])
        t = T[tid]
        rec = plan.get(tid, {})
        exp = rec.get("text", "")
        said = " ".join(x["w"] for x in rs)
        cov, sim = coverage(exp, said)
        nexp = int(t.get("n_word_exp") or 0)
        dur = float(t.get("audio_dur") or 0)
        wpm = round(60.0 * nexp / dur) if dur else 0

        matched = [i for i, r in enumerate(rs) if r["exp_w"]]
        first = matched[0] if matched else len(rs)
        last = matched[-1] if matched else -1
        lead = [x["w"] for x in rs[:first]]
        n_miss = max(0, nexp - len(matched))

        f = []
        if cov < 0.45:
            f.append("NO_TARGET")
        elif cov < 0.75:
            f.append("TRUNC")
        if len(lead) >= 3 and cov >= 0.45:
            f.append("LEAD_REF")
        # wpm 对短句天生失效（1 词 p50=71 / 4-7 词 167），只对 >=8 词判档
        if wpm > 255 and nexp >= 8:
            f.append("PACE")

        best_run, cur = [], []
        for i in range(max(0, first), last + 1):
            r = rs[i]
            v = r["f0_std_st"]
            ok = r["exp_w"] and v and float(v) < thr_f and r["n_fr"] and int(r["n_fr"]) >= 5
            if ok:
                cur.append(r)
                if len(cur) > len(best_run):
                    best_run = list(cur)
            else:
                cur = []
        flat_span = (float(best_run[-1]["t1"]) - float(best_run[0]["t0"])) if best_run else 0.0
        if len(best_run) >= 3 and flat_span >= 1.0:
            f.append("FLAT_RUN")
        fs_med = t.get("f0_std_med")
        if fs_med and float(fs_med) < thr_take:
            f.append("FLAT_TAKE")

        # Parakeet 的 logprob 极度尖锐（本批中位 1.000 / p5 0.836），脆声口径的 0.35 几乎不命中；
        # 改 p<0.5（本批约 1.5%）+ 至少 5 帧浨音 + 不在开头的参考句里。
        low = [x["w"] for i, x in enumerate(rs) if i >= first and x["asr_prob"]
               and float(x["asr_prob"]) < 0.5 and x["n_fr"] and int(x["n_fr"]) >= 5]
        if low:
            f.append("LOW_PROB")

        flags.append(dict(
            tid=tid, spk=t.get("spk"), conf=t.get("conf"),
            text=exp[:90], said=said[:90],
            cov=round(cov, 3), sim=round(sim, 3),
            dur=round(dur, 2), nexp=nexp, wpm=wpm,
            n_lead=len(lead), lead_txt=" ".join(lead)[:50], n_miss=n_miss,
            flat_run=[x["w"] for x in best_run][:6], flat_span=round(flat_span, 2),
            f0_std_med=t.get("f0_std_med"), energy_span=t.get("energy_span"),
            low_prob=low[:4],
            flags=f, verdict=("OK" if not f else "FAIL")))

    with io.open(a.out, "w", encoding="utf-8") as fo:
        for r in flags:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(flags)
    c = Counter()
    for r in flags:
        for x in r["flags"]:
            c[x] += 1
    ok = sum(1 for r in flags if not r["flags"])
    L = ["# 词级旗标汇总（%d 条）\n" % n,
         "参系：词级 f0_std 中位 %.2f st（词级塔平阈 %.2f · 整条塔平阈 %.2f）· 能量中位 %.1f dB\n" % (st.median(fstd), thr_f, thr_take, med_e),
         "| 旗标 | 条数 | 占比 |", "|---|---|---|"]
    for k, v in c.most_common():
        L.append("| %s | %d | %.1f%% |" % (k, v, 100.0 * v / n))
    L.append("\n**干净 %d / %d = %.1f%%**\n" % (ok, n, 100.0 * ok / n))

    for tag, key in [
        ("NO_TARGET：音频里没有这句台词", "NO_TARGET"),
        ("TRUNC：目标只念了一半", "TRUNC"),
        ("LEAD_REF：开头先念了音色参考句", "LEAD_REF"),
        ("FLAT_RUN：连续多词音高塔平", "FLAT_RUN"),
        ("FLAT_TAKE：整条塔平", "FLAT_TAKE"),
        ("PACE：语速超过 255wpm 上限", "PACE"),
    ]:
        rows = [r for r in flags if key in r["flags"]]
        if key in ("NO_TARGET", "TRUNC"):
            rows.sort(key=lambda r: r["cov"])
        elif key in ("PACE",):
            rows.sort(key=lambda r: -r["wpm"])
        elif key == "LEAD_REF":
            rows.sort(key=lambda r: -r["n_lead"])
        else:
            rows.sort(key=lambda r: -len(r["flat_run"]))
        if not rows:
            continue
        L.append("\n## %s（共 %d 条，列前 20）\n" % (tag, len(rows)))
        L.append("| tid | 覆盖 | 时长 | wpm | 实际听到 | 应读文本 |")
        L.append("|---|---|---|---|---|---|")
        for r in rows[:20]:
            L.append("| %s | %.0f%% | %.1fs | %d | %s | %s |" % (
                r["tid"], 100 * r["cov"], r["dur"], r["wpm"],
                r["said"].replace("|", "/")[:44], r["text"].replace("|", "/")[:40]))
    io.open(a.md, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:12]))
    print("\n→ %s\n→ %s" % (a.out, a.md))


if __name__ == "__main__":
    main()
