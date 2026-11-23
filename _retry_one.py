# -*- coding: utf-8 -*-
"""_retry_one.py —— 单条多 seed 试生成，只报时长/语速，不覆盖正式产物。

为什么要它：regen_r3 里 3 条落不进时长硬闸（0.65~1.55），
其中 1 条是「参考档在该句上必然提前 EOS」（wronged_1/begging_1），
另 2 条是「同一 seed 生成偏慢」。逐条换 seed / 换档重试比整批重跑便宜。

用法：
  G:/Python310/python.exe _retry_one.py c1_0050 Thomas_begging_3 7 1234
"""
import json, os, subprocess, sys, soundfile as sf

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIBJ = "G:/_setup/_emo_refs_all.json"
TMP = "G:/_setup/_regen_r3_out/_try"
os.makedirs(TMP, exist_ok=True)

lib = json.load(open(LIBJ, encoding="utf-8"))
plan = {}
for l in open("G:/_setup/_dlg_plan_v2.jsonl", encoding="utf-8"):
    l = l.strip()
    if l:
        o = json.loads(l); plan[o["id"]] = o


def resolve(voice):
    head, n = voice.rsplit("_", 1)
    role, _, emo = head.partition("_")
    it = lib[role][emo][int(n) - 1]
    return it["path"], it.get("text") or ""


def words(t):
    t = (t or "").replace("\u2018", " ").replace("\u2019", "'")
    return len([k for k in t.split() if any(c.isalpha() for c in k)])


def run(i, voice, seed):
    p = plan[i]
    ref, rtext = resolve(voice)
    text = p.get("text_src") or p["text"]
    mt = max(120, min(900, int(len(text.split()) * 12 + 120)))
    out = os.path.join(TMP, "%s_%s_s%d.wav" % (i, voice, seed))
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6", "--voice-ref", ref,
           "--reference-text", rtext, "--text", text, "--seed", str(seed),
           "--out", out, "--request-option", "max_tokens=%d" % mt,
           "--session-option", "dots_tts.mem_saver=true"]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=ACPP_DIR, timeout=900)
    if not os.path.exists(out):
        return None
    d = sf.info(out).duration
    old = sf.info("G:/_setup/_audio_ch123/out/%s.wav" % i).duration
    w = words(p["text"])
    print("  %-8s %-20s seed %-5d %5.2fs  x%.2f  %3.0fwpm  %s"
          % (i, voice, seed, d, d / old if old else 0, w / d * 60 if d else 0, out), flush=True)
    return d, out


if __name__ == "__main__":
    i = sys.argv[1]
    voices = sys.argv[2].split(",")
    seeds = [int(s) for s in sys.argv[3].split(",")]
    print("原: %.2fs  %s" % (sf.info("G:/_setup/_audio_ch123/out/%s.wav" % i).duration,
                            plan[i]["text"][:60]))
    for v in voices:
        for s in seeds:
            run(i, v, s)
