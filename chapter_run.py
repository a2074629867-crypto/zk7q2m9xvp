# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dots_markup as MK
"""chapter_run.py —— 整章生成流水线（dots.tts / acpp Vulkan）

流程（每块）：
  1) 文本场景分析 → 决定这一块的 <rate>（基准 0.80，按场景 ±0.08）
  2) 生成（整块只挂一个 <rate> span —— 实测唯一不丢词的写法）
  3) 停顿移植（真人静音素材，间隙夹在 0.85~1.70s）
最后按顺序拼接，块间插入 1.6s 真人静音。

用法：
  python chapter_run.py --text G:/_setup/chapter1/chapter1_narration.txt \
      --out-dir G:/_setup/chapter1/audio [--limit N] [--chunk-words 120]
"""
import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ACPP = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
EXE = os.path.join(ACPP, "audiocpp_cli.exe")
MODEL = r"E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = r"G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
DONOR = r"E:/tts-models/acpp/out/calmdeep_final/real_trim.wav"
SR = 48000

# 场景词典：关键词 -> (rate 增量, 停顿倍率, 标签)
SCENES = {
    "sleep": (["sleep", "sleeps", "doze", "drifting off", "dream", "dreams", "eyelids",
               "pillow", "blanket", "cozy", "warmth", "breath", "tucked"], -0.030, 1.12),
    "calm": (["quiet", "peaceful", "stillness", "silence", "calming", "gentle", "soft",
              "tender", "hush", "serene", "tranquil", "soothing", "delicate"], -0.025, 1.10),
    "awe": (["universe", "galaxy", "galaxies", "cosmos", "cosmic", "solar system", "planet",
             "light years", "billion", "magnificent", "miraculous", "splendor",
             "breathtaking", "wondrous", "marvelous"], -0.020, 1.08),
    "night": (["night", "starlight", "stars", "moon", "darkness", "glow", "shimmer",
               "twinkling", "sky", "constellations"], -0.015, 1.06),
    "water": (["lake", "water", "waves", "rippling", "streams", "oceans", "rivers",
               "tides", "sea", "shore", "waterfall", "springs"], -0.010, 1.04),
    "energy": (["streaked", "soared", "danced", "fireworks", "flurry", "rushing",
                "racing", "swept", "burst", "plunged", "flamingos", "dolphins"], 0.040, 0.94),
    "facts": (["miles", "per second", "percent", "thousand", "million", "solar system",
               "sixteen", "year old", "degrees"], 0.000, 1.03),
}

BASE_RATE = 0.80
RATE_MIN, RATE_MAX = 0.78, 0.84


def split_sents(t):
    return re.split(r"(?<=[.!?])\s+", t.strip())


def chunk_sents(sents, target=120, hard_max=165):
    out, cur, n = [], [], 0
    for s in sents:
        w = len(s.split())
        if cur and n + w > hard_max:
            out.append(" ".join(cur)); cur, n = [], 0
        cur.append(s); n += w
        if n >= target:
            out.append(" ".join(cur)); cur, n = [], 0
    if cur:
        out.append(" ".join(cur))
    return out


def profile(chunk):
    """场景 → rate。取「最强场景」的增量（不叠加），避免多场景把 rate 一路压到下限。"""
    low = chunk.lower()
    scores = []
    hits = []
    for name, (kws, dr, gs) in SCENES.items():
        c = sum(low.count(k) for k in kws)
        if c:
            hits.append("%s×%d" % (name, c))
            scores.append((min(c, 3) / 3.0 * abs(dr), dr, gs, name))
    rate, gscale = BASE_RATE, 1.0
    if scores:
        _, dr, gs, name = max(scores)
        rate += dr
        gscale = gs
    # 枚举/排比：短句占比高 → 略放慢、停顿略拉长
    sents = split_sents(chunk)
    shorts = sum(1 for s in sents if len(s.split()) <= 6)
    if len(sents) >= 3 and shorts / len(sents) >= 0.4:
        rate -= 0.010
        gscale *= 1.04
        hits.append("enum")
    rate = max(RATE_MIN, min(RATE_MAX, round(rate, 2)))
    return rate, round(gscale, 3), (", ".join(hits) or "neutral")


SPAN_LIMIT = 10   # 实测：9 span 不丢词（131/131），29 span 丢整句（130→101）

# ---- token 估算（实测锚点，不要拍）----
#   chapter1/audio/fix/c04.wav = 146 词 @ rate 0.78 → 71.0s，max_tokens 900 完整无截断
#   ⇒ 12.7 token/秒语音；rate=1.0 时语速 158 wpm
#   减速块 rate 越低，同样文本需要越多 token，固定 900 会在长块上截断。
TOK_PER_SEC = 12.7
WPM_AT_1 = 158.0


