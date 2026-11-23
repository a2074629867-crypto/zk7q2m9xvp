# -*- coding: utf-8 -*-
"""wlevel_probe.py —— 词级声学属性探针（POC-A）。

目的：给 take 建一张**逐词**属性表，用来
  ① 两个 take 之间挑更好的（逐词比，不比整条）
  ② 筛出「韵律没读到 / 词塔平 / 吞字」的 take

引擎口径（2026-11-12 改）：
  ASR **Parakeet TDT v3 int8**（本项目的标准 ASR，不是 whisper）→ 每词 t0/t1/置信度
  parselmouth → 该词窗内 F0（半音）与能量
  两个环境靠 json 交接：ASR 在 asr_venv（有 onnx_asr）、F0 在本环境（有 parselmouth）。

用法：
  G:/Python310/python.exe wlevel_probe.py --limit 12
  G:/Python310/python.exe wlevel_probe.py --ids c1_0001,c1_0002 --out _wl_probe2.csv
  G:/Python310/python.exe wlevel_probe.py --limit 60 --asr-refresh   # 强制重跑 ASR

已知限制（RAG 2026-10-18）：Parakeet 时间戳 80ms 粒度，短词窗只几帧 F0，
  下游必须用 n_fr >= 5 过滤；不要把 n_fr 少的词当「塔平」证据。
"""
import argparse
import csv
import difflib
import json
import os
import re
import statistics as st
import subprocess

import numpy as np
import parselmouth

os.environ.setdefault("OMP_NUM_THREADS", "2")

ROOT = "G:/_setup"
PLAN = os.path.join(ROOT, "_castle_en_ch123_plan.jsonl")
AUD = os.path.join(ROOT, "_audio_ch123", "out")
ASR_PY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")
ASR_SCRIPT = os.path.join(ROOT, "_wl_asr.py")


def norm_words(s):
    s = s.replace("\u2019", "'").replace("\u2018", "'").lower()
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return [w for w in s.split() if w]


def load_plan(limit=0):
    rows = [json.loads(l) for l in open(PLAN, encoding="utf-8") if l.strip()]
    if limit:
        rows = rows[:limit]
    return rows


def run_asr(paths, out_json, refresh=False):
    """调 asr_venv 把 wav 转成词级 json（Parakeet），返回 dict。"""
    if refresh and os.path.exists(out_json):
        os.remove(out_json)
    need = True
    if os.path.exists(out_json):
        old = json.load(open(out_json, encoding="utf-8"))
        need = any(p not in old for p in paths)
    if need:
        lst = out_json + ".list"
        with open(lst, "w", encoding="utf-8") as f:
            f.write("\n".join(paths) + "\n")
        cmd = [ASR_PY, ASR_SCRIPT, "--list", lst, "--out", out_json, "--append"]
        print("[ASR] %s" % " ".join(cmd[:2]))
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            raise SystemExit("ASR 失败 rc=%d" % r.returncode)
    return json.load(open(out_json, encoding="utf-8"))


def align(expected, got):
    """把 ASR 词序列比对回原文词序列，返回 got 下标 -> 原文下标。"""
    sm = difflib.SequenceMatcher(a=expected, b=got, autojunk=False)
    out = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            out[blk.b + k] = blk.a + k
    return out


