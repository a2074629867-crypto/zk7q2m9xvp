# -*- coding: utf-8 -*-
"""RDR 闸门 —— 测试链里「插停顿之前」的一环。

位置：TTS 输出（逐单元）→ 裁边 → **本闸门** → 拼接插停顿 → 成品
必须放在任何停顿处理之前，理由见下。

★★★ 主口径是 C（voiced 总和），不是 RDR 原文的 B。

RDR 原文（SceneTTS-Bench）规定「VAD 去首尾静音、保留中间停顿」，因为它的
目标场景是「一个长句被切成多次合成调用」，切分段内部**不含标点停顿**。
我们的单元 180 个里 139 个（77%）含内部停顿——这些是模型念标点时自己停的
（不是我们插的；我们插的三档停顿在单元之间，属拼接阶段），其密度取决于
文本标点，与「说得快不快」无关。把停顿算进有效时长，等于把**标点密度**
当成**语速**，会造出 32% 的假超标（真值 6%）。

三种有效时长口径：
  A  常数扣减 0.25s（head_pad 0.05 + tail_pad 0.20）
  B  VAD 首尾边界（RDR 原文，含内部停顿）—— 仅作与社区数字换算用
  C  VAD voiced 总和（只算发声帧）           ← 主用

判据（voiced 口径，阈值 1.5×）：
  马修母带 ≥3 词 超 9%；≥10 词 超 0%
  我们   ch1 ≥3 词 超 6%；≥10 词 超 4%
  章级准入：RDR <= --max-rdr（默认 0.15）

用法：
  G:/Python310/python.exe mt_rdr_gate.py --ch ch1
  G:/Python310/python.exe mt_rdr_gate.py --ch ch2 --units _mt_final_raw_trim \
      --para _ch2_unit_para.json --out _rdr_gate_ch2.json
退出码：0 = PASS，1 = 超准入线，2 = 缺输入。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, "D:/py_libs")
sys.path.insert(0, "G:/_setup")
import numpy as np
import soundfile as sf
import mt_final_pause as FP


def nwords(t):
    return len(re.findall(r"[A-Za-z][A-Za-z'\-]*", t))


def durations(x, sr):
    """返回 (A, B, C) 三种有效时长。"""
    dur = len(x) / sr
    db, nfl, hop = FP.frame_db(x, sr)          # hop 是帧移样本数，不是秒
    if len(db) == 0:
        return dur, 0.0, 0.0
    thr = np.percentile(db, 90) - 25.0
    on = db > thr
    idx = np.where(on)[0]
    if len(idx) == 0:
        return dur, 0.0, 0.0
    return (dur - 0.25,
            float(idx[-1] - idx[0] + 1) * hop / sr,
            float(len(idx)) * hop / sr)


def build(rows, key, thr):
    groups = {}
    for r in rows:
        if r["pid"] is None:
            continue
        groups.setdefault(r["pid"], []).append(r)
    seams = []
    for pid, g in sorted(groups.items()):
        g = [r for r in g if r["eff_" + key] and r["eff_" + key] > 0.4
             and r["rate_" + key]]
        g.sort(key=lambda r: r["uid"])
        if len(g) < 2:
            continue
        med = float(np.median([r["rate_" + key] for r in g]))
        for a, b in zip(g, g[1:]):
            ra, rb = a["rate_" + key], b["rate_" + key]
            ratio = max(ra, rb) / min(ra, rb)
            da = abs(np.log(ra / med))
            db_ = abs(np.log(rb / med))
            seams.append(dict(pid=pid, a=a["uid"], b=b["uid"],
                              rate_a=ra, rate_b=rb, ratio=round(ratio, 2),
                              group_median=round(med, 1),
                              culprit=a["uid"] if da >= db_ else b["uid"],
                              culprit_dev=round(float(max(da, db_)), 3)))
    ngroup = len({s["pid"] for s in seams})
    bad = [s for s in seams if s["ratio"] > thr]
    return seams, bad, ngroup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--units", default="_mt_final_raw_trim",
                    help="逐单元 wav 目录（TTS 输出、裁边后，未插停顿）")
    ap.add_argument("--state", default="_mt_loop_state.json")
    ap.add_argument("--para", default="_ch1_unit_para.json",
                    help="单元→原书段落映射，接缝分组的依据")
    ap.add_argument("--out", default=None)
    ap.add_argument("--thr", type=float, default=1.5)
    ap.add_argument("--max-rdr", type=float, default=0.15,
                    help="章级准入线（马修 0.09，ch1 0.054）")
    ap.add_argument("--stage", default="pre_pause",
                    choices=["pre_pause", "post_pause"],
                    help="post_pause 时只有 C 口径可读，B/A 已失真")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if a.stage == "post_pause":
        print("⚠ 本闸门跑在停顿处理之后；B/A 口径（含内部停顿）此时失去意义，"
              "只有 C 口径可读。")
    if not os.path.exists(a.para):
        print("✗ 缺段落映射 %s —— 没有它无法区分「段内接缝」与「段间断句」，"
              "跨段语速跳变是正常的，会全被误报。" % a.para)
        return 2

    S = json.load(open(a.state, encoding="utf-8"))["units"]
    para = {r["uid"]: r.get("pid") for r in json.load(open(a.para, encoding="utf-8"))}

    rows = []
    for uid, pid in para.items():
        if S.get(uid, {}).get("ch") not in (None, a.ch):
            continue
        p = os.path.join(a.units, uid + ".wav")
        if not os.path.exists(p):
            continue
        x, sr = sf.read(p, dtype="float32", always_2d=True)
        x = x.mean(1)
        w = nwords(S[uid]["text"])
        if w < 3:
            continue
        da, db_, dc = durations(x, sr)
        r = dict(uid=uid, pid=pid, w=w, dur=round(len(x) / sr, 3), text=S[uid]["text"])
        for k, v in (("A", da), ("B", db_), ("C", dc)):
            r["eff_" + k] = round(v, 3)
            r["rate_" + k] = round(w / v * 60, 1) if v > 0.4 else None
        rows.append(r)

    if not rows:
        print("✗ %s 下没有找到与 %s 匹配的单元" % (a.units, a.para))
        return 2

    if not a.quiet:
        print("=== %s 接缝语速闸门（voiced 口径，阈值 %.1f×）===" % (a.ch, a.thr))
        print("单元 %d 个（>=3 词），其中纯单段语音 %d 个"
              % (len(rows),
                 sum(1 for r in rows if r["eff_B"] and r["eff_C"] / r["eff_B"] > 0.98)))

    res = {}
    for k in "CBA":
        seams, bad, ngroup = build(rows, k, a.thr)
        res[k] = (seams, bad, ngroup)

    seams, bad, ngroup = res["C"]
    rdr = len({s["pid"] for s in bad}) / max(1, ngroup)
    r = np.array([s["ratio"] for s in seams]) if seams else np.array([1.0])

    if not a.quiet:
        print()
        print("%-4s %-22s %6s %6s %6s %8s" % ("口径", "含义", "接缝", "超标", "组数", "RDR"))
        for k, desc in (("C", "VAD voiced（主用）"), ("B", "VAD 首尾（原文）"),
                        ("A", "常数扣减 0.25s")):
            s2, b2, g2 = res[k]
            print("%-4s %-22s %6d %6d %6d %8.3f"
                  % (k, desc, len(s2), len(b2), g2,
                     len({x["pid"] for x in b2}) / max(1, g2)))
        print()
        print("主口径 C：p50 %.2f  p90 %.2f  max %.2f  超 %.1f× 的比例 %.0f%%"
              % (np.median(r), np.percentile(r, 90), r.max(), a.thr,
                 100 * (r > a.thr).mean()))
        print("对照：马修母带同口径 超 %.1f× = 9%%（≥3 词）/ 0%%（≥10 词）" % a.thr)
        if bad:
            print()
            print("超标接缝（按倍数降序）：")
            for s in sorted(bad, key=lambda s: -s["ratio"]):
                txt = next(x["text"] for x in rows if x["uid"] == s["culprit"])
                print("  段%-4d %s(%3.0f)→%s(%3.0f)  %.2f×   %s  [%s]"
                      % (s["pid"], s["a"], s["rate_a"], s["b"], s["rate_b"],
                         s["ratio"], s["culprit"], txt[:44]))

    verdict = "PASS" if rdr <= a.max_rdr else "FAIL"
    print()
    print("%s  RDR %.3f（准入线 %.2f）" % (verdict, rdr, a.max_rdr))

    out = a.out or ("_rdr_gate_%s.json" % a.ch)
    json.dump(dict(ch=a.ch, stage=a.stage, threshold=a.thr, max_rdr=a.max_rdr,
                   verdict=verdict, primary="C",
                   ngroup=ngroup, nseam=len(seams), nbad=len(bad), rdr=rdr,
                   p50=float(np.median(r)), p90=float(np.percentile(r, 90)),
                   seams=seams, rows=rows,
                   culprits=sorted({s["culprit"] for s in bad}),
                   rdr_by_method={k: len({s["pid"] for s in res[k][1]}) / max(1, res[k][2])
                                  for k in "CBA"}),
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已写 %s" % out)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
