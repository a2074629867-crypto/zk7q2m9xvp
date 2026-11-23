# -*- coding: utf-8 -*-
"""gsv5_fix_verify.py —— 验证 PR#2537 对齐修复后的微调权重是否还塌缩。

关键：直接 hook t2s_model.model.infer_panel，抓出生成的语义 token 序列本身
     （而不是只听时长），这样"是否提前 EOS"一眼可见。

对照基线（修复前的塌缩表，来自 _esweep.log 的 "T2S Decoding EOS" 打印）：
    base s1v3 : 521 token (20.84s)
    e1        :  36 token
    e2        :  25 token
    e3/e5     :  12 token   ← 第一个合法步就 EOS
    e8        :  13 token
    e11/e15   :  26 token
"""
import os
import sys
import time

import numpy as np
import soundfile as sf

REPO = r"G:/_setup/gsv5probe"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "GPT_SoVITS"))
os.chdir(REPO)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ["version"] = "v5turbo"

from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config  # noqa: E402

PM = "GPT_SoVITS/pretrained_models"
CFG = {"custom": {
    "device": "cpu", "is_half": False, "version": "v5turbo",
    "bert_base_path": PM + "/chinese-roberta-wwm-ext-large",
    "cnhuhbert_base_path": PM + "/chinese-hubert-base",
    "t2s_weights_path": PM + "/s1v3.ckpt",
    "vits_weights_path": PM + "/gsv-v5-pretrained/s2Gv5turbo.pth",
}}

REF = r"G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TEXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
TEXT = open(r"G:/_setup/scene_calmdeep.txt", encoding="utf-8").read().strip()
OUT = r"E:/tts-models/acpp/out/v5fix"
os.makedirs(OUT, exist_ok=True)

BASE = PM + "/s1v3.ckpt"
FIX_DIR = "GPT_weights_fix/"
EPS = ["e1", "e2", "e3", "e5", "e8", "e11", "e12", "e15"]

print("TEXT 词数: %d" % len(TEXT.split()), flush=True)

tts = TTS(TTS_Config(CFG))

# ---- hook：抓 infer_panel 的返回（y_list, idx_list）----
cap = {}
_orig = tts.t2s_model.model.infer_panel


def _hooked(*a, **kw):
    out = _orig(*a, **kw)
    try:
        y_list, idx_list = out
        cap["y"] = y_list
        cap["idx"] = idx_list
    except Exception as e:  # noqa: BLE001
        cap["err"] = repr(e)
    return out


tts.t2s_model.model.infer_panel = _hooked

RUN_ARGS = dict(
    ref_audio_path=REF, prompt_text=REF_TEXT, prompt_lang="en",
    text=TEXT, text_lang="en",
    top_k=15, top_p=1, temperature=1, repetition_penalty=1.35,
    parallel_infer=True, split_bucket=False, seed=42, speed_factor=1.0,
)

rows = []


def run_one(tag, path):
    if not os.path.exists(path):
        print("[MISS] %s" % tag, flush=True)
        return
    cap.clear()
    t0 = time.time()
    tts.init_t2s_weights(path)
    sr, audio = None, None
    for chunk in tts.run(dict(RUN_ARGS)):
        if chunk is not None:
            sr, audio = chunk
    dt = time.time() - t0
    dur = len(audio) / sr if audio is not None else 0.0
    ntok = None
    y = cap.get("y")
    if y is not None:
        try:
            arr = y if isinstance(y, (list, tuple)) else [y]
            ntok = int(sum(int(t.shape[-1]) for t in arr))
        except Exception:  # noqa: BLE001
            ntok = -1
    if audio is not None:
        sf.write(os.path.join(OUT, "%s.wav" % tag), audio, sr)
    rows.append((tag, round(dur, 2), ntok))
    print("  %-8s 时长 %6.2fs   语义token %s   (%.0fs)" %
          (tag, dur, ntok if ntok is not None else "?", dt), flush=True)


print("\n===== base 基线 =====", flush=True)
run_one("base", BASE)

print("\n===== 修复版微调权重 =====", flush=True)
for e in EPS:
    run_one(e, FIX_DIR + "mcconaughey_v5full_fix-%s.ckpt" % e)

print("\n===== 汇总 =====", flush=True)
for tag, dur, ntok in rows:
    flag = "✅" if (ntok or 0) > 300 else ("⚠️" if (ntok or 0) > 100 else "❌塌缩")
    print("  %-8s %6.2fs  %5s token  %s" % (tag, dur, ntok, flag))

import json  # noqa: E402
json.dump(rows, open("G:/_setup/_v5fix_verify.json", "w"), ensure_ascii=False, indent=1)
print("输出目录: %s" % OUT, flush=True)
