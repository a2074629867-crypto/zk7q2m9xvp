# -*- coding: utf-8 -*-
"""_short_gate.py —— 短句（<1.6s）专用验收闸。

为什么需要它：
  七闸里的声纹（需 >=2.0s / 3.8s 才测）、情绪（需 >=1.2s 窗口 + 参考档）在短句上
  **物理不可测**，dialog_gate 只能给 MANUAL（D 档）。但「测不了」不等于「不能验收」：
  短句上仍然成立的四件事 —— 念的是不是这句话（内容）、电平、有没有截断、自然度。

判据（全部在 <1.6s 上可测）：
  content : 字符级 coverage >= 0.75 且 sim >= 0.70   （ASR vs 原文）
  level   : voiced RMS in [-25.5, -22.5] dBFS
  clean   : silent_ratio <= 0.55，dur >= 0.30s
  nat     : |nat.score| <= 2.5 sigma

判决：
  S_PASS   四项全过  —— 短句验收通过（声纹/情绪不可测，免责）
  S_REGEN  内容挂     —— 真问题：吞字/念错/多念，必须重生成
  S_FIX    只有电平/静音/自然度挂 —— 可后处理修
  S_UNK    ASR 失败
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as _P

from wlevel_flags import coverage

ROOT = _P.ROOT
AUDIO = os.path.join(ROOT, "_audio_ch123", "out_paused")
PLAN = os.path.join(ROOT, "_dlg_plan_v2_paused.jsonl")


def load_plan():
    d = {}
    for l in io.open(PLAN, encoding="utf-8"):
        if l.strip():
            x = json.loads(l)
            d[x["id"]] = x
    return d


def tech(p):
    import numpy as np
    import soundfile as sf
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    dur = len(y) / float(sr)
    # 25ms 帧，20ms  hop，-45dBFS 判定有声
    fl = int(0.025 * sr)
    hp = int(0.020 * sr)
    if len(y) < fl:
        return {"dur": dur, "rms_db": -99.0, "silent": 1.0}
    n = 1 + (len(y) - fl) // hp
    idx = np.arange(fl)[None, :] + hp * np.arange(n)[:, None]
    fr = y[idx]
    rms = np.sqrt((fr ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    vo = db > -45.0
    silent = 1.0 - vo.mean() if n else 1.0
    vr = float(np.sqrt((fr[vo] ** 2).mean())) if vo.any() else 1e-6
    return {"dur": dur, "rms_db": 20 * float(np.log10(vr + 1e-12)), "silent": float(silent)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", default=os.path.join(ROOT, "_dlg_buckets_v41.json"))
    ap.add_argument("--gate", default=os.path.join(ROOT, "_gate_dlg_v41.json"))
    ap.add_argument("--bucket", default="D")
    ap.add_argument("--ids", default="", help="显式 id 列表（逗号分隔），覆盖 --bucket")
    ap.add_argument("--auto-short", action="store_true",
                    help="从 --gate 里自动挑「七闸只挂短句类原因」的条目（口径不再依赖旧 buckets）")
    ap.add_argument("--asr-json", default="", help="asr_venv 产出的 {path: {text}} json")
    ap.add_argument("--asr-only", action="store_true", help="只在 asr_venv 下跑 ASR 并落盘")
    ap.add_argument("--cand", default="", help="候选目录（<id>__s<seed>.wav），评估生成件而非现役")
    ap.add_argument("--out", default=os.path.join(ROOT, "_short_gate.json"))
    ap.add_argument("--md", default=os.path.join(ROOT, "_short_gate.md"))
    a = ap.parse_args()

    plan = load_plan()
    g = {os.path.basename(x["wav"])[:-4]: x for x in json.load(io.open(a.gate, encoding="utf-8"))}

    paths, meta = [], []
    if a.cand:
        import glob
        for p in sorted(glob.glob(os.path.join(a.cand, "*.wav"))):
            paths.append(p)
            meta.append(os.path.basename(p)[:-4])
        print("待测 %d（候选目录）" % len(paths), flush=True)
    else:
        if a.ids:
            ids = [x.strip() for x in a.ids.split(",") if x.strip()]
        elif a.auto_short:
            codes = {"too_short", "spk_short", "emo_short", "nat_na"}
            ids = sorted(k for k, x in g.items()
                         if x.get("verdict") != "PASS"
                         and [r["code"] for r in (x.get("reasons") or [])]
                         and set(r["code"] for r in (x.get("reasons") or [])) <= codes)
        else:
            ids = json.load(io.open(a.buckets, encoding="utf-8"))[a.bucket]
        for i in ids:
            p = os.path.join(AUDIO, i + ".wav")
            if os.path.exists(p):
                paths.append(p)
                meta.append(i)
        print("待测 %d / %d" % (len(paths), len(ids)), flush=True)

    if a.asr_only:
        import _asr_lib
        res = _asr_lib.transcribe(paths)
        json.dump(res, io.open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        print("ASR 写出", a.out, len(res), flush=True)
        return

    if a.asr_json:
        res = json.load(io.open(a.asr_json, encoding="utf-8"))
    else:
        import _asr_lib
        res = _asr_lib.transcribe(paths)
    out = []
    WR = {}
    wj = os.path.join(ROOT, "_whisper_recall.json")
    if os.path.exists(wj):
        WR = json.load(io.open(wj, encoding="utf-8"))
    for p, i in zip(paths, meta):
        bid = i.split("__")[0]
        said = (res.get(p) or {}).get("text") or ""
        ref = (plan.get(bid) or {}).get("text") or ""
        cov, sim = coverage(ref, said)
        t = tech(p)
        nat = (g.get(bid) or {}).get("nat") or {}
        nsc = nat.get("score")
        reasons = []
        abbr = cov >= 0.95 and sim >= 0.60          # O.K.→Okay 这类写法差异
        wr = WR.get(bid)
        by_w = wr is not None and wr >= 0.80        # 第二 ASR（whisper）认出即认内容在
        if not (cov >= 0.75 and sim >= 0.70) and not abbr and not by_w:
            reasons.append("content")
        if not (-25.5 <= t["rms_db"] <= -22.5):
            reasons.append("level")
        if t["silent"] > 0.55 or t["dur"] < 0.30:
            reasons.append("clean")
        if nsc is not None and abs(nsc) > 2.5:
            reasons.append("nat")
        if "content" in reasons:
            v = "S_REGEN"
        elif reasons:
            v = "S_FIX"
        else:
            v = "S_PASS"
        out.append({"id": i, "verdict": v, "reasons": reasons, "cov": round(cov, 3), "sim": round(sim, 3),
                    "dur": round(t["dur"], 2), "rms_db": round(t["rms_db"], 2),
                    "silent": round(t["silent"], 2), "nat": nsc,
                    "ref": ref, "said": said,
                    "who": (plan.get(bid) or {}).get("who"), "emo": (plan.get(bid) or {}).get("emo")})

    json.dump(out, io.open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    from collections import Counter
    cnt = Counter(x["verdict"] for x in out)
    print(dict(cnt), flush=True)

    lines = ["# 短句专用验收（<1.6s，声纹/情绪不可测，改用 内容/电平/静音/自然度）", "",
             "| 结论 | 条数 |", "|---|---|"]
    for k in ["S_PASS", "S_FIX", "S_REGEN", "S_UNK"]:
        lines.append("| %s | %d |" % (k, cnt.get(k, 0)))
    lines += ["", "## 未通过明细", "", "| id | 结论 | 挂的项 | cov | sim | dur | RMS | 原文 → ASR |", "|---|---|---|---|---|---|---|---|"]
    for x in out:
        if x["verdict"] == "S_PASS":
            continue
        lines.append("| %s | %s | %s | %.2f | %.2f | %.2f | %.1f | %s → %s |" % (
            x["id"], x["verdict"], ",".join(x["reasons"]), x["cov"], x["sim"], x["dur"], x["rms_db"],
            (x["ref"] or "")[:40].replace("|", "/"), (x["said"] or "")[:40].replace("|", "/")))
    io.open(a.md, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("写出", a.out, a.md, flush=True)


if __name__ == "__main__":
    main()
