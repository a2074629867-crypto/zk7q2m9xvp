# -*- coding: utf-8 -*-
"""把 `_ref9/_index.json` 里各段的参考文本换成 SRT 原文。

为什么必须换
------------
`_ref9` 的 text 是当初用 Parakeet 听写出来的，就是「吞字」的根因一：
官方 dots.tts 排查清单第一条 —— 「出现漏字/读错 → `--prompt-text` 与音频内容
不匹配，逐字对齐」。实测 13.58s 那条参考 ASR 猜错 3 处：

    ASR "Moi aussi, je suis né comme ça."   SRT i=25  "Je suis né comme ça aussi?"
    ASR "Vous êtes Monsieur Breaud ?"       SRT i=33  "Vous êtes M. Bréaud?"
    ASR "Et si elle ne vous aime pas ?"     SRT i=357 "Et si elle, elle vous aime pas?"

`castle_cues/c<i>_<t0>_<t1>.wav` 的文件名里带 SRT 序号 i，能直接查回原文。
voice_lib 里的条目没有序号，保持原文本（那些是用户当初自己给的）。

输出 `_ref9/_index_srt.json`，结构同 `_index.json`，只改 "text"。
"""
import io
import json
import os
import re

ROOT = "G:/_setup"
IDX = os.path.join(ROOT, "_ref9", "_index.json")
SRT = os.path.join(ROOT, "castle_srt_cues.json")
OUT = os.path.join(ROOT, "_ref9", "_index_srt.json")


def cue_i(path):
    """castle_cues/c185_2051.8_2056.7.wav → 185；其它返回 None。"""
    b = os.path.basename(path)
    m = re.match(r"^c(\d+)_[\d.]+_[\d.]+\.wav$", b)
    return int(m.group(1)) if m else None


def clean(t):
    t = (t or "").replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", "").replace("\u201d", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def main():
    idx = json.load(io.open(IDX, encoding="utf-8"))
    srt = json.load(io.open(SRT, encoding="utf-8"))
    byi = {x["i"]: x["text"] for x in srt}

    changed = 0
    for key, v in idx.items():
        parts = []
        for p in v["parts"]:
            i = cue_i(p["path"])
            t = clean(p.get("text"))
            if i is not None and i in byi:
                t2 = clean(byi[i])
                if t2 and t2 != t:
                    p["was"] = t
                    t = t2
                    changed += 1
            p["text"] = t
            parts.append(t)
        v["text"] = " ".join(parts)

    json.dump(idx, io.open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("校正 %d 段 → %s（%d 组）" % (changed, OUT, len(idx)))
    for k in ("Charles_neutral", "Charles_excited", "Thomas_nervous"):
        if k in idx:
            print("\n== %s  %.2fs" % (k, idx[k]["dur"]))
            print("   " + idx[k]["text"][:220])


if __name__ == "__main__":
    main()
