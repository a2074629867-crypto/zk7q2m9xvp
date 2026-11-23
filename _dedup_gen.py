"""① c2_0325 换柔和参考重生成（平静却像喊）② 13 条重复音频按不同 seed 重生成。"""
import json
import os
import subprocess
import sys

PY = "G:/Python310/python.exe"
S = "G:/_setup"
seeds = {
    "c2_0263": 3, "c2_0283": 5, "c3_0851": 7, "c3_0855": 11,
    "c3_0863": 13, "c3_0867": 17, "c1_0014": 19, "c2_0294": 23,
    "c2_0268": 29, "c3_0814": 31, "c2_0281": 37, "c2_0366": 41, "c3_0865": 43,
}


def run(cmd):
    print("+ " + " ".join(cmd), flush=True)
    p = subprocess.run(cmd, cwd=S, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((p.stdout or "")[-400:], flush=True)
    if p.returncode:
        print("RC=%d %s" % (p.returncode, (p.stderr or "")[-300:]), flush=True)


def main():
    # ① c2_0325：平静但 voiced-tilt 0.397（像喊），换 c039 中性参考 + 载体短语
    run([PY, "-u", "_gen_tail.py", "--id", "c2_0325b", "--text", "We lived in Wales.",
         "--ref", "G:/_setup/castle_cues/c039_362.4_363.9.wav",
         "--ref-text", "Non, ça va mieux maintenant.",
         "--seeds", "7,11,23", "--out", "G:/_setup/_sweep/cand26"])
    # ② 13 条重复音频：每条一个不同 seed
    for rid, sd in seeds.items():
        run([PY, "-u", "_seed_sweep.py", "--ids", rid, "--seeds", str(sd),
             "--cand-dir", "G:/_setup/_sweep/cand27"])
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
