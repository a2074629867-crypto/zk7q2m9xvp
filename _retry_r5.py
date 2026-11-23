# -*- coding: utf-8 -*-
"""_retry_r5.py —— 对被语速闸拒收的 3 条换 seed 重试。

判据（与 finish_r5 一致）：新语速落 [90,260] wpm，且 NISQA-MOS 不低于旧音频 −0.15。
不达标就留着旧音频，不硬塞。
"""
import json, os, subprocess, sys
import numpy as np, soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
import _nat_guard as NG
from norm_dlg import vdb

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
HERE = "G:/_setup"
TMP = os.path.join(HERE, "_regen_r5_out/_try")
OUT = os.path.join(HERE, "_regen_r5_out")

IDS = ["c3_0623", "c3_0653", "c3_0853"]
SEEDS = [7, 1234, 2026]


def words(t):
    t = (t or "").replace("\u2018", " ").replace("\u2019", "'")
    return len([k for k in t.split() if any(c.isalpha() for c in k)])


def main():
    os.makedirs(TMP, exist_ok=True)
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
    lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
    todo = {r["id"]: r for r in json.load(open(os.path.join(HERE, "_regen_r5.json"), encoding="utf-8"))}

    for i in IDS:
        p = plan[i]; t = todo[i]
        role, _, emo = t["voice"].rsplit("_", 1)[0].partition("_")
        n = int(t["voice"].rsplit("_", 1)[1])
        it = lib[role][emo][n - 1]
        ref, rtext = it["path"], it.get("text") or ""
        text = p.get("text_src") or p["text"]
        w = words(text)
        old = os.path.join(HERE, "_audio_ch123/out", i + ".wav")
        m_old = (NG.raw(old) or {}).get("nq_mos")
        print("\n=== %s %s %d词 旧MOS %.2f" % (i, t["voice"], w, m_old or 0), flush=True)
        best = None
        for s in SEEDS:
            out = os.path.join(TMP, "%s_s%d.wav" % (i, s))
            mt = max(120, min(900, int(w * 12 + 120)))
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", "6",
                   "--voice-ref", ref, "--reference-text", rtext,
                   "--text", text, "--seed", str(s), "--out", out,
                   "--request-option", "max_tokens=%d" % mt,
                   "--session-option", "dots_tts.mem_saver=true", "--metrics"]
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=900)
            if not (os.path.exists(out) and os.path.getsize(out) > 50000):
                print("  seed %-5s 生成失败" % s, flush=True); continue
            y, sr = sf.read(out, dtype="float32")
            if y.ndim > 1:
                y = y.mean(1)
            d = len(y) / sr
            wpm = w / d * 60
            g = -24.0 - vdb(y, sr)
            y1 = (y * (10 ** (g / 20.0))).astype(np.float32) if abs(g) <= 20 else y
            sf.write(out, y1, sr, subtype="PCM_16")
            m = (NG.raw(out) or {}).get("nq_mos") or 0
            ok = 90 <= wpm <= 260 and m >= (m_old or 0) - 0.15
            print("  seed %-5s %5.2fs %4.0fwpm MOS %.2f  %s" % (s, d, wpm, m, "✓" if ok else ""), flush=True)
            if ok and (best is None or m > best[1]):
                best = (out, m, wpm)
        if best:
            import shutil
            shutil.copy2(best[0], os.path.join(OUT, i + ".wav"))
            print("  -> 采用 seed 结果 %.2fs %.0fwpm MOS %.2f" % (
                sf.info(best[0]).duration, best[2], best[1]), flush=True)
        else:
            print("  -> 无合格结果，保留旧音频", flush=True)


if __name__ == "__main__":
    main()
