# -*- coding: utf-8 -*-
"""_wary_pick.py —— 「警惕」双 seed 取一（闸门自己的 bimodal 提示要求的做法）。

背景：`BIMODAL` 集合里已有「警惕」，注释写明
  「同 ref 五个 seed 可 0.906 / 0.031 两极，单条不合格不代表 ref 错，需 2 seed 取一」。
r6 的 12 条警惕全部用 seed 42 生成；本脚本再补 seed 7，按
  ① e2v disgusted 概率（判据本身，阈值 p25=0.0052）
  ② 自然度 MOS
取优者覆盖 `_regen_r6_out/<id>.wav`，让后续闸门只看到胜出的那条。

用法：python _wary_pick.py [seed]
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
HERE = "G:/_setup"
OUT = os.path.join(HERE, "_regen_r6_out")
ALT = os.path.join(HERE, "_wary_s7")


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def resolve(lib, voice):
    parts = voice.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None, None
    head, n = parts[0], int(parts[1])
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    if 1 <= n <= len(items):
        it = items[n - 1]
        return (it.get("path"), it.get("text") or "") if isinstance(it, dict) else (it, "")
    return None, None


def main():
    seed = sys.argv[1] if len(sys.argv) > 1 else "7"
    os.makedirs(ALT, exist_ok=True)
    lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
    todo = [t for t in json.load(open(os.path.join(HERE, "_regen_r6.json"), encoding="utf-8"))
            if t["emo"] == "警惕"]
    print("警惕 %d 条，补 seed %s" % (len(todo), seed), flush=True)

    import ser as S
    import _nat_guard as NG
    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))

    def probe(p):
        sc = e2v.score(p) or {}
        return float(sc.get("厌恶/disgusted", 0.0)), (NG.raw(p).get("nq_mos") or 0), sc.get("_top")

    rows = []
    for k, t in enumerate(todo, 1):
        i = t["id"]
        ref, rtext = resolve(lib, t["voice"])
        if not ref:
            print("[%d] %s 参考解析失败" % (k, i), flush=True)
            continue
        p = plan[i]
        text = p.get("text_src") or p["text"]
        alt = os.path.join(ALT, "%s_s%s.wav" % (i, seed))
        if not (os.path.exists(alt) and os.path.getsize(alt) > 50000):
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", "6",
                   "--voice-ref", ref, "--reference-text", rtext or "",
                   "--text", text, "--seed", str(seed), "--out", alt,
                   "--request-option", "max_tokens=%d" % mtok(len(text.split())),
                   "--session-option", "dots_tts.mem_saver=true", "--metrics"]
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=1200)
        if not (os.path.exists(alt) and os.path.getsize(alt) > 50000):
            print("[%d/%d] %-8s 备用 seed 生成失败" % (k, len(todo), i), flush=True)
            continue
        cur = os.path.join(OUT, i + ".wav")
        if not os.path.exists(cur):
            print("[%d/%d] %-8s 主 seed 缺失，直接用备用" % (k, len(todo), i), flush=True)
            shutil.copy2(alt, cur)
            continue
        d0, m0, t0 = probe(cur)
        d1, m1, t1 = probe(alt)
        # 先比 disgusted（判据本身），差 < 0.0005 视为持平，再比 MOS
        win = "s" + seed if (d1 > d0 + 0.0005 or (abs(d1 - d0) <= 0.0005 and m1 > m0 + 0.1)) else "42"
        rows.append(dict(id=i, d42=round(d0, 4), m42=round(m0, 2), t42=t0,
                         dalt=round(d1, 4), malt=round(m1, 2), talt=t1, win=win))
        if win != "42":
            shutil.copy2(alt, cur)
        print("[%d/%d] %-8s disgusted %.4f/%.4f  MOS %.2f/%.2f  top %s/%s  -> %s"
              % (k, len(todo), i, d0, d1, m0, m1, t0, t1, win), flush=True)

    json.dump(rows, open(os.path.join(HERE, "_wary_pick_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if rows:
        n = sum(1 for r in rows if r["win"] != "42")
        print("\n备用 seed 胜出 %d / %d；台账 _wary_pick_log.json" % (n, len(rows)), flush=True)


if __name__ == "__main__":
    main()
