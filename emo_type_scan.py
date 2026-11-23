# -*- coding: utf-8 -*-
"""emo_type_scan.py —— 一句 × 8 个 emo type，测「每个 type 到底推得动多少」。

背景：pilot 6 条发现 type 之间差异巨大——
  sad      Charles 委屈  neutral 0.9987 → sad 0.9994   ✅ 干净推开
  afraid   Charles 紧张  happy   0.972  → fearful 0.508 ✅ 推开
  afraid   Joseph  紧张  happy   0.984  → neutral 0.856  ❌ 只降 A 不升 fear
  disgusted Thomas 警惕  sad     0.987  → sad 0.944     ❌ 完全不动
  happy    Thomas 兴奋  sad     0.972  → sad 0.499+neutral 0.445 ❌ 打散了

⇒ 「警惕→disgusted」这条映射（22 条在用）可能根本生不出来。
本脚本用一句**对标签响应良好**的基线句（c2_0309，ctl 是 neutral 0.9987）
把所有 type 都打一遍，量出每个 type 的推力和副作用（时长/F0/声纹）。

判读规则（先定后看）：
  1. 推力 = 目标维度 eV 相对 ctl 的增量，以及 top-1 是否变成目标类
  2. 副作用 = 语音时长比（>1.5 或 <0.7 视为崩）、F0 位移、峰值
  3. 只比较相对 ctl，不比绝对阈值（阈值是按人工正样本分位定的另一把尺子）
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
os.chdir("G:/_setup")

import numpy as np
import soundfile as sf
import parselmouth

ACPP = "G:/_setup/dots_tts_acpp/audiocpp_cli.exe"
ACPP_DIR = "G:/_setup/dots_tts_acpp"
MODEL = "G:/_setup/models/dots_tts"
OUT_DIR = "G:/_setup/_emo_type_scan"
THREADS = 6
SEED = 42

UNIT = "c2_0309"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
# 目标维度：type -> e2v 里的类名（用于判 top-1 是否命中）
TYPES = ["angry", "happy", "sad", "afraid", "disgusted",
         "surprised", "calm", "melancholic", "neutral"]
WANT = {
    "angry": "生气/angry", "happy": "开心/happy", "sad": "难过/sad",
    "afraid": "恐惧/fearful", "disgusted": "厌恶/disgusted",
    "surprised": "吃惊/surprised", "calm": "中立/neutral",
    "melancholic": "难过/sad", "neutral": "中立/neutral",
}


def words(t):
    return re.findall(r"[A-Za-z']+", t)


def plain(text):
    t = text.strip()
    for ch in "\"'\"'":
        t = t.replace(ch, "")
    return re.sub(r"\s+", " ", t).strip()


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def gen(src, plain_text, instruction, out, mt):
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", str(THREADS),
           "--request-option", "template_name=edit",
           "--source-audio", src,
           "--request-option", "source_text=" + plain_text,
           "--request-option", "target_text=" + plain_text,
           "--request-option", "use_xvector=on",
           "--text", instruction, "--seed", str(SEED), "--out", out,
           "--request-option", "max_tokens=%d" % mt,
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ACPP_DIR, timeout=1200)
    ok = os.path.exists(out) and os.path.getsize(out) > 20000
    return ok, time.time() - t0


def phys(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    snd = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr)
    pt = snd.to_pitch(time_step=0.005, pitch_floor=50.0, pitch_ceiling=400.0)
    f = pt.selected_array["frequency"]
    v = f[f > 0]
    dur = len(f) * 0.005
    voiced = len(v) * 0.005
    peak = float(np.max(np.abs(y)))
    # 扣静音后的语音时长：有声帧 + 50ms 容差
    return {"dur": round(dur, 2),
            "voiced": round(voiced, 2),
            "silent": round(1 - voiced / max(dur, 1e-6), 3),
            "f0_med": round(float(np.percentile(v, 50)), 1) if len(v) > 5 else None,
            "f0_span": round(float(np.percentile(v, 90) - np.percentile(v, 10)), 1) if len(v) > 5 else None,
            "peak": round(peak, 3)}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            plan[r["id"]] = r
    p = plan[UNIT]
    txt = plain(p["text"])
    n = len(words(txt))
    src = os.path.join("_regen_r2_out", UNIT + ".wav")
    if not os.path.exists(src):
        src = os.path.join("_audio_ch123/out", UNIT + ".wav")
    mt = mtok(n)
    print("%s  %s  %s  %d 词  mt=%d" % (UNIT, p["who"], p["emo"], n, mt), flush=True)
    print("text: %s\n" % txt, flush=True)

    from ser import E2V
    print("加载 e2v …", flush=True)
    e2v = E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large")

    rows = []
    # 先跑 ctl（同 seed 无标签），作为唯一对照
    todo = [("ctl", None)] + [(t, t) for t in TYPES]
    for tag, etype in todo:
        out = os.path.join(OUT_DIR, "%s_%s.wav" % (UNIT, tag))
        instr = txt if etype is None else '<emo type="%s" level="2">%s</emo>' % (etype, txt)
        if os.path.exists(out) and os.path.getsize(out) > 20000:
            print("[skip] %-12s 已存在" % tag, flush=True)
        else:
            ok, dt = gen(src, txt, instr, out, mt)
            print("[gen ] %-12s %s  %.0fs" % (tag, "OK" if ok else "FAIL", dt), flush=True)
            if not ok:
                continue
        ph = phys(out)
        sc = e2v.score(out) or {}
        top = sc.pop("_top", None)
        rec = {"tag": tag, "type": etype, "top": top,
               "want": WANT.get(etype or "", None),
               "hit": (top == WANT.get(etype or "")) if etype else None,
               "target_p": round(float(sc.get(WANT.get(etype or "", ""), 0)), 4) if etype else None,
               "scores": dict(sorted(sc.items(), key=lambda kv: -kv[1])[:4]), **ph}
        rows.append(rec)
        print("        F0 %5s span %5s | dur %5s voiced %5s peak %5s | top %-14s %s"
              % (ph["f0_med"], ph["f0_span"], ph["dur"], ph["voiced"], ph["peak"],
                 top, "HIT" if rec["hit"] else ("-" if etype else "")), flush=True)

    json.dump(rows, open("G:/_setup/_emo_type_scan.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    base = next((r for r in rows if r["tag"] == "ctl"), None)
    print("\n=== 推力表（相对 ctl）===")
    if base:
        print("%-12s %6s %6s %6s %8s %6s" % ("type", "ΔF0", "Δspan", "时长×", "目标维", "top命中"))
        for r in rows:
            if r["tag"] == "ctl":
                continue
            d = (r["f0_med"] or 0) - (base["f0_med"] or 0)
            print("%-12s %+6.1f %+6.1f %6.2f %8s %6s"
                  % (r["type"], d, (r["f0_span"] or 0) - (base["f0_span"] or 0),
                     r["dur"] / max(base["dur"], 1e-6),
                     r["target_p"], "✓" if r["hit"] else "×"))
    print("→ G:/_setup/_emo_type_scan.json")


if __name__ == "__main__":
    main()
