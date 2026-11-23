# -*- coding: utf-8 -*-
"""全库对白体检：内容 / 亮度 / 音高 / 静音 / 电平 / 重复音频。

为什么要有这一个脚本：
  前几轮都是「用户听出问题 -> 才去量那一条」。这次反着来：把已知的每一类缺陷
  一次算全 239 条，按 (角色, 情绪) 分组取中位做基线，找离群。

指标
  tech      : dur / voiced RMS / 静音比
  voiced-tilt: 只取有声帧（F0>0）的 2~5k / 200~1k 能量比 —— 「喊」的量化
  f0        : 有声帧 F0 中位
  content   : ASR vs 原文，字符级 cov/sim + 词级 lead(开头多念) / miss(吞字) / trunc(结尾断)
  dup       : 同 md5

判据见 DECISIONS.md「voiced-tilt」与「LEAD_REF」两条。

用法：G:/Python310/python.exe _audit_all.py
"""
import collections
import difflib
import hashlib
import io
import json
import os
import re
import sys

import numpy as np
import parselmouth
import soundfile as sf
from numpy.fft import rfft
from parselmouth.praat import call

sys.path.insert(0, "G:/_setup")
from _short_gate import tech
from wlevel_flags import coverage

ROOT = "G:/_setup"
AUD = os.path.join(ROOT, "_audio_ch123", "out_paused")
PLAN = os.path.join(ROOT, "_dlg_plan_v2_paused.jsonl")
GATE = os.path.join(ROOT, "_gate_dlg_v41.json")
ASR = os.path.join(ROOT, "_audit_asr.json")
WR = os.path.join(ROOT, "_whisper_recall.json")

SHOUT = {"激动反抗", "兴奋", "生气", "愤怒", "怒吼"}
WIN = np.hanning(1024)


def norm_words(t):
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9'\u00c0-\u024f ]+", " ", t)
    t = t.replace("'", "")
    return [w for w in t.split() if w]


