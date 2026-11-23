# -*- coding: utf-8 -*-
"""全量发音终检：原版 vs 拆句版，逐条词级 diff + 判定。

    asr_venv/Scripts/python.exe bk_final_check.py
"""
import difflib
import json
import os
import sys

import onnx_asr
import onnxruntime as ort

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bk_asr_check as B

OUT = "G:/_setup/dots_edit2"

# 允许的口音/专名偏差：不算错
ACCENT_OK = {
    ("st", "vincent's"), ("saint", "vicence"), ("saint", "vincent"),
    ("kingshaw",), ("king", "shaw"),
    ("scaredy",), ("scarity",), ("scardy",),
    ("mummy's",), ("mommy's",),
    ("want", "to"), ("wanna",),
}


def judge(bad_pairs):
    hard, soft = [], []
    for ref_seg, asr_seg in bad_pairs:
        rw = ref_seg.split()
        aw = asr_seg.split()
        # 纯人名/口音类
        joined = " ".join(rw + aw).lower()
        if any(k in joined for k in ("vincent", "vicence", "kingshaw", "king shaw",
                                     "scaredy", "scarity", "scardy", "mummy", "mommy")):
            soft.append((ref_seg, asr_seg))
        elif set(aw) <= set(rw) or not aw:
            soft.append((ref_seg, asr_seg))   # 漏词/吞音
        else:
            hard.append((ref_seg, asr_seg))
    return hard, soft


def main():
    so = ort.SessionOptions()
    so.log_severity_level = 3
    m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
                            quantization="int8",
                            providers=[("CPUExecutionProvider", {})], sess_options=so)
    rows = []
    for tag, name, ref in B.LINES:
        for suffix, label in (("", "原版"), ("_r", "拆句版")):
            p = os.path.join(OUT, "BK_%s%s.wav" % (tag, suffix))
            if not os.path.exists(p):
                continue
            a, sr = B.rd(p)
            hyp = (m.recognize(B.r16(a, sr)) or "").strip()
            rw, hw = B.norm(ref), B.norm(hyp)
            sm = difflib.SequenceMatcher(None, rw, hw)
            pairs = []
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op == "equal":
                    continue
                pairs.append((" ".join(rw[i1:i2]), " ".join(hw[j1:j2])))
            hard, soft = judge(pairs)
            rows.append(dict(tag=tag, name=name, label=label, file=os.path.basename(p),
                             dur=round(len(a) / sr, 2), acc=round(sm.ratio() * 100),
                             ref=ref, asr=hyp, hard=hard, soft=soft))
            mark = "OK " if not hard else "BAD"
            print("%s BK_%-3s %-6s %5.2fs %3d%%  %s" %
                  (mark, tag, label, len(a) / sr, sm.ratio() * 100,
                   "; ".join("%s->%s" % x for x in hard) or "-"), flush=True)
    with open("G:/_setup/_bk_final_check.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print("\nBAD:", sum(1 for r in rows if r["hard"]), "/", len(rows))


if __name__ == "__main__":
    main()
