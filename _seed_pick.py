# -*- coding: utf-8 -*-
"""_seed_pick.py —— 原生生成路线：同文本多 seed 择优，挑「目标词本身就长」的 take。

为什么走这条：
  · `<rate>` 标签在本机不生效（分词表里没有 rate/pitch/pause 控制 token，
    GGUF `--inspect` 只声明 tts/clon、`supports_timestamps=false`）。
  · 官方 `dots.tts.edit` SDK 需要 ROCm/CUDA torch；Windows 没有 ROCm 轮子（实测无匹配），
    RX580(gfx803) 也不在 ROCm 支持列表 ⇒ 本地跑不了。
  · 所以「原生」只剩 seed 择优：模型自己生成，不动音频一帧。已有数据：
    think 在 seed 42/43/44 = 220/320/220ms，天然跨度 1.45x。

判据（全部实测，不看单条）：
  目标词时长（干净文本 forced_align，取第 --occ 次出现）/ 全文覆盖率（不吃字）/ F0 不越界。
"""
import argparse
import json
import os
import re
import subprocess
import sys

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _align_gate as AG      # noqa: E402
import _paths as P            # noqa: E402

OUT = "G:/_setup/_seedpick"


def clean(t):
    """去掉包裹引号后再把内部 ’(U+2019) 统一成撇号。

    坑：剧本用 ‘…’（U+2018/U+2019）当引号，而 don’t / it’s 的撇号也是 U+2019。
    直接全局替换会把收尾引号变成孤零零的 '，喂给 TTS 就多念一个符号。
    """
    t = t.strip()
    if t[:1] in "\u2018\u201c\"'":
        t = t[1:]
    if t[-1:] in "\u2019\u201d\"'":
        t = t[:-1]
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", "").replace("\u201d", "")
    return re.sub(r"\s+", " ", t).strip()


def gen(text, ref, out, seed):
    cmd = [P.ACPP, "--task", "tts", "--family", "dots_tts", "--model", P.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=760",
           "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, cwd=P.ACPP_DIR, capture_output=True, text=True, timeout=1500)
    return r.returncode


def words(path, text, proc, model):
    r = AG.align(proc, model, path, text)
    if not r:
        return None
    ws, cur = [], []
    for tk in r["tokens"]:
        if tk["tok"] == "|":
            if cur:
                ws.append(cur)
            cur = []
        else:
            cur.append(tk)
    if cur:
        ws.append(cur)
    return [("".join(x["tok"] for x in w).lower(),
             (w[-1]["end"] - w[0]["start"]) * 0.02 * 1000) for w in ws]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="c2_0368")
    ap.add_argument("--word", default="think")
    ap.add_argument("--occ", type=int, default=1, help="第几次出现（1=第一个）")
    ap.add_argument("--seeds", default="42,43,44,45,46,47,48,49")
    ap.add_argument("--ref", default="")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json",
                                               encoding="utf-8"))}
    text = clean(rows[a.id]["text"])
    voice = ""
    for l in open("G:/_setup/_castle_en_ch123_plan_v4.jsonl", encoding="utf-8"):
        d = json.loads(l)
        if d["id"] == a.id:
            voice = d.get("voice", "")
            break
    ref = a.ref or "G:/_setup/_refs_v3/%s.wav" % voice
    if not os.path.exists(ref):                       # plan 里是 Charles_soft_1，库里是 Charles_soft
        alt = "G:/_setup/_refs_v3/%s.wav" % re.sub(r"_\d+$", "", voice)
        if os.path.exists(alt):
            ref = alt
    print("id=%s voice=%s" % (a.id, voice))
    print("ref=%s  exists=%s" % (ref, os.path.exists(ref)))
    print("text=%r" % text)
    if not os.path.exists(ref):
        sys.exit("参考不存在")

    proc, model = AG.load_model()
    res = []
    base = "G:/_setup/_audio_ch123/out/%s.wav" % a.id   # 基线用现役成品，不重新生成
    os.makedirs(os.path.join(OUT, a.id), exist_ok=True)
    if os.path.exists(base):
        w0 = words(base, text, proc, model)
        occ = [d for k, d in (w0 or []) if k == a.word] if w0 else []
        b = occ[a.occ - 1] if len(occ) >= a.occ else None
        print("基线（现役 out/）目标词 %s = %s" % (a.word, ("%.0fms" % b) if b else "n/a"))

    for sd in [x.strip() for x in a.seeds.split(",") if x.strip()]:
        p = os.path.join(OUT, a.id, "s%s.wav" % sd)
        if not (os.path.exists(p) and os.path.getsize(p) > 10000):
            if gen(text, ref, p, int(sd)) != 0 or not os.path.exists(p):
                print("seed %-3s 生成失败" % sd)
                continue
        w = words(p, text, proc, model)
        if not w:
            print("seed %-3s 对齐失败" % sd)
            continue
        occ = [d for k, d in w if k == a.word]
        tv = occ[a.occ - 1] if len(occ) >= a.occ else None
        y, sr = sf.read(p, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        f = parselmouth.Sound(p).to_pitch(0.01, 75, 600).selected_array["frequency"]
        f = f[f > 0]
        res.append(dict(seed=sd, dur=round(len(y) / sr, 2),
                        target=round(tv, 0) if tv else None,
                        nword=len(w), f0=int(np.median(f)) if len(f) else 0))
        print("seed %-3s 总%5.2fs  %s=%s  词数 %d  F0 %d"
              % (sd, len(y) / sr, a.word, ("%.0fms" % tv) if tv else "n/a",
                 len(w), res[-1]["f0"]))

    json.dump(res, open(os.path.join(OUT, a.id, "_pick.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = [r for r in res if r["target"]]
    if ok:
        ok.sort(key=lambda r: -r["target"])
        print()
        print("按目标词时长排序（前 4）：")
        for r in ok[:4]:
            print("  seed %-3s %4.0fms  总%.2fs  F0 %d" % (r["seed"], r["target"], r["dur"], r["f0"]))
