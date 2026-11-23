# -*- coding: utf-8 -*-
"""极短句重建 v2：载体短语 + forced_align 定位切点。

为什么不用能量找静音（v1 失败）
------------------------------
v1 靠「第一个 ≥0.15s 静音」切，但模型念 "No. That's all." 时两句之间几乎没有停顿，
测不到静音 → 4 个后缀全报 no-silence。放宽阈值又会切在词中间。

现在改成：生成 "目标句 + 载体句"，用 forced_align 把 gold 文本强制对齐到音频上，
取**目标句最后一个词的结束帧**当切点。forced_align 不依赖 ASR 是否听清，
1 个词的短句也能给出边界（这正是 wav2vec2 相对 whisper 的优势）。

2026-11-22 实测过的坏例子（所以必须有载体）：
    'No'   不给参考文本 → 0.61s，ASR 听成 SERVS
    'It'   不给参考文本 → 4.14s，念成 "AS US SHE NASS E SRULY HEVER TELL MASHE"
    'Well' 不给参考文本 → 2.30s，念成 "WHAT NO"
逐字生成时模型没有句边界先验，会自由发挥；加一个短载体后才有稳定的句末锚点。

    _regen_short.py --ids c2_0263,c3_0631 --out _sweep/short2
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P

ROOT = P.ROOT
SR = 48000
FRAME_MS = 20

CARRIERS = ["That's all.", "I mean it."]


def norm24(y, sr):
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    n = 1 + (len(y) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(n)[:, None]
    fr = y[idx]
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-12)
    v = fr[db > db.max() - 40]
    lv = float(20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)) if len(v) else -99
    if lv < -80:
        return y, lv
    y = (y * 10 ** ((-24.0 - lv) / 20)).astype(np.float32)
    pk = float(np.abs(y).max())
    if pk > 0.95:
        y = (y * (0.95 / pk)).astype(np.float32)
    return y, lv


def strip_punct(t):
    import re
    t = (t or "").strip()
    for q in ("\u2018", "\u2019", "\u201c", "\u201d", '"', "'"):
        t = t.replace(q, "")
    return re.sub(r"[.\u3002\u2026]+$", "", t.strip()).strip()


def word_spans_from_tokens(tokens, chars):
    """把 forced_align 的字符级 spans 聚成词级。

    坑：to_tokens 用 '|' 表示空格（不是 ' '），而且 norm_text 把撇号也变成空格
    （THAT'S → THAT S）。所以词数要按 norm_text 后的空格数算，不能按原文本 split。
    """
    out, cur, ci = [], [], 0
    for ch in chars:
        if ch == "|":
            if cur:
                out.append(cur)
                cur = []
            continue
        if ci < len(tokens):
            cur.append(tokens[ci])
            ci += 1
    if cur:
        out.append(cur)
    return [{"start": g[0]["start"], "end": g[-1]["end"]} for g in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "_sweep", "short2"))
    ap.add_argument("--threads", type=int, default=P.ACPP_THREADS)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    import _regen9 as R9
    import _align_gate as AG
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

    plan = {p["id"]: p for p in R9.load_plan()}
    idx = json.load(open(R9.IDX, encoding="utf-8"))
    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    os.makedirs(a.out, exist_ok=True)
    raw = os.path.join(a.out, "_raw")
    os.makedirs(raw, exist_ok=True)

    print("加载 wav2vec2 ...", flush=True)
    name = "facebook/wav2vec2-base-960h"
    proc = Wav2Vec2Processor.from_pretrained(name)
    model = Wav2Vec2ForCTC.from_pretrained(name).eval()

    rep = []
    for n, rid in enumerate(ids, 1):
        row = plan[rid]
        ref, _rt = R9.ref_for(R9.group_of(row.get("voice")), idx)
        base = strip_punct(row["text"])
        got = False
        for ci, car in enumerate(CARRIERS):
            gen_text = base + " " + car
            # 载体本身也要规范化后再数词，否则 "That's" 的撇号会让目标词数算错
            tmp = os.path.join(raw, "%s__c%d.wav" % (rid, ci))
            if not (os.path.exists(tmp) and os.path.getsize(tmp) > 50000):
                mtok = max(120, min(900, int(len(gen_text.split()) * 12 + 120)))
                cmd = [R9.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R9.MODEL,
                       "--backend", P.ACPP_BACKEND, "--threads", str(a.threads),
                       "--voice-ref", ref, "--reference-text", "",
                       "--text", gen_text, "--seed", str(a.seed), "--out", tmp,
                       "--request-option", "max_tokens=%d" % mtok]
                cmd += P.mem_saver_args() + ["--metrics"]
                subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=R9.ACPP_DIR, timeout=1800)
            if not (os.path.exists(tmp) and os.path.getsize(tmp) > 50000):
                rep.append((rid, "gen FAIL c%d" % ci, 0))
                continue
            r = AG.align(proc, model, tmp, gen_text)
            if not r:
                rep.append((rid, "align FAIL c%d" % ci, 0))
                continue
            chars, _ = AG.to_tokens(proc, gen_text)
            ws = word_spans_from_tokens(r["tokens"], chars)
            nword = len(AG.norm_text(base).split())
            if len(ws) < nword:
                rep.append((rid, "span短 %d<%d c%d" % (len(ws), nword, ci), 0))
                continue
            cut = (ws[nword - 1]["end"] * FRAME_MS / 1000.0) + 0.10
            y, sr = sf.read(tmp, dtype="float64")
            if y.ndim > 1:
                y = y.mean(1)
            seg = y[:int(min(cut, len(y) / sr) * sr)]
            fl, hop = int(0.025 * sr), int(0.01 * sr)
            nn = 1 + (len(seg) - fl) // hop
            ixx = np.arange(fl)[None, :] + hop * np.arange(nn)[:, None]
            db = 20 * np.log10(np.sqrt((seg[ixx] ** 2).mean(1)) + 1e-12)
            v = np.where(db > db.max() - 40)[0]
            if len(v):
                seg = seg[max(0, int(v[0] * hop - 0.02 * sr)):]
            dur = len(seg) / sr
            if not (0.18 <= dur <= 1.6):
                rep.append((rid, "dur %.2fs c%d「%s」" % (dur, ci, car), dur))
                continue
            seg, lv = norm24(seg.astype(np.float32), sr)
            k = int(0.010 * sr)
            if len(seg) > 2 * k:
                seg[:k] *= np.linspace(0, 1, k, dtype=np.float32)
                seg[-k:] *= np.linspace(1, 0, k, dtype=np.float32)
            out = os.path.join(a.out, "%s__s42.wav" % rid)
            sf.write(out, seg, sr, subtype="PCM_16")
            rep.append((rid, "OK 「%s」" % gen_text, dur))
            got = True
            break
        if not got:
            print("[%d/%d] %s 全败" % (n, len(ids), rid), flush=True)

    print("\n%-9s %-40s %6s" % ("id", "结果", "dur"))
    for rid, msg, dur in rep:
        print("%-9s %-40s %6.2f" % (rid, msg, dur))
    print("\nOK %d / %d" % (sum(1 for r in rep if r[1].startswith("OK")), len(ids)))


if __name__ == "__main__":
    main()
