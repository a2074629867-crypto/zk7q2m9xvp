# -*- coding: utf-8 -*-
"""验证 dots.tts 是否能用 `...` 让模型自己在逗号处停顿（原生），而不是后期灌静音。

对照：同一句、同一 seed，只改标点。
  A: "The third week of term, he had been ill."      （逗号，后期会在这切）
  B: "The third week of term... he had been ill."    （省略号，期望模型自己停）
产物：_native_test/*.wav + _native_test/report.json
"""
import json, os, subprocess, time

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
OUT = "G:/_setup/_native_test"
os.makedirs(OUT, exist_ok=True)

CASES = [
    ("A_comma_s42", "The third week of term, he had been ill.", 42),
    ("B_ellipsis_s42", "The third week of term... he had been ill.", 42),
    ("B_ellipsis_s7", "The third week of term... he had been ill.", 7),
]

rep = []
for tag, text, seed in CASES:
    out = os.path.join(OUT, tag + ".wav")
    if os.path.exists(out) and os.path.getsize(out) > 50000:
        print(tag, "SKIP", flush=True)
    else:
        cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
               "--backend", "vulkan", "--threads", "2",
               "--voice-ref", REF, "--reference-text", "",
               "--text", text, "--seed", str(seed), "--out", out,
               "--request-option", "max_tokens=228",
               "--session-option", "dots_tts.mem_saver=true", "--metrics"]
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=900)
        dt = time.time() - t0
        ok = os.path.exists(out) and os.path.getsize(out) > 50000
        print(f"{tag} {'OK' if ok else 'FAIL'} {dt:.1f}s", flush=True)
        if not ok:
            print((r.stderr or r.stdout or '')[-600:], flush=True)
    if os.path.exists(out):
        rep.append(dict(tag=tag, text=text, seed=seed, wav=out,
                        bytes=os.path.getsize(out)))
json.dump(rep, open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('done', len(rep))
