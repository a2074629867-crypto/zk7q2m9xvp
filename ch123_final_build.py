# -*- coding: utf-8 -*-
"""最终链路：原始 ch123 → 降速（同 slow5 规则，tempo 硬底 0.70）→ clean（只整体增益）

与 ch123_v5 的唯一差别：收尾不用 U.limiter（lookahead 会产生增益调制，听感"抽吸/炸"），
改用 CL.clean（单一整体增益 + 仅在会削波时整体回退）。
"""
import glob
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_rebuild as RB
import ch123_slow5 as S
import ch123_clean as CL

SRC = "G:/_setup/ch123"
DST = "G:/_setup/ch123_final"

# 后续单独修复过的条目：这些不在本脚本生成，由 ch123_clean 覆盖回来
FIXED = ["L005", "L017", "L050", "L053", "L054", "L061", "L068", "L075",
         "L078", "L079", "L083", "L084", "L085", "L088"]


def main():
    os.makedirs(DST, exist_ok=True)
    rows = []
    for f in sorted(glob.glob(os.path.join(SRC, "*.wav"))):
        k = os.path.basename(f)[:-4]
        if k not in S.WORDS or k in FIXED:
            continue
        who = S.WHO.get(k, "C")
        n = S.WORDS[k]
        tgt = S.target_of(n, who)
        a, sr = sf.read(f, dtype="float32", always_2d=True)
        a = a.mean(1)
        r0, _ = S.rate_of(a, sr, n)
        dur = len(a) / sr
        tempo = 1.0
        if k in S.EXEMPT:
            tempo = S.EXEMPT[k]
        elif r0 > 0:
            tempo = min(S.TEMPO_MAX, max(S.tempo_floor(n, dur), tgt / r0))
            if dur < 1.05 and tempo < 0.999:
                tempo = max(S.TEMPO_FLOOR, min(tempo, dur / 1.05))
        # ★ 一律 stretch_whole（RAG 账本「禁 stretch_segments」定稿）：
        #   stretch_segments 在某段 <0.4s 时于边界造伪影，NISQA DIS 掉 2.4 分
        #   （L014 4.18→1.81），改 whole 回 4.53。原来是 whole 只在
        #   (dur<1.1) 或 (n<=6 and dur<2.2) 时用，其余走 segments ⇒ 多数长条重踩。
        #   narr_post.py 一直是全 stretch_whole，所以旁白链没踩这条。
        if abs(tempo - 1.0) > 0.045:
            y = S.stretch_whole(a, sr, tempo, k)
        else:
            y = a
        y = CL.clean(y, sr)
        sf.write(os.path.join(DST, k + ".wav"), y, sr, subtype="PCM_16")
        r1, _ = S.rate_of(y, sr, n)
        rows.append((k, who, n, r0, r1, tempo, len(y) / sr))
        print("%-5s %s %2d词 %5.0f → %5.0f wpm  tempo %.3f  %5.2fs"
              % (k, who, n, r0, r1, tempo, len(y) / sr), flush=True)

    print("\n生成 %d 条（另有 %d 条走 FIXED 覆盖）" % (len(rows), len(FIXED)))


if __name__ == "__main__":
    main()
