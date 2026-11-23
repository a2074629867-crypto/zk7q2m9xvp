# -*- coding: utf-8 -*-
"""逐句生成 Wonder 原文（BEST 配方），用于和真实录音做同文本的韵律对比/移植。

每句输出一个 wav，文本与 `_dataset/sliced/` 里的真实切片逐字一致。
"""
import argparse
import os
import sys
import time

REPO = r"G:/GPT-SoVITS"
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "GPT_SoVITS"))

import soundfile as sf  # noqa: E402

from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config  # noqa: E402

BERT = "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
HUBERT = "GPT_SoVITS/pretrained_models/chinese-hubert-base"
S2G_DEF = "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth"
S1_DEF = "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"

W_S2 = "SoVITS_weights_v2/mcconaughey_calm_e8_s1216.pth"
W_S1 = "GPT_weights_v2/mcconaughey_calm-e10.ckpt"

SL = r"G:/GPT-SoVITS/_dataset/sliced"
REF_SIR = SL + "/wonder_train.wav_0018112640_0018378240.wav"
TXT_SIR = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."

# (id, 文本(与真实切片逐字一致), 真实切片文件)
LINES = [
    ("L1_long_and_bright",
     "Others long and bright, they voyage in the same direction.",
     "wonder_train.wav_0014440960_0014607680.wav"),
    ("L2_right_now",
     "before crumbling to dust, right now.",
     "wonder_train.wav_0016587840_0016739520.wav"),
    ("L3_galactic_travelers",
     "Right here, right now, we're galactic travelers on this vessel.",
     "wonder_train.wav_0019802560_0020009920.wav"),
    ("L4_long_journey",
     "An adventurer is arriving home after a long journey.",
     "wonder_train.wav_0036888640_0037002880.wav"),
]

# BEST 配方（见 tune_prosody.py）
RECIPE = dict(
    text_lang="en", prompt_lang="en",
    ref_audio_path=REF_SIR, prompt_text=TXT_SIR,
    top_k=15, top_p=1, temperature=0.9,
    text_split_method="cut0",
    batch_size=1, speed_factor=1.0, seed=42,
    parallel_infer=True, repetition_penalty=1.35,
)


def build_tts():
    cfg = {"version": "v2", "custom": {
        "device": "cpu", "is_half": False, "version": "v2",
        "t2s_weights_path": S1_DEF, "vits_weights_path": S2G_DEF,
        "cnhuhbert_base_path": HUBERT, "bert_base_path": BERT}}
    t0 = time.time()
    tts = TTS(TTS_Config(cfg))
    print("[init] 底模加载 %.1fs" % (time.time() - t0), flush=True)
    return tts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="E:/tts-models/out/lines")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = set(x for x in a.only.split(",") if x)
    os.makedirs(a.out, exist_ok=True)

    tts = build_tts()
    tts.init_vits_weights(os.path.join(REPO, W_S2))
    tts.init_t2s_weights(os.path.join(REPO, W_S1))
    print("[w] s2=%s s1=%s" % (W_S2, W_S1), flush=True)

    for lid, text, donor in LINES:
        if only and lid not in only:
            continue
        t0 = time.time()
        gen = tts.run(dict(RECIPE, text=text))
        sr = audio = None
        for sr, audio in gen:
            pass
        if audio is None:
            print("[!!] %s 无输出" % lid, flush=True)
            continue
        wav = os.path.join(a.out, lid + "_raw.wav")
        sf.write(wav, audio, sr)
        print("[ok] %-22s %5.2fs  %s  用时 %.1fs" %
              (lid, len(audio) / sr, text[:42], time.time() - t0), flush=True)

    print("完成", flush=True)


if __name__ == "__main__":
    main()
