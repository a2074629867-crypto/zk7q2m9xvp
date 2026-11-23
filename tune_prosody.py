# -*- coding: utf-8 -*-
"""韵律 / 节奏调参实验（CPU 推理）

问题：音色相似度已到 0.81（同一人），但听感"没味道"。
客观诊断（timbre.py）：
    指标        Wonder原声  生成e10   参考片段7.8s
    F0 跨度       23.51      5.27      28.60     ← 抑扬顿挫被抹平
    F0 起伏        6.26      3.49       7.64
    谱心 Hz        640       278        428      ← 高频气声丢失
⇒ "每个词的语气差别很大"这一维，在生成里基本没了。

本脚本固定最优权重（s2e8 + s1e10），只扫**能影响韵律的杠杆**：
    temperature / top_k / repetition_penalty / speed_factor / text_split_method / 参考音频

用法： python -u tune_prosody.py --out E:/tts-models/out/tune
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
REF_BASE = SL + "/wonder_train.wav_0023447040_0023696640.wav"
TXT_BASE = "Off the coast of Portugal waves rising as high as hills are rolling calmly toward the shore"
REF_ICE = SL + "/wonder_train.wav_0016135360_0016373120.wav"
TXT_ICE = "Long ago, as those pieces of icy rock get swept up into our atmosphere"
REF_SIR = SL + "/wonder_train.wav_0018112640_0018378240.wav"
TXT_SIR = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."

TEXT = (
    "Three months ago, his grandmother died, and then they had moved to this house. "
    "I will not live there again, until it belongs to me, his father had said. "
    "Though the old man lay upstairs, after a second stroke, and lingered, giving no trouble."
)

# 每组只动一个杠杆，方便归因
EXPS = [
    ("BASE",     dict(),                                                        "现状基线"),
    ("T115",     dict(temperature=1.15),                                        "提高采样温度→韵律更多变"),
    ("T140",     dict(temperature=1.40),                                        "温度再高，看是否跑偏"),
    ("K40",      dict(top_k=40),                                                "放开 top_k→候选更宽"),
    ("REP10",    dict(rep=1.0),                                                 "去掉重复惩罚压制"),
    ("CUT0",     dict(split="cut0"),                                            "整段不切句→跨句韵律连贯"),
    ("SP92",     dict(speed=0.92),                                              "放慢→韵律有时间展开"),
    ("COMBO",    dict(temperature=1.15, top_k=40, rep=1.0, speed=0.95,
                      split="cut0"),                                            "多杠杆叠加"),
    ("REF_ICE",  dict(ref=REF_ICE, rtext=TXT_ICE),                              "换参考：谱心903(气声最强)"),
    ("REF_SIR",  dict(ref=REF_SIR, rtext=TXT_SIR),                              "换参考：谱心868+F0跨度28.5"),
    ("BEST",     dict(ref=REF_SIR, rtext=TXT_SIR, split="cut0"),                "★最优组合：REF_SIR + 不切句"),
]


def build_tts():
    cfg = {
        "version": "v2",
        "custom": {
            "device": "cpu",
            "is_half": False,
            "version": "v2",
            "t2s_weights_path": S1_DEF,
            "vits_weights_path": S2G_DEF,
            "cnhuhbert_base_path": HUBERT,
            "bert_base_path": BERT,
        },
    }
    t0 = time.time()
    tts = TTS(TTS_Config(cfg))
    print("[init] 底模加载完成 %.1fs" % (time.time() - t0), flush=True)
    return tts


def synth(tts, tag, out_dir, o):
    ref = o.get("ref", REF_BASE)
    rtext = o.get("rtext", TXT_BASE)
    t0 = time.time()
    gen = tts.run({
        "text": TEXT,
        "text_lang": "en",
        "ref_audio_path": ref,
        "prompt_text": rtext,
        "prompt_lang": "en",
        "top_k": o.get("top_k", 15),
        "top_p": o.get("top_p", 1),
        "temperature": o.get("temperature", 0.9),
        "text_split_method": o.get("split", "cut5"),
        "batch_size": 1,
        "speed_factor": o.get("speed", 1.0),
        "seed": o.get("seed", 42),
        "parallel_infer": True,
        "repetition_penalty": o.get("rep", 1.35),
    })
    sr, audio = None, None
    for sr, audio in gen:
        pass
    if audio is None:
        raise RuntimeError("推理无输出: " + tag)
    os.makedirs(out_dir, exist_ok=True)
    wav = os.path.join(out_dir, tag + ".wav")
    sf.write(wav, audio, sr)
    print("[ok] %-10s %5.2fs 音频  用时 %4.1fs" % (tag, len(audio) / sr, time.time() - t0), flush=True)
    return wav


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="E:/tts-models/out/tune")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = set(x for x in a.only.split(",") if x)

    os.makedirs(a.out, exist_ok=True)
    tts = build_tts()

    p2 = os.path.join(REPO, W_S2)
    p1 = os.path.join(REPO, W_S1)
    print("[w] 固定权重 s2=%s  s1=%s" % (os.path.basename(p2), os.path.basename(p1)), flush=True)
    tts.init_vits_weights(p2)
    tts.init_t2s_weights(p1)

    done = []
    for tag, o, desc in EXPS:
        if only and tag not in only:
            continue
        print("\n===== %-10s %s =====" % (tag, desc), flush=True)
        try:
            synth(tts, tag, a.out, o)
            done.append(tag)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("[!!] %s 失败: %s" % (tag, e), flush=True)

    print("\n完成 %d 组: %s" % (len(done), ", ".join(done)), flush=True)


if __name__ == "__main__":
    main()
