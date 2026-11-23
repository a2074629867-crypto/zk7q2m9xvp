#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""降 arousal 可行性探针：不改 TTS，只用后期处理把 base 音频变慢/变低，
看 VAD 维度模型的 A 是否真的会降。用于回答「sad 能不能救」。"""
import os, sys, json, subprocess, shutil

FF = "E:/tool/oopz/ffmpeg.exe"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "var")
os.makedirs(OUT, exist_ok=True)

# 只测 4 个 ref，覆盖最低 A(C_normal) 到最高 A(E_loud)
SRC = ["C_normal", "C_soft", "E_loud", "E_calm"]

# 变体: name -> ffmpeg -af
VARS = {
    "slow80":    "atempo=0.80",                                  # 只慢，音高不变
    "slow_lo3":  "asetrate={sr}*0.84,aresample={sr}",            # 慢+降 3 半音（时长×1.19）
    "slow_lo5":  "asetrate={sr}*0.75,aresample={sr}",            # 慢+降 5 半音（时长×1.33）
}


def probe_sr(p):
    import soundfile as sf
    return sf.info(p).samplerate


def main():
    made = []
    for pid in SRC:
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "gen",
                           "%s__base__s2051.wav" % pid)
        if not os.path.exists(src):
            print("MISS", src); continue
        sr = probe_sr(src)
        for name, af in VARS.items():
            dst = os.path.join(OUT, "%s__%s.wav" % (pid, name))
            cmd = [FF, "-y", "-v", "error", "-i", src, "-af", af.format(sr=sr),
                   "-c:a", "pcm_s16le", dst]
            subprocess.run(cmd, capture_output=True)
            if os.path.exists(dst):
                made.append({"pid": pid, "var": name, "path": dst})
            else:
                print("FAIL", dst)
    with open(os.path.join(OUT, "_index.jsonl"), "w", encoding="utf-8") as f:
        for m in made:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print("made", len(made))


if __name__ == "__main__":
    main()
