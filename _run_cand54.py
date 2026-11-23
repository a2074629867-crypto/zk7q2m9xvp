# -*- coding: utf-8 -*-
"""把 cand54 补齐（断点续跑：已有 >50KB 的 take 会 SKIP）。

只补两个缺的：c3_0861__s11 / c2_0312__s42。
参考固定为 castle_fr_ref/1_charles_normal.wav（48k / 13.58s / 用户手切 8 段拼接），
参考文本用 SRT 逐句校正版（见 _build_listen_page.py 顶部注释）。
"""
import subprocess
import sys

PY = r"G:/Python310/python.exe"
SCRIPT = r"G:/_setup/_regen_native.py"
IDS = "c2_0246,c2_0279,c2_0299,c2_0312,c2_0368,c2_0487,c3_0853,c3_0861,c3_0876,c3_0922"
REF = r"G:/_setup/castle_fr_ref/1_charles_normal.wav"
REF_TEXT = ("Je suis né comme ça aussi? Vous êtes Monsieur Bréaud? "
            "Moi, je suis Charles Vernet. Non. Ça va mieux, maintenant. Non, monsieur. "
            "Et si elle, elle vous aime pas? Laisse. C'est moi qui t'invite. "
            "Je suis encore très riche.")

cmd = [PY, "-u", SCRIPT,
       "--ids", IDS, "--seeds", "11,42",
       "--out", r"G:/_setup/_sweep/cand54",
       "--ref", REF, "--ref-text", REF_TEXT,
       "--threads", "2"]
print("RUN:", " ".join(cmd), flush=True)
r = subprocess.run(cmd, cwd=r"G:/_setup")
print("EXIT", r.returncode, flush=True)
sys.exit(r.returncode)