def mtok_for(words, rate, safety=1.08):
    dur = words / WPM_AT_1 * 60.0 / max(rate, 0.5)
    return int(-(-dur * TOK_PER_SEC * safety // 10) * 10)


def chunks_from_plan(sents, plan_ch):
    """按 LLM 减速方案（narr_rate_plan.json）切块并定 rate。

    rate 是硬约束，由 narr_slow_llm.py 校验过：
      - 0.72~0.84，0.70 实测会丢整句
      - 相邻段差 ≤0.06
      - 减速段词数 ≤20%
    """
    out = []
    for p in plan_ch.get("paras") or []:
        s0, s1 = int(p["s0"]), int(p["s1"])
        txt = " ".join(sents[s0:s1 + 1]).strip()
        if not txt:
            continue
        r = float(p.get("rate", BASE_RATE))
        w = len(txt.split())
        out.append(dict(text=txt, rate=r, gscale=1.0, why=str(p.get("why", "")),
                        mtok=mtok_for(w, r), words=w, s0=s0, s1=s1))
    return out



def merge_to_limit(sents, limit=SPAN_LIMIT):
    """把句子数压到 limit 以内：每次合并「词数之和最小」的相邻两句。
    只用于拆 rate span，不改文本内容（合并后标点仍保留在句中）。"""
    s = [x for x in sents if x.strip()]
    while len(s) > limit:
        best, bi = None, 0
        for k in range(len(s) - 1):
            w = len(s[k].split()) + len(s[k + 1].split())
            if best is None or w < best:
                best, bi = w, k
        s[bi:bi + 2] = [s[bi].rstrip() + " " + s[bi + 1].lstrip()]
    return s


def call_tts(text, out, seed=42, max_tokens=900):
    cmd = [EXE, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % max_tokens,
           "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, cwd=ACPP, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout or "").splitlines() if "audio_out" in l or "error" in l.lower()]
    return r.returncode, " | ".join(tail[-2:])


def transplant(gen, out, report, gmin=0.85, gmax=1.70):
    cmd = [r"G:/Python310/python.exe", r"G:/_setup/pause_donor_by_position.py",
           "--gen", gen, "--donor", DONOR, "--out", out, "--report", report,
           "--min-gap", "0.30", "--gap-min", str(gmin), "--gap-max", str(gmax)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "").strip().splitlines()[-1:] or [""]


def load(p):
    x, sr = sf.read(p, dtype="float64", always_2d=True)
    x = x.mean(1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = np.gcd(int(sr), SR)
        x = resample_poly(x, SR // g, sr // g)
    return x


def donor_gap(seconds):
    """从真人录音里取一段真实静音（最长间隙的居中片段），用来做块间停顿。"""
    d = load(DONOR)
    hop = int(SR * 0.010)
    n = len(d) // hop
    db = 20 * np.log10(np.sqrt((d[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12)
    m = db > (db.max() - 35.0)
    best, cur, bs = 0, 0, 0
    for i, v in enumerate(m):
        if not v:
            cur += 1
            if cur > best:
                best, bs = cur, i - cur + 1
        else:
            cur = 0
    seg = d[int(bs * 0.01 * SR): int((bs + best) * 0.01 * SR)]
    need = int(seconds * SR)
    if len(seg) < need:
        seg = np.tile(seg, int(np.ceil(need / max(1, len(seg)))))
    seg = seg[:need].copy()
    nf = int(0.01 * SR)
    seg[:nf] *= np.linspace(0, 1, nf)
    seg[-nf:] *= np.linspace(1, 0, nf)
    return seg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="G:/_setup/chapter1/chapter1_narration.txt")
    ap.add_argument("--out-dir", default="G:/_setup/chapter1/audio")
    ap.add_argument("--chunk-words", type=int, default=120)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 块（调试用）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rate-plan", default="G:/_setup/narr_rate_plan.json",
                    help="LLM 减速方案（narr_slow_llm.py 产出）；不存在则回退关键词场景")
    ap.add_argument("--no-rate-plan", action="store_true", help="强制回退 chunk_sents+profile")
    a = ap.parse_args()

    out = Path(a.out_dir)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "fix").mkdir(parents=True, exist_ok=True)

    text = Path(a.text).read_text(encoding="utf-8")
    sents = split_sents(text)

    plan_ch = {}
    if not a.no_rate_plan and os.path.exists(a.rate_plan):
        raw = json.load(open(a.rate_plan, encoding="utf-8"))
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            plan_ch = v
            break
        if plan_ch and int(plan_ch.get("paras", [{}])[-1].get("s1", -1)) + 1 != len(sents):
            print("[warn] rate-plan 覆盖 %d 句，但文本有 %d 句 —— 方案与文本不匹配，回退"
                  % (int(plan_ch.get("paras", [{}])[-1].get("s1", -1)) + 1, len(sents)),
                  flush=True)
            plan_ch = {}

    if plan_ch:
        recs = chunks_from_plan(sents, plan_ch)
        print("旁白 %d 词 → %d 段（LLM 减速方案 %s）"
              % (len(text.split()), len(recs), os.path.basename(a.rate_plan)), flush=True)
    else:
        chunks = chunk_sents(sents, target=a.chunk_words)
        recs = []
        for ch in chunks:
            r, gs, why = profile(ch)
            recs.append(dict(text=ch, rate=r, gscale=gs, why=why,
                             mtok=mtok_for(len(ch.split()), r), words=len(ch.split())))
        print("旁白 %d 词 → %d 块（关键词场景，目标 %d 词/块）"
              % (len(text.split()), len(recs), a.chunk_words), flush=True)

    if a.limit:
        recs = recs[: a.limit]

    meta = []
    t_all = time.time()
    for i, seg in enumerate(recs, 1):
        ch, rate, gs, why = seg["text"], seg["rate"], seg["gscale"], seg["why"]
        # ★ 实测（131 词 / tts 任务）：单 span 的 rate 兑现率仅 24%，
        #   按句拆 span 后升到 74%；但 span >10 会丢整句（29 span 实测 130→101 词）。
        #   ⇒ 句数 ≤10 按句挂 rate，超过就退回整块单 span。
        _sents = merge_to_limit(split_sents(ch), SPAN_LIMIT)
        if len(_sents) >= 2:
            tag = " ".join(MK.rate(x, rate) for x in _sents)
            n_span = len(_sents)
        else:
            tag = MK.rate(ch, rate)
            n_span = 1
        raw = out / "raw" / ("c%02d.wav" % i)
        fix = out / "fix" / ("c%02d.wav" % i)
        rec = dict(idx=i, words=seg["words"], rate=rate, gap_scale=gs,
                   scene=why[:60], n_span=n_span, max_tokens=seg["mtok"], text=ch)
        if fix.exists() and fix.stat().st_size > 10000:
            d = len(sf.read(str(fix))[0]) / SR
            rec.update(dur=round(d, 2), status="cached")
            print("[%02d/%02d] cached %.2fs  rate=%s  %s" % (i, len(recs), d, rate, why[:40]), flush=True)
            meta.append(rec); continue
        t0 = time.time()
        rc, msg = call_tts(tag, str(raw), seed=a.seed, max_tokens=seg["mtok"])
        if rc != 0 or not raw.exists():
            rec.update(status="fail", err=msg)
            print("[%02d/%02d] FAIL rc=%s %s" % (i, len(recs), rc, msg[:160]), flush=True)
            meta.append(rec); continue
        d_raw = len(sf.read(str(raw))[0]) / SR
        rc2, msg2 = transplant(str(raw), str(fix), str(out / "fix" / ("c%02d.json" % i)))
        d_fix = len(sf.read(str(fix))[0]) / SR if fix.exists() else 0
        el = time.time() - t0
        rec.update(dur=round(d_fix, 2), dur_raw=round(d_raw, 2),
                   status="ok" if rc2 == 0 else "transplant_fail", elapsed=round(el, 1))
        print("[%02d/%02d] %4d词 rate=%-4s tok%-4d %-28s %6.2fs→%6.2fs  %5.1fs" % (
            i, len(recs), rec["words"], rate, seg["mtok"], why[:24], d_raw, d_fix, el), flush=True)
        meta.append(rec)
        json.dump(meta, open(out / "chunks.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    # ---- 拼接 ----
    ok = [m for m in meta if m.get("status") in ("ok", "cached") and m.get("dur")]
    print("\n成功 %d/%d 块，总耗时 %.1f 分钟" % (len(ok), len(recs), (time.time() - t_all) / 60))
    if not ok:
        raise SystemExit("没有可用块")
    gap = donor_gap(1.6)
    parts = []
    for k, m in enumerate(ok):
        p = out / "fix" / ("c%02d.wav" % m["idx"])
        parts.append(load(str(p)))
        if k != len(ok) - 1:
            parts.append(gap.copy())
    full = np.concatenate(parts)
    # 首尾留 0.4s 静音
    pad = np.zeros(int(0.4 * SR))
    full = np.concatenate([pad, full, pad])
    dst = out / ("chapter1_%.1fs.wav" % (len(full) / SR))
    sf.write(str(dst), full.astype(np.float32), SR, subtype="PCM_16")
    json.dump(dict(chunks=meta, out=str(dst), dur=round(len(full) / SR, 2)),
              open(out / "chapter.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→ %s  (%.2fs = %.1f 分钟)" % (dst, len(full) / SR, len(full) / SR / 60))


if __name__ == "__main__":
    main()
