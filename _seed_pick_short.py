# -*- coding: utf-8 -*-
"""_seed_pick_short.py —— 极短句（≤3 词）的省略号延长：载体短语 + seed 择优。

为什么极短句不能直接 seed 择优
  实测 `No. But...`（2 词）基线 1.07s / 2 个发声段，seed 42 生成 5.60s / **7 个发声段**
  （开头还有 −240 数字零）；`It...`（1 词）seed 45 生成 7.04s。逐字生成时模型没有句边界
  先验，会自由发挥 —— 这正是 `_regen_short.py` 当初加载体的原因（2026-11-22 记录：
  'It' 不给参考文本会念成 "AS US SHE NASS E SRULLY..."）。

做法
  gen_text = 目标句 + " That's all."  →  forced_align 把 gold 对齐到音频
  →  取目标句最后一词的 end 帧 + 0.10s 当切点  →  切出  →  量目标词发声时长
  →  换 seed 重复，挑「目标词自然更长」的那个 take（零后处理，模型自己生成的）

判据
  词数对齐 / 切出时长 0.18~1.6s / 目标词 ratio ≥1.5（<1.5 听不出延长）/ 发声段数 ≤ 词数+2
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import _align_gate as AG          # noqa: E402
import _paths as P                # noqa: E402
import _regen_short as RS         # noqa: E402
from _seed_pick_batch import (clean, norm_words, voiced_len, n_voiced_segs,   # noqa: E402
                              resolve_ref, f0_med)

OUT = "G:/_setup/_seedpick_short"
CARRIER = "That's all."


def gen(text, ref, out, seed):
    n = len(text.split())
    mtok = max(200, min(900, int(n * 12 + 120) + 150))
    cmd = [P.ACPP, "--task", "tts", "--family", "dots_tts", "--model", P.MODEL,
           "--backend", P.ACPP_BACKEND, "--threads", str(P.ACPP_THREADS),
           "--voice-ref", ref, "--reference-text", "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % mtok]
    cmd += P.mem_saver_args()
    r = subprocess.run(cmd, cwd=P.ACPP_DIR, capture_output=True, text=True, timeout=1800)
    return r.returncode


def cut_target(path, gen_text, base, proc, model):
    """切出目标句，返回 (y, sr, 目标词发声ms, 目标词start秒, 词数)。"""
    r = AG.align(proc, model, path, gen_text)
    if not r:
        return None
    chars, _ = AG.to_tokens(proc, gen_text)
    ws = RS.word_spans_from_tokens(r["tokens"], chars)
    nword = len(norm_words(base))
    if len(ws) < nword:
        return None
    cut = (ws[nword - 1]["end"] * RS.FRAME_MS / 1000.0) + 0.10
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    seg = y[:int(min(cut, len(y) / sr) * sr)]
    # 去掉开头静音
    fl, hop = int(0.025 * sr), int(0.01 * sr)
    nn = 1 + (len(seg) - fl) // hop
    idx = np.arange(fl)[None, :] + hop * np.arange(nn)[:, None]
    db = 20 * np.log10(np.sqrt((seg[idx] ** 2).mean(1)) + 1e-12)
    v = np.where(db > db.max() - 40)[0]
    a0 = max(0, int(v[0] * hop - 0.02 * sr)) if len(v) else 0
    seg = seg[a0:]
    t_start = (ws[nword - 1]["start"] * RS.FRAME_MS / 1000.0) - a0 / sr
    tv = voiced_len(seg, sr, max(0.0, t_start))
    return seg, sr, tv, t_start, len(ws)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--seeds", default="42,43,44,45,46")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    items = json.load(open("G:/_setup/_elong_targets.json", encoding="utf-8"))
    short_ids = [x.strip() for x in open("G:/_setup/_elong_short_ids.txt",
                                         encoding="utf-8") if x.strip()]
    items = [x for x in items if x["id"] in short_ids]
    if a.ids:
        want = {x.strip() for x in a.ids.split(",") if x.strip()}
        items = [x for x in items if x["id"] in want]
    seeds = [x.strip() for x in a.seeds.split(",") if x.strip()]

    print("加载 wav2vec2 ...", flush=True)
    proc, model = AG.load_model()

    out_rows = []
    for it in items:
        rid = it["id"]
        rows = json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))
        text = clean(next(r["text"] for r in rows if r["id"] == rid))
        base = RS.strip_punct(text)                     # 去尾部省略号/句号
        gen_text = base + " " + CARRIER
        nw = len(norm_words(base))
        ref = resolve_ref(it.get("voice", ""))
        d = os.path.join(OUT, rid)
        os.makedirs(d, exist_ok=True)
        print("\n=== %s  v=%s  base=%r  词数%d" % (rid, it.get("voice"), base, nw))

        b = "G:/_setup/_audio_ch123/out/%s.wav" % rid
        b_t = b_dur = None
        if os.path.exists(b):
            y0, sr0 = sf.read(b, dtype="float64")
            if y0.ndim > 1:
                y0 = y0.mean(1)
            b_dur = len(y0) / sr0
            r0 = AG.align(proc, model, b, text)
            if r0:
                w0 = RS.word_spans_from_tokens(r0["tokens"], AG.to_tokens(proc, text)[0])
                if len(w0) >= nw:
                    b_t = voiced_len(y0, sr0, w0[nw - 1]["start"] * 0.02)
            print("  基线 %s=%.0fms  总%.2fs  段%d" % (
                it["word"], b_t or 0, b_dur, n_voiced_segs(b)))

        res = []
        for sd in seeds:
            p = os.path.join(d, "s%s.wav" % sd)
            if not (os.path.exists(p) and os.path.getsize(p) > 10000):
                if gen(gen_text, ref, p, int(sd)) != 0 or not os.path.exists(p):
                    print("  seed %-3s 生成失败" % sd)
                    continue
            got = cut_target(p, gen_text, base, proc, model)
            if not got:
                print("  seed %-3s 对齐/切段失败" % sd)
                continue
            seg, sr, tv, _, nws = got
            dur = len(seg) / sr
            r = dict(seed=int(sd), tv=round(tv), cut_dur=round(dur, 2), nword=nws,
                     f0=f0_med(p))
            bad = []
            if not (0.18 <= dur <= 1.6):
                bad.append("切出%.2fs" % dur)
            if b_t and tv / b_t < 1.5:
                bad.append("%.1fx" % (tv / b_t))
            r["ratio"] = round(tv / b_t, 2) if b_t else None
            r["ok"] = not bad
            r["why"] = ",".join(bad)
            res.append(r)
            print("  seed %-3s %s=%.0fms(%sx) 切出%.2fs 段%d F0 %d  %s" % (
                sd, it["word"], tv, ("%.1f" % r["ratio"]) if r["ratio"] else "-",
                dur, n_voiced_segs(p), r["f0"], "OK" if r["ok"] else "✗ " + r["why"]))

        okr = [r for r in res if r["ok"]]
        pick = None
        if okr:
            pick = max(okr, key=lambda r: r["tv"])
            # 落盘：切段 + norm24 + 10ms 淡入淡出 + PCM_24
            got = cut_target(os.path.join(d, "s%s.wav" % pick["seed"]), gen_text, base,
                             proc, model)
            seg, sr = got[0], got[1]
            seg, _lv = RS.norm24(seg.astype(np.float32), sr)
            k = int(0.010 * sr)
            if len(seg) > 2 * k:
                seg[:k] *= np.linspace(0, 1, k, dtype=np.float32)
                seg[-k:] *= np.linspace(1, 0, k, dtype=np.float32)
            sf.write(os.path.join(OUT, "%s.wav" % rid), seg, sr, subtype="PCM_24")
            print("  → 选 seed %s  %s=%.0fms (%.1fx)" % (
                pick["seed"], it["word"], pick["tv"], pick["ratio"] or 0))
        else:
            print("  → 全部被拦（极短句载体法+seed 也没找到自然长音）")
        out_rows.append(dict(id=rid, voice=it.get("voice"), word=it["word"], base_text=base,
                             base=round(b_t) if b_t else None,
                             base_dur=round(b_dur, 2) if b_dur else None,
                             seeds=res, pick=pick["seed"] if pick else None,
                             pick_tv=round(pick["tv"]) if pick else None,
                             pick_ratio=pick["ratio"] if pick else None))
        json.dump(out_rows, open(os.path.join(OUT, "_summary_short.json"), "w",
                                 encoding="utf-8"), ensure_ascii=False, indent=1)

    print("\n===== 极短句汇总 =====")
    for r in out_rows:
        print("%-9s base=%s pick=%s %sms ratio=%s" % (
            r["id"], r["base"], r["pick"], r["pick_tv"], r["pick_ratio"]))
    print("-> %s/_summary_short.json" % OUT)


if __name__ == "__main__":
    main()
