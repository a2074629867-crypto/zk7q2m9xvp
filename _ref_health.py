# -*- coding: utf-8 -*-
"""_ref_health.py —— 参考体检：一个参考能不能稳定生成，靠 5 条真实文本一起看。

为什么（2026-11-13 20:40 实测）：
  `_ab_tier48.py` 每组只测了 **1 条**试句就下「48k 参考有效」的结论，
  于是把 `c285_p0` 登记成 `Thomas_loud_5` 并开始批量重生成 80 条 ——
  结果前 10 条 **9 条生成失败**（0.32s / 0.48s 的残片）。

  同一条文本对照（c1_0162 / c1_0020）：
    旧参考 Thomas_loud_1(16k)  → 1.60s / 3.36s 正常
    新参考 Thomas_loud_5(48k)  → 0.48s / 0.32s 残片
  ⇒ 不是随机失败，是这个参考对一部分文本不工作。

**教训：参考的「声学指标好」≠「能稳定生成」。A/B 必须同时看三项：
  生成成功率、cos_char、时长比。单条样本不足以下结论。**

体检项（每条文本）：
  dur_ratio = 生成时长 / 原音频时长     < 0.6 判残片
  成功率 = 正常生成条数 / 5

用法：python _ref_health.py Thomas_loud_5 Charles_neutral_4 Charles_excited_4
"""
import json, os, subprocess, sys
import soundfile as sf

HERE = "G:/_setup"
sys.path.insert(0, HERE)

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
OUT = os.path.join(HERE, "_refhealth")
os.makedirs(OUT, exist_ok=True)
AUD = os.path.join(HERE, "_audio_ch123/out")
# 5 条覆盖短/中/长与不同引号结构（都用 plan 里真实条目）
PROBE = ["c1_0162", "c1_0020", "c2_0292", "c2_0304", "c1_0159"]


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def resolve(lib, voice):
    head, n = voice.rsplit("_", 1)[0], int(voice.rsplit("_", 1)[1])
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    if 1 <= n <= len(items):
        it = items[n - 1]
        return it["path"], it.get("text") or ""
    return None, ""


def main():
    lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}

    for voice in sys.argv[1:]:
        ref, rtext = resolve(lib, voice)
        print("\n===== %s  ref=%s  reftxt=%r" % (voice, os.path.basename(ref or "?"), (rtext or "")[:50]), flush=True)
        ok = 0
        for tid in PROBE:
            d_old = sf.info(os.path.join(AUD, tid + ".wav")).duration
            text = plan[tid].get("text_src") or plan[tid]["text"]
            out = os.path.join(OUT, "%s_%s.wav" % (voice, tid))
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", "6",
                   "--voice-ref", ref, "--reference-text", rtext,
                   "--text", text, "--seed", "42", "--out", out,
                   "--request-option", "max_tokens=%d" % mtok(len(text.split())),
                   "--session-option", "dots_tts.mem_saver=true"]
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=900)
            d = sf.info(out).duration if os.path.exists(out) else 0
            r = d / d_old if d_old else 0
            good = r >= 0.6
            ok += good
            print("  %-8s 原 %.2fs → 生成 %.2fs  x%.2f  %s" % (
                tid, d_old, d, r, "OK" if good else "★残片"), flush=True)
        print("  → 成功 %d/5  %s" % (ok, "可用" if ok >= 4 else "★不可用"), flush=True)


if __name__ == "__main__":
    main()
