# -*- coding: utf-8 -*-
"""gsv5_mini_verify.py —— 用 mini 过拟合权重做推理，验证管线是否真的通。

判据：若输出时长/token 数与 base 同量级（≥300 token），说明微调管线本身没问题，
      461 片那个塌缩是数据质量问题（静音+对齐方差）。
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
OUT = r"E:/tts-models/acpp/out/v5mini"
os.makedirs(OUT, exist_ok=True)

# mini 训练集里的一句（测"背下来"）+ 目标文本（测"泛化"）
MINI_TEXT = "she wrapped herself in a fuzzy blanket,"

CAND = [
    ("base", PM + "/s1v3.ckpt"),
    ("mini_e10", "GPT_weights_mini/mcconaughey_mini-e10.ckpt"),
    ("mini_e20", "GPT_weights_mini/mcconaughey_mini-e20.ckpt"),
    ("mini_e30", "GPT_weights_mini/mcconaughey_mini-e30.ckpt"),
    ("fix_e1", "GPT_weights_fix/mcconaughey_v5full_fix-e1.ckpt"),
    ("fix_e11", "GPT_weights_fix/mcconaughey_v5full_fix-e11.ckpt"),
]

tts = TTS(TTS_Config(CFG))


def run(tag, path, text, name):
    if not os.path.exists(path):
        print("  [MISS] %s" % tag, flush=True)
        return None
    tts.init_t2s_weights(path)
    run_args = dict(
        ref_audio_path=REF, prompt_text=REF_TEXT, prompt_lang="en",
        text=text, text_lang="en",
        top_k=15, top_p=1, temperature=1, repetition_penalty=1.35,
        parallel_infer=True, split_bucket=False, seed=42,
    )
    sr, audio = None, None
    for chunk in tts.run(run_args):
        if chunk is not None:
            sr, audio = chunk
    dur = len(audio) / sr if audio is not None else 0.0
    if audio is not None:
        sf.write(os.path.join(OUT, "%s_%s.wav" % (tag, name)), audio, sr)
    print("  %-10s %-14s %6.2fs" % (tag, name, dur), flush=True)
    return dur


print("=== 目标文本（38 词，base 约 22s）===", flush=True)
for tag, p in CAND:
    run(tag, p, TEXT, "target")

print("\n=== mini 训练集内的句子（测背没背下来）===", flush=True)
for tag, p in CAND[:4]:
    run(tag, p, MINI_TEXT, "seen")

print("\n输出目录: %s" % OUT, flush=True)
