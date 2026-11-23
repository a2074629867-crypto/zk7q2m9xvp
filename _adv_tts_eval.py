# -*- coding: utf-8 -*-
"""_adv_tts_eval.py —— tts 纯生成各条件的对照评估。

回答的唯一问题：**标签加时长，是真的把整句撑长了，还是从邻词借的？**

三个量：
    file_dur   整段文件时长（含首尾静音）
    speech_dur 全句有声帧总长（voiced × 5ms）—— 真·发声时间，去掉停顿的影响
    vdur[word] 每个实词的有声时长

判据：
    speech_dur 变长 + 邻词 vdur 基本不变  ⇒ 真的变长了（模型自己多花了时间）
    speech_dur 不变 + 目标词 +X / 邻词 −X ⇒ 只是重新分配（edit 的行为）

用法：
    python _adv_tts_eval.py --tag N0627_base_s2051 --tag N0627_r7_s2051 ...
    python _adv_tts_eval.py --group N0627            # 自动取该单元全部条件
"""
import argparse
import glob
import json
import os
import statistics as S
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")
import _adv_align as A
import _f0_accent as F
import _adv_prom as P
import _adv_vdur as V

ROOT = "G:/_setup"
STATE = os.path.join(ROOT, "_mt_adv_state.json")
PROM_DIR = os.path.join(ROOT, "_wpt_out")


def one(tag, text, adv):
    wav = os.path.join(ROOT, "_adv_tts", tag + ".wav")
    prom = os.path.join(PROM_DIR, "_adv_tts__%s.prom" % tag)
    if not (os.path.exists(wav) and os.path.exists(prom)):
        return dict(tag=tag, note="缺 wav/prom")
    ts, fs, ss, dur = F.track_ex(wav)
    rows = F.read_prom(prom)
    spans = A.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    tw = A.text_words(text)
    words = {}
    for i, x in enumerate(tw):
        if not x["is_word"] or x["key"] in F.FUNC:
            continue
        sp = spans[i]
        if sp["t0"] is None:
            continue
        tot, longest = V.vdur(ts, sp["t0"], sp["t1"])
        if tot <= 0:
            continue
        words[x["key"]] = dict(vdur=round(tot, 3), longest=round(longest, 3),
                               t0=round(sp["t0"], 2), t1=round(sp["t1"], 2))
    # 全句有声时间
    speech = float(len(ts)) * 0.005
    # 副词 F0（p75 口径，和 _adv_prom 一致）
    cws = P.measure_one(wav, prom, text) or []
    hit = [c for c in cws if c["key"] == adv]
    loc = peak = None
    if hit:
        c = hit[-1]
        loc = round(c["loc"], 2) if c["loc"] is not None else None
        peak = round(c["peak"], 2) if c.get("peak") is not None else None
    return dict(tag=tag, dur=round(dur, 2), speech=round(speech, 2),
                adv_w=adv, adv=words.get(adv), words=words, loc=loc, peak=peak)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--group", action="append", default=[])
    a = ap.parse_args()

    st = json.load(open(STATE, encoding="utf-8"))["units"]
    tags = list(a.tag)
    for g in a.group:
        tags += [os.path.basename(p)[:-4] for p in
                 sorted(glob.glob(os.path.join(ROOT, "_adv_tts", g + "_*.wav")))]
    tags = [t for t in dict.fromkeys(tags) if not t.startswith("_")]

    # 按 uid 分组：uid_cond_sSEED
    groups = {}
    for t in tags:
        parts = t.split("_")
        if len(parts) < 3:
            continue
        uid, cond, seed = parts[0], "_".join(parts[1:-1]), parts[-1]
        groups.setdefault((uid, seed), {})[cond] = t

    out = []
    for (uid, seed), conds in sorted(groups.items()):
        x = st.get(uid)
        if not x:
            continue
        text, adv = x["text"], x["adv"].lower()
        base = None
        print("\n=== %s  seed=%s   adv=%s   %s"
              % (uid, seed.replace("s", ""), x["adv"], text[:62]))
        print("  %-6s %-7s %-9s %-8s %-7s %-6s  %s"
              % ("条件", "文件s", "全句有声", "副词vdur", "邻词中位", "loc", "各词 vdur"))
        recs = {}
        for cond, tag in sorted(conds.items()):
            r = one(tag, text, adv)
            if r.get("note"):
                print("  %-6s %s" % (cond, r["note"]))
                continue
            recs[cond] = r
            if cond == "base":
                base = r
            aw = (r["adv"] or {}).get("vdur")
            others = [w["vdur"] for k, w in r["words"].items() if k != adv]
            med = S.median(others) if others else None
            r["med_other"] = med
            line = " ".join("%s=%.3f" % (k, w["vdur"]) for k, w in r["words"].items())
            print("  %-6s %-7.2f %-9.2f %-8s %-7s %-6s  %s"
                  % (cond, r["dur"], r["speech"],
                     "%.3f" % aw if aw else "-",
                     "%.3f" % med if med else "-",
                     "-" if r["loc"] is None else "%+.2f" % r["loc"], line))
        # 相对 base 的差
        if base:
            print("  ── Δ vs base ──")
            bw = base["words"]
            for cond, r in sorted(recs.items()):
                if cond == "base":
                    continue
                dsp = r["speech"] - base["speech"]
                daw = ((r["adv"] or {}).get("vdur") or 0) - ((base["adv"] or {}).get("vdur") or 0)
                shifts = []
                for k, w in r["words"].items():
                    if k in bw:
                        d = w["vdur"] - bw[k]["vdur"]
                        if abs(d) >= 0.02:
                            shifts.append("%s%+.3f" % (k + " ", d))
                print("  %-6s 全句有声 %+.2f s (%+.0f%%)  副词 %+.3f s  其它变动: %s"
                      % (cond, dsp, 100.0 * dsp / max(base["speech"], 1e-6), daw,
                         ", ".join(shifts) if shifts else "无"))
        out.append(dict(uid=uid, seed=seed, recs=recs))

    if out:
        json.dump(out, open(os.path.join(ROOT, "_adv_tts_eval.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n写出 _adv_tts_eval.json")


if __name__ == "__main__":
    main()