def measure(wav, words, expected):
    """words: [{"w","start","end","p"}]，已经剔了标点。"""
    s = parselmouth.Sound(wav)
    dur = float(s.duration)
    pitch = s.to_pitch_ac(pitch_floor=75.0, pitch_ceiling=400.0,
                          time_step=0.01, silence_threshold=0.03, octave_cost=0.01,
                          very_accurate=True)
    f0 = pitch.selected_array["frequency"]
    pt = pitch.xs()
    inten = s.to_intensity(minimum_pitch=75.0, time_step=0.01)
    iv = inten.values[0]
    it = inten.xs()

    voiced = f0 > 0
    if voiced.sum() < 5:
        return None, None
    base = float(np.median(f0[voiced]))

    rows = []
    n = len(words)
    for i, w in enumerate(words):
        t0, t1 = float(w["start"]), float(w["end"])
        if t1 - t0 < 0.02:
            t1 = t0 + 0.02
        # F0 窗：80ms 粒度下短词帧太少，向词间空隙各借 20ms（不越邻词边界）
        lo, hi = t0 - 0.02, t1 + 0.02
        if i > 0:
            lo = max(lo, float(words[i - 1]["end"]))
        if i < n - 1:
            hi = min(hi, float(words[i + 1]["start"]))
        lo, hi = max(0.0, lo), min(dur, max(hi, t1))

        m = (pt >= lo) & (pt < hi) & voiced
        mi = (it >= t0) & (it < t1)
        f = f0[m]
        e = iv[mi]
        e = e[np.isfinite(e)]
        if len(f) >= 3:
            sst = 12.0 * np.log2(f / base)
            slope = float(np.polyfit(pt[m] - t0, sst, 1)[0]) if len(f) >= 5 else 0.0
            f0_mean = float(np.mean(f))
            f0_std = float(np.std(sst))
            f0_range = float(np.percentile(sst, 95) - np.percentile(sst, 5))
        else:
            slope = f0_mean = f0_std = f0_range = None
        rows.append(dict(
            w=w["w"], t0=round(t0, 3), t1=round(t1, 3), dur=round(t1 - t0, 3),
            n_fr=int(m.sum()),
            f0_mean=None if f0_mean is None else round(f0_mean, 1),
            f0_std_st=None if f0_std is None else round(f0_std, 2),
            f0_range_st=None if f0_range is None else round(f0_range, 2),
            f0_slope_st_s=None if slope is None else round(slope, 2),
            energy_db=round(float(np.mean(e)), 1) if len(e) else None,
            asr_prob=w.get("p"),
        ))

    # 词间空隙
    prev = 0.0
    for r in rows:
        r["gap_before"] = round(max(0.0, r["t0"] - prev), 3)
        prev = r["t1"]

    # take 级汇总
    fst = [r["f0_std_st"] for r in rows if r["f0_std_st"] is not None]
    erg = [r["energy_db"] for r in rows if r["energy_db"] is not None]
    pr = [r["asr_prob"] for r in rows if r["asr_prob"] is not None]
    agg = dict(
        audio_dur=round(dur, 2),
        n_word=len(rows),
        n_word_exp=len(expected),
        word_cov=round(len(rows) / max(1, len(expected)), 2),
        f0_med=round(base, 1),
        f0_std_med=round(st.median(fst), 2) if fst else None,
        energy_span=round(max(erg) - min(erg), 1) if len(erg) > 1 else None,
        prob_min=round(min(pr), 3) if pr else None,
        prob_mean=round(st.mean(pr), 3) if pr else None,
        n_low_prob=sum(1 for p in pr if p < 0.5),
    )
    return rows, agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "_wl_probe.csv"))
    ap.add_argument("--asr-json", default=os.path.join(ROOT, "_wl_words.json"))
    ap.add_argument("--asr-refresh", action="store_true", help="忽略缓存重新转写")
    ap.add_argument("--shard", default="0/1", help="i/n，只跑第 i 片")
    a = ap.parse_args()

    plan = load_plan(a.limit)
    si, sn = [int(x) for x in a.shard.split("/")]
    if sn > 1:
        plan = [r for k, r in enumerate(plan) if k % sn == si]
    if a.ids:
        want = set(a.ids.split(","))
        plan = [r for r in plan if r["id"] in want]

    wavs = []
    for rec in plan:
        p = os.path.join(AUD, rec["id"] + ".wav").replace("\\", "/")
        if os.path.exists(p):
            wavs.append(p)
    miss = len(plan) - len(wavs)
    if not wavs:
        raise SystemExit("没有音频")
    words_by_wav = run_asr(wavs, a.asr_json, a.asr_refresh)

    words_out, takes_out = [], []
    for k, rec in enumerate(plan, 1):
        wav = os.path.join(AUD, rec["id"] + ".wav").replace("\\", "/")
        if wav not in words_by_wav:
            continue
        exp = norm_words(rec["text"])
        items = [w for w in words_by_wav[wav]["words"]
                 if re.search(r"[A-Za-z0-9]", w["w"])]   # 剔标点 token
        if not items:
            # 空转写也是一条结论：要么短到不成立（截断件），要么电平低到无语音。
            # 不能直接跳过，否则 flags 层看不见这批，NO_TARGET 永远为 0。
            print("[EMPTY] %s ASR 无词（dur %.2fs）" % (rec["id"], words_by_wav[wav]["dur"]))
            takes_out.append(dict(
                tid=rec["id"], spk=rec["speaker"], conf=rec["conf"], rate=rec.get("rate", ""),
                audio_dur=words_by_wav[wav]["dur"], n_word=0, n_word_exp=len(exp), word_cov=0.0,
                n_extra=0, n_missing=len(exp), f0_med=None, f0_std_med=None, energy_span=None,
                prob_min=None, prob_mean=None, n_low_prob=0))
            continue
        got = [norm_words(w["w"])[0] if norm_words(w["w"]) else "?" for w in items]
        m = align(exp, got)
        rows, agg = measure(wav, items, exp)
        if rows is None:
            print("[ERR] %s 测不出" % rec["id"])
            continue
        for i, r in enumerate(rows):
            r["exp_w"] = exp[m[i]] if i in m else None   # None = ASR 多出来的词
            r["tid"] = rec["id"]
            r["spk"] = rec["speaker"]
            r["idx"] = i + 1
            words_out.append(r)
        agg.update(tid=rec["id"], spk=rec["speaker"], conf=rec["conf"],
                   rate=rec.get("rate", ""), n_extra=sum(1 for i in range(len(rows)) if i not in m),
                   n_missing=len(exp) - len(m))
        takes_out.append(agg)
        print("[%3d/%3d] %-9s %-9s w=%2d/%2d cov=%.2f f0std=%s esp=%s pmin=%s" % (
            k, len(plan), rec["id"], rec["speaker"], agg["n_word"], agg["n_word_exp"],
            agg["word_cov"], agg["f0_std_med"], agg["energy_span"], agg["prob_min"]))

    fld = ["tid", "spk", "idx", "w", "exp_w", "t0", "t1", "dur", "gap_before", "n_fr",
           "f0_mean", "f0_std_st", "f0_range_st", "f0_slope_st_s", "energy_db", "asr_prob"]
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fld, extrasaction="ignore")
        w.writeheader()
        w.writerows(words_out)
    tout = a.out.replace(".csv", "_takes.csv")
    fld2 = ["tid", "spk", "conf", "rate", "audio_dur", "n_word", "n_word_exp", "word_cov",
            "n_extra", "n_missing", "f0_med", "f0_std_med", "energy_span", "prob_min",
            "prob_mean", "n_low_prob"]
    with open(tout, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fld2, extrasaction="ignore")
        w.writeheader()
        w.writerows(takes_out)
    print("\n词表 %d 行 -> %s" % (len(words_out), a.out))
    print("take 表 %d 行 -> %s   (缺音频 %d)" % (len(takes_out), tout, miss))


if __name__ == "__main__":
    main()