def vfeat(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    y = np.ascontiguousarray(y, dtype="float32")
    pit = call(parselmouth.Sound(y, sr), "To Pitch", 0.0, 75, 600)
    f = pit.selected_array["frequency"]
    tilts, f0s = [], []
    for k, val in enumerate(f):
        c = int(k * 0.01 * sr)
        seg = y[max(0, c - 512):max(0, c - 512) + 1024]
        if len(seg) < 1024 or val <= 0:
            continue
        if np.sqrt((seg ** 2).mean()) < 0.01:
            continue
        m = np.abs(rfft(seg * WIN)) + 1e-12
        fr = np.linspace(0, sr / 2, len(m))
        lo = m[(fr > 200) & (fr < 1000)].mean()
        hi = m[(fr > 2000) & (fr < 5000)].mean()
        if lo <= 0:
            continue
        tilts.append(float(hi / lo))
        f0s.append(float(val))
    return (float(np.median(tilts)) if tilts else None,
            float(np.median(f0s)) if f0s else None)


def wdiff(ref, hyp):
    a, b = norm_words(ref), norm_words(hyp)
    if not a:
        return 0, 0, False
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = sm.get_opcodes()
    lead = 0
    miss = 0
    trunc = False
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        if tag == "insert" and i1 == 0:
            lead = j2 - j1
        elif tag == "delete":
            miss += i2 - i1
            if i2 >= len(a) - 0 and len(a) - i2 <= 0:
                trunc = True
        elif tag == "replace":
            miss += max(0, (i2 - i1) - (j2 - j1))
    # 结尾是否断：最后一个 opcode 之后原文还有词没被覆盖到
    last = ops[-1]
    if last[0] != "equal" or last[2] < len(a):
        if last[2] < len(a) and (len(a) - last[2]) <= 3:
            trunc = True
    return lead, int(miss), bool(trunc)


def main():
    plan = {}
    for l in io.open(PLAN, encoding="utf-8"):
        if l.strip():
            x = json.loads(l)
            plan[x["id"]] = x
    asr = json.load(io.open(ASR, encoding="utf-8"))
    wr = json.load(io.open(WR, encoding="utf-8")) if os.path.exists(WR) else {}
    gate = {os.path.basename(x["wav"])[:-4]: x
            for x in json.load(io.open(GATE, encoding="utf-8"))}

    rows = []
    for i in sorted(plan):
        p = os.path.join(AUD, i + ".wav")
        if not os.path.exists(p):
            continue
        pl = plan[i]
        t = tech(p)
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        md5 = hashlib.md5(np.ascontiguousarray(y).tobytes()).hexdigest()[:10]
        tl, f0 = vfeat(p)
        said = (asr.get(i) or {}).get("text") or ""
        ref = pl.get("text") or ""
        cov, sim = coverage(ref, said)
        lead, miss, trunc = wdiff(ref, said)
        rows.append(dict(id=i, who=pl["who"], emo=pl["emo"], text=ref, said=said,
                         dur=round(t["dur"], 2), rms=round(t["rms_db"], 2),
                         silent=round(t["silent"], 2), tilt=tl, f0=f0,
                         cov=round(cov, 2), sim=round(sim, 2),
                         lead=lead, miss=miss, trunc=trunc, md5=md5,
                         wrecall=wr.get(i), gate=(gate.get(i) or {}).get("verdict")))

    # 分组基线
    grp = collections.defaultdict(list)
    for r in rows:
        if r["tilt"] is not None:
            grp[r["who"]].append(r["tilt"])
    role_med = {k: float(np.median(v)) for k, v in grp.items()}
    gem = collections.defaultdict(list)
    for r in rows:
        if r["tilt"] is not None:
            gem[(r["who"], r["emo"])].append(r["tilt"])
    gem_med = {k: float(np.median(v)) for k, v in gem.items()}
    gf0 = collections.defaultdict(list)
    for r in rows:
        if r["f0"]:
            gf0[r["who"]].append(r["f0"])
    f0_p = {k: (float(np.percentile(v, 5)), float(np.percentile(v, 95))) for k, v in gf0.items()}

    dup = collections.Counter(r["md5"] for r in rows)

    for r in rows:
        f = []
        if dup[r["md5"]] > 1:
            f.append("dup")
        if r["lead"] >= 2:
            f.append("lead")
        if r["miss"] >= 2:
            f.append("miss")
        if r["trunc"]:
            f.append("trunc")
        if not (r["cov"] >= 0.90 and r["sim"] >= 0.80):
            if r["cov"] < 0.75 and (r["wrecall"] is None or r["wrecall"] < 0.80):
                f.append("content")
            else:
                f.append("content?")
        if r["emo"] not in SHOUT and r["tilt"] is not None:
            base = gem_med.get((r["who"], r["emo"])) or role_med.get(r["who"]) or 0.1
            if r["tilt"] > max(0.30, 3.0 * base):
                f.append("shout")
        if r["f0"] and r["who"] in f0_p:
            lo, hi = f0_p[r["who"]]
            if r["f0"] > hi * 1.08:
                f.append("f0_hi")
            elif r["f0"] < lo * 0.90:
                f.append("f0_lo")
        if r["silent"] > 0.55 and r["dur"] >= 1.6:
            f.append("silent")
        if not (-25.5 <= r["rms"] <= -22.5):
            f.append("level")
        r["flags"] = f

    bad = [r for r in rows if r["flags"]]
    bad.sort(key=lambda r: (-len(r["flags"]), r["id"]))

    L = []
    L.append("# 对白全库体检（%d 条）\n" % len(rows))
    L.append("| 项 | 值 |\n|---|---|")
    L.append("| 有声帧 tilt 中位 | %s |" % ", ".join("%s %.3f" % (k, role_med[k]) for k in sorted(role_med)))
    L.append("| 电平 | 中位 %.2f，跨度 %.2f，越界 %d |" % (
        np.median([r["rms"] for r in rows]),
        max(r["rms"] for r in rows) - min(r["rms"] for r in rows),
        sum(1 for r in rows if "level" in r["flags"])))
    L.append("| 重复音频 | %d 组 |" % sum(1 for k, v in dup.items() if v > 1))
    L.append("| 有问题的条目 | **%d** |" % len(bad))
    L.append("")
    cnt = collections.Counter(f for r in rows for f in r["flags"])
    L.append("标记分布：" + "，".join("%s %d" % (k, v) for k, v in cnt.most_common()) + "\n")
    L.append("## 明细\n")
    L.append("| id | 角色 | 情绪 | 标记 | tilt | F0 | dur | silent | cov/sim | lead/miss | 原文 → ASR |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in bad:
        L.append("| %s | %s | %s | %s | %s | %s | %.2f | %.2f | %.2f/%.2f | %d/%d | %s → %s |" % (
            r["id"], r["who"], r["emo"], ",".join(r["flags"]),
            ("%.3f" % r["tilt"]) if r["tilt"] is not None else "-",
            ("%.0f" % r["f0"]) if r["f0"] else "-",
            r["dur"], r["silent"], r["cov"], r["sim"], r["lead"], r["miss"],
            (r["text"] or "")[:38].replace("|", "/"),
            (r["said"] or "")[:38].replace("|", "/")))
    md = "\n".join(L)
    io.open(os.path.join(ROOT, "_dlg_audit.md"), "w", encoding="utf-8").write(md)
    json.dump(rows, io.open(os.path.join(ROOT, "_dlg_audit.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(md[:3000])
    print("\n写出 _dlg_audit.md / _dlg_audit.json，问题条目 %d / %d" % (len(bad), len(rows)))


if __name__ == "__main__":
    main()
