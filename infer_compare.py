# -*- coding: utf-8 -*-
"""GPT-SoVITS 采样对比脚本（CPU 推理）

一次加载底模（BERT / HuBERT / GPT / SoVITS），之后按 plan 逐组热切换权重出样，
避免每组都重新加载模型。

用法：
  python -u infer_compare.py --plan plan.json --out E:/tts-models/out/gsv

plan.json 形如：
  [
    {"tag": "Z0_pretrained", "s1": null, "s2": null},
    {"tag": "T_s2e8_s1e15",  "s1": "GPT_weights_v2/xxx-e15.ckpt",
                             "s2": "SoVITS_weights_v2/xxx_e8_s1234.pth"}
  ]
s1/s2 为 null 时用官方预训练底模（= 零样本克隆基线）。

产出：<out>/<tag>.wav  +  <out>/<tag>_slow80.wav（ffmpeg atempo 0.80，保音高，对齐 P4）
"""
import argparse
import json
import os
import subprocess
import sys
import time

REPO = r"G:/GPT-SoVITS"
FF = r"E:/tool/oopz/ffmpeg.exe"
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "GPT_SoVITS"))

import soundfile as sf  # noqa: E402

from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config  # noqa: E402

BERT = "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
HUBERT = "GPT_SoVITS/pretrained_models/chinese-hubert-base"
S2G_DEF = "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth"
S1_DEF = "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"

# 参考音频（从 Wonder 训练集里挑的 7.80s 干净片段）
REF = r"G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0023447040_0023696640.wav"
REF_TEXT = "Off the coast of Portugal waves rising as high as hills are rolling calmly toward the shore"

# 与 P1~P4 完全相同的测试文本（E:/tts-models/para3.json）
TEXT = (
    "Three months ago, his grandmother died, and then they had moved to this house. "
    "I will not live there again, until it belongs to me, his father had said. "
    "Though the old man lay upstairs, after a second stroke, and lingered, giving no trouble."
)


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


def synth(tts, tag, out_dir, ref=REF, ref_text=REF_TEXT, text=TEXT,
          speed=1.0, seed=42, top_k=15, temperature=0.9, rep=1.35):
    t0 = time.time()
    gen = tts.run({
        "text": text,
        "text_lang": "en",
        "ref_audio_path": ref,
        "prompt_text": ref_text,
        "prompt_lang": "en",
        "top_k": top_k,
        "top_p": 1,
        "temperature": temperature,
        "text_split_method": "cut5",
        "batch_size": 1,
        "speed_factor": speed,
        "seed": seed,
        "parallel_infer": True,
        "repetition_penalty": rep,
    })
    sr, audio = None, None
    for sr, audio in gen:
        pass
    if audio is None:
        raise RuntimeError("推理无输出: " + tag)
    os.makedirs(out_dir, exist_ok=True)
    wav = os.path.join(out_dir, tag + ".wav")
    sf.write(wav, audio, sr)
    dur = len(audio) / sr
    print("[ok] %-18s %5.2fs 音频  用时 %.1fs  -> %s" % (tag, dur, time.time() - t0, wav), flush=True)
    return wav


def slow80(wav, out_dir, tag):
    out = os.path.join(out_dir, tag + "_slow80.wav")
    r = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", wav,
                        "-af", "atempo=0.80", "-c:a", "pcm_s16le", out],
                       capture_output=True)
    if r.returncode == 0:
        print("[ok] %-18s 0.80x -> %s" % (tag + "_slow80", out), flush=True)
    else:
        print("[!!] atempo 失败: " + r.stderr.decode("utf-8", "ignore")[-200:], flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-slow", action="store_true")
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    tts = build_tts()

    done = []
    for job in plan:
        tag = job["tag"]
        s1 = job.get("s1")
        s2 = job.get("s2")
        print("\n===== %s =====" % tag, flush=True)
        try:
            if s2:
                p = s2 if os.path.isabs(s2) else os.path.join(REPO, s2)
                if not os.path.exists(p):
                    print("[skip] 缺 SoVITS 权重 " + p, flush=True)
                    continue
                tts.init_vits_weights(p)
            else:
                tts.init_vits_weights(S2G_DEF)
            if s1:
                p = s1 if os.path.isabs(s1) else os.path.join(REPO, s1)
                if not os.path.exists(p):
                    print("[skip] 缺 GPT 权重 " + p, flush=True)
                    continue
                tts.init_t2s_weights(p)
            else:
                tts.init_t2s_weights(S1_DEF)
            wav = synth(tts, tag, a.out)
            if not a.no_slow:
                slow80(wav, a.out, tag)
            done.append(tag)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("[!!] %s 失败: %s" % (tag, e), flush=True)

    print("\n完成 %d/%d: %s" % (len(done), len(plan), ", ".join(done)), flush=True)


if __name__ == "__main__":
    main()
