# -*- coding: utf-8 -*-
"""mt_chapter_join.py —— 把逐单元音频拼成整章（旁白轨）。

    python mt_chapter_join.py --dir _mt_smooth_ch1 --ch ch1 --out _chap_ch1_smooth.wav
    python mt_chapter_join.py --dir _mt_raw_s42   --ch ch1 --out _chap_ch1_raw.wav

做四件事：
  1. 按单元编号排序（N0001 → N0183）
  2. 逐条电平归一到 voiced RMS −24 dBFS（各条生成电平不同，不归一拼接会一会儿大一会儿小）
  3. 单元间按**末尾标点**插停顿：. ? ! → clause 1.695s / , ; : – → bound 1.135s / 无标点 → 0.35s
  4. 整章叠加合成底噪 −56 dBFS（真人实测中位；不是 −58）

★ 为什么单元间停顿按标点而不按 LLM：单元切分是「旁白片段」，末尾标点就是真实断点。
  castle ch1 有 33 个单元以逗号结尾（半句），这些必须用 bound 而不是 clause，
  否则整章听起来处处是句末。

★ 为什么电平归一必须逐条：_mt_raw_s42 的 voiced RMS 跨 20dB 以上，直接拼会忽大忽小。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, "G:/_setup")
import numpy as np
import soundfile as sf

import mt_final_pause as FP

TARGET_DB = -24.0
BED_DB = -56.0
GAP = {"clause": 1.695, "bound": 1.135, "none": 0.35}


def _gap_of(text):
    t = (text or "").rstrip()
    if not t:
        return GAP["none"], "none"
    c = t[-1]
    if c in ".?!":
        return GAP["clause"], "clause"
    if c in ",;:\u2013\u2014-":
        return GAP["bound"], "bound"
    return GAP["none"], "none"


def level_norm(x, sr, target_db=TARGET_DB):
    """把 voiced 段的 RMS 归一到 target_db。判据同 ch123_clean：只在语音帧上算。"""
    db, nfl, hop = FP.frame_db(x, sr)
    if len(db) == 0:
        return x, 0.0
    thr = np.percentile(db, 90) - 25.0
    mask = db > thr
    if mask.sum() < 3:
        return x, 0.0
    idx = np.where(mask)[0]
    seg = []
    for i in idx:
        a = i * hop
        b = min(len(x), a + hop)
        if b > a:
            seg.append(x[a:b])
    if not seg:
        return x, 0.0
    y = np.concatenate(seg).astype(np.float64)
    rms = float(np.sqrt((y ** 2).mean()) + 1e-12)
    cur = 20 * np.log10(rms)
    g = 10 ** ((target_db - cur) / 20.0)
    return (x * g).astype(np.float32), round(target_db - cur, 2)


def level_norm_capped(x, sr, target_db, max_gain=6.0, max_cut=3.0, peak_cap=0.95):
    """同上，但增益夹在 [-max_cut, +max_gain]，并按峰值上限回退，避免削波。

    ★ 只有尾部（轻声短句）会吃到 +gain；主体 p10~p90 本来就在 2.4dB 内，几乎不动。
    """
    db, _, hop = FP.frame_db(x, sr)
    if len(db) == 0:
        return x, 0.0
    thr = np.percentile(db, 90) - 25.0
    mask = db > thr
    if mask.sum() < 3:
        return x, 0.0
    seg = [x[i * hop:min(len(x), i * hop + hop)] for i in np.where(mask)[0]]
    y = np.concatenate(seg).astype(np.float64)
    cur = 20 * np.log10(float(np.sqrt((y ** 2).mean()) + 1e-12))
    gdb = float(np.clip(target_db - cur, -max_cut, max_gain))
    peak = float(np.abs(x).max()) + 1e-12
    if peak * 10 ** (gdb / 20.0) > peak_cap:
        gdb = 20 * np.log10(peak_cap / peak)
    return (x * 10 ** (gdb / 20.0)).astype(np.float32), round(gdb, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bed-db", type=float, default=BED_DB)
    ap.add_argument("--no-bed", action="store_true")
    ap.add_argument("--no-norm", action="store_true",
                    help="输入已做过电平归一（如 mt_final_pause 的产物）时用")
    ap.add_argument("--norm-target", type=float, default=None,
                    help="逐条归一到该 voiced RMS（dBFS），带增益夹与峰值保护")
    ap.add_argument("--norm-max-gain", type=float, default=6.0)
    ap.add_argument("--norm-max-cut", type=float, default=3.0)
    ap.add_argument("--gap-bed", action="store_true",
                    help="间隔填底噪而非数字零（配合 --no-bed 用，避免二次叠加底噪）")
    ap.add_argument("--gap-para", type=float, default=None, help="段末停顿（秒）")
    ap.add_argument("--gap-clause", type=float, default=None, help="段内句号停顿（秒）")
    ap.add_argument("--gap-bound", type=float, default=None, help="逗号/分号停顿（秒）")
    ap.add_argument("--gap-none", type=float, default=None, help="无标点停顿（秒）")
    ap.add_argument("--para-map", help="_ch1_unit_para.json，用于判定段末")
    ap.add_argument("--json")
    a = ap.parse_args()

    if a.gap_para is not None:
        GAP["para"] = a.gap_para
    if a.gap_clause is not None:
        GAP["clause"] = a.gap_clause
    if a.gap_bound is not None:
        GAP["bound"] = a.gap_bound
    if a.gap_none is not None:
        GAP["none"] = a.gap_none
    PARA_END = set()
    if a.para_map:
        for r in json.load(open(a.para_map, encoding="utf-8")):
            if r.get("para_end"):
                PARA_END.add(r["uid"])

    S = json.load(open("G:/_setup/_mt_loop_state.json", encoding="utf-8"))["units"]
    units = sorted([(n, u) for n, u in S.items() if u["ch"] == a.ch])
    if not units:
        sys.exit("没有 %s 的单元" % a.ch)

    parts, rows, sr0 = [], [], None
    missing = []
    n_units = len(units)
    for ui, (n, u) in enumerate(units):
        p = os.path.join(a.dir, n + ".wav")
        if not os.path.exists(p):
            missing.append(n)
            continue
        x, sr = sf.read(p, dtype="float32", always_2d=True)
        x = x.mean(1)
        if sr0 is None:
            sr0 = sr
        elif sr != sr0:
            sys.exit("采样率不一致：%s 是 %d，前面是 %d" % (n, sr, sr0))
        if a.no_norm:
            x, dg = x, 0.0
        elif a.norm_target is not None:
            x, dg = level_norm_capped(x, sr, a.norm_target,
                                      a.norm_max_gain, a.norm_max_cut)
        else:
            x, dg = level_norm(x, sr)
        g, kind = _gap_of(u["text"])
        # 段末（原书段落边界）用更长的一档；只对句号类生效
        if kind == "clause" and n in PARA_END and "para" in GAP:
            g, kind = GAP["para"], "para"
        parts.append(x)
        # 最后一条不加间隔，避免整章尾部挂一段静音
        if ui < n_units - 1:
            ns = int(round(g * sr))
            if a.gap_bed:
                parts.append(FP.synth_bed(ns, sr, None, a.bed_db,
                                          np.random.default_rng(ui + 7)))
            else:
                parts.append(np.zeros(ns, dtype=np.float32))
        rows.append({"uid": n, "dur": round(len(x) / sr, 3), "gain_db": dg,
                     "gap": g, "gap_kind": kind, "tail": u["text"][-24:]})

    if not parts:
        sys.exit("一条都没读到")

    y = np.concatenate(parts)
    if not a.no_bed:
        rng = np.random.default_rng(20261030)
        bed = FP.synth_bed(len(y), sr0, None, a.bed_db, rng)
        y = y + bed
    peak = float(np.abs(y).max())
    if peak > 0.999:
        y = y * (0.999 / peak)
        clipped = True
    else:
        clipped = False
    sf.write(a.out, y.astype(np.float32), sr0)

    tot = len(y) / sr0
    gap_sum = sum(r["gap"] for r in rows)
    print("=== %s / %s ===" % (a.ch, os.path.basename(a.dir)))
    print("  单元 %d（缺 %d）  总时长 %.1f s = %.1f 分" % (len(rows), len(missing), tot, tot / 60))
    print("  停顿合计 %.1f s（%.0f%%）" % (gap_sum, 100 * gap_sum / tot))
    from collections import Counter
    print("  间隔档位 " + "  ".join("%s %d" % (k, v) for k, v in
                                   sorted(Counter(r["gap_kind"] for r in rows).items())))
    gs = [r["gain_db"] for r in rows if r["gain_db"]]
    if gs:
        print("  电平增益 %.1f ~ %.1f dB（中位 %.1f）—— 跨度 %.1f dB"
              % (min(gs), max(gs), float(np.median(gs)), max(gs) - min(gs)))
    print("  峰值 %.3f%s" % (float(np.abs(y).max()), "（已整体回退）" if clipped else ""))
    if missing:
        print("  缺文件：%s" % ",".join(missing[:10]))
    print("  → %s" % a.out)
    if a.json:
        json.dump({"ch": a.ch, "dir": a.dir, "out": a.out, "dur": tot,
                   "rows": rows, "missing": missing},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
