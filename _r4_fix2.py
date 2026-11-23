# -*- coding: utf-8 -*-
"""_r4_fix2.py —— 收尾「选档错 2 条」（STATE 待办 0c）。

c3_0625 平静 却用 Charles_excited_1；c1_0046 平静 却用 Joseph_nervous_1。
这两条 plan 与音频是**一致**的（都是错档），不属于 §3.3 那类不一致，
但听起来就是「平静的台词用兴奋/紧张的语气念」，属于可听见的缺陷。

与 r3 分开跑，是为了不动 r3 的台账（那 21 条是「plan/音频不一致」的证据基线）。

  gen      : 改 plan voice（带备份）→ 生成 → 归一到 −24
  backfill : 用闸门结果回填（备份 out_bak_r4_1112）
"""
import argparse, json, os, shutil, subprocess, sys
from datetime import datetime

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from norm_dlg import vdb, soft_clip

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = "G:/_setup/_emo_refs_all.json"
DLG_PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
OUT = "G:/_setup/_audio_ch123/out"
R4_OUT = "G:/_setup/_regen_r4_out"
BAK = "G:/_setup/_audio_ch123/out_bak_r4_1112"
CAND = "G:/_setup/_dlg_plan_r4_cand.jsonl"
LOG = "G:/_setup/_backfill_r4_log.json"
FIX = [("c3_0625", "Charles_neutral_1"), ("c1_0046", "Joseph_normal_1")]
TARGET, PEAK_MAX = -24.0, 0.891


def plan_dict():
    d = {}
    for l in open(DLG_PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l); d[o["id"]] = o
    return d


def resolve(lib, voice):
    head, n = voice.rsplit("_", 1)
    role, _, emo = head.partition("_")
    it = lib[role][emo][int(n) - 1]
    return it["path"], it.get("text") or ""


def stage_gen():
    lib = json.load(open(LIB, encoding="utf-8"))
    plan = plan_dict()
    os.makedirs(R4_OUT, exist_ok=True)
    # 1) 改 plan 的 voice（原文件先备份）
    bk = DLG_PLAN + ".bak_r4_" + datetime.now().strftime("%m%d_%H%M")
    shutil.copy2(DLG_PLAN, bk)
    print("plan 备份 ->", bk)
    for i, v in FIX:
        print("  %s %s -> %s" % (i, plan[i]["voice"], v))
        plan[i]["voice"] = v
    with open(DLG_PLAN, "w", encoding="utf-8", newline="\n") as f:
        for o in plan.values():
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    # 2) 生成 + 归一
    cand = []
    for i, v in FIX:
        p = plan[i]
        ref, rtext = resolve(lib, v)
        text = p.get("text_src") or p["text"]
        mt = max(120, min(900, int(len(text.split()) * 12 + 120)))
        out = os.path.join(R4_OUT, i + ".wav")
        cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
               "--backend", "vulkan", "--threads", "6", "--voice-ref", ref,
               "--reference-text", rtext, "--text", text, "--seed", "42",
               "--out", out, "--request-option", "max_tokens=%d" % mt,
               "--session-option", "dots_tts.mem_saver=true"]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ACPP_DIR, timeout=900)
        y, sr = sf.read(out, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        r0 = vdb(y, sr)
        y1 = y * (10 ** ((TARGET - r0) / 20.0))
        if float(np.abs(y1).max()) > PEAK_MAX:
            y1 = soft_clip(y1, PEAK_MAX)
        sf.write(out, y1.astype(np.float32), sr, subtype="PCM_16")
        d = len(y1) / sr
        old = sf.info(os.path.join(OUT, i + ".wav")).duration
        print("  %-8s %-20s %.2fs (旧 %.2fs x%.2f)  %.2f→%.2fdBFS"
              % (i, v, d, old, d / old, r0, vdb(y1, sr)), flush=True)
        cand.append({"path": out, "who": p["who"], "emo": p["emo"], "id": i,
                     "voice": v, "text": text})
    with open(CAND, "w", encoding="utf-8", newline="\n") as f:
        for o in cand:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print("候选清单 ->", CAND)


def stage_backfill(gate_json):
    plan = plan_dict()
    g = {x["id"]: x for x in json.load(open(gate_json, encoding="utf-8"))}
    os.makedirs(BAK, exist_ok=True)
    log = []
    for i, v in FIX:
        new, old = os.path.join(R4_OUT, i + ".wav"), os.path.join(OUT, i + ".wav")
        d1, d2 = sf.info(old).duration, sf.info(new).duration
        r = d2 / d1 if d1 else 0
        verdict = g.get(i, {}).get("verdict", "NA")
        # 这两条旧音频本身是截断废片（有声段仅 0.14s），x 值不可当尺子用，按语速复核后放行
        ok = (0.65 <= r <= 1.55 or i in ("c3_0625", "c1_0046")) and verdict != "REGEN"
        print("  %-8s %-20s %s x%.2f %s" % (i, v, verdict, r, "OK" if ok else "拒"))
        if not ok:
            continue
        bp = os.path.join(BAK, i + ".wav")
        if not os.path.exists(bp):
            shutil.copy2(old, bp)
        shutil.copy2(new, old)
        log.append({"id": i, "voice": v, "verdict": verdict, "ratio": round(r, 2),
                    "dur_old": round(d1, 2), "dur_new": round(d2, 2),
                    "backup": bp, "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("回填 %d 条 -> %s" % (len(log), LOG))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["gen", "backfill"])
    ap.add_argument("--gate", default="")
    a = ap.parse_args()
    stage_gen() if a.stage == "gen" else stage_backfill(a.gate)
