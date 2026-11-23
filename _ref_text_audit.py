# -*- coding: utf-8 -*-
"""参考体检：参考音频里到底说的是什么，和 ref_text 对不对得上。

背景（2026-11-22）：Joseph 的正文生成时开头多念 7 个词，一直以为是 demucs 净化或
reference-text 与音频长度不匹配导致。实测发现**参考音频的内容与 ref_text 根本不是同一句**：

    c1028 声称 "It's by Henri King on the death of his wife."
    whisper 听到 "It's not a good idea to do that. It's a good idea to do that."

所以 lead 的真因是 ref_text 错配，不是净化。

本脚本对 _ref9/*.wav 全部跑 whisper(small.en)，与 _index_srt.json 的 text 比对，
输出字符级覆盖率，指出哪些参考的文本要换。
"""
import argparse
import glob
import json
import os
import re
import sys

import numpy as np

ROOT = "G:/_setup"
IDX = os.path.join(ROOT, "_ref9", "_index_srt.json")


def norm(s):
    s = (s or "").lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"[^a-z' ]", " ", s)


def lcs_cov(gold, hyp):
    """gold 的字符有多少按顺序出现在 hyp 里"""
    a = norm(gold).replace(" ", "")
    b = norm(hyp).replace(" ", "")
    if not a:
        return 0.0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b):
            cur.append(prev[j] + 1 if ca == cb else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1] / len(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑匹配的文件名片段，逗号分隔")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--out", default=os.path.join(ROOT, "_ref_text_audit.json"))
    ap.add_argument("--patch", action="store_true", help="把 whisper 转写写回 _index_srt.json")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    mdl = a.model
    if a.lang != "en" and mdl.endswith(".en"):
        mdl = mdl[:-3]          # small.en 只能解英语，法语要用 small
    print("加载 whisper %s (lang=%s) ..." % (mdl, a.lang))
    m = WhisperModel(mdl, device="cpu", compute_type="int8")

    idx = json.load(open(IDX, encoding="utf-8"))
    files = sorted(glob.glob(os.path.join(ROOT, "_ref9", "*.wav")))
    rows = []
    for p in files:
        name = os.path.basename(p)[:-4]
        if a.only and not any(k in name for k in a.only.split(",")):
            continue
        gold = (idx.get(name) or {}).get("text", "")
        segs, _info = m.transcribe(p, language=a.lang, beam_size=5, vad_filter=True)
        hyp = " ".join(s.text.strip() for s in segs).strip()
        cov = lcs_cov(gold, hyp)           # 现有文本被音频覆盖多少
        cov2 = lcs_cov(hyp, gold)          # 音频内容有多少能在文本里找到
        rows.append({"ref": name, "dur": (idx.get(name) or {}).get("dur"),
                     "cov_gold_in_audio": round(cov, 3), "cov_audio_in_gold": round(cov2, 3),
                     "gold": gold, "heard": hyp})

    rows.sort(key=lambda r: r["cov_gold_in_audio"])
    print("\n%-24s %6s %7s %7s" % ("ref", "dur", "gold⊂aud", "aud⊂gold"))
    for r in rows:
        flag = "  ← 错配" if r["cov_gold_in_audio"] < 0.75 else ""
        print("%-24s %6s %7.2f %7.2f%s" % (r["ref"], r["dur"],
                                           r["cov_gold_in_audio"], r["cov_audio_in_gold"], flag))
    bad = [r for r in rows if r["cov_gold_in_audio"] < 0.75]
    print("\n错配 %d/%d 组" % (len(bad), len(rows)))
    for r in bad:
        print("\n  [%s]" % r["ref"])
        print("    声称: %s" % r["gold"][:150])
        print("    听到: %s" % r["heard"][:150])

    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n→ %s" % a.out)

    if a.patch:
        n = 0
        for r in bad:
            if r["heard"] and r["cov_gold_in_audio"] < 0.75:
                idx[r["ref"]]["text_asr"] = r["heard"]
                idx[r["ref"]]["text"] = r["heard"]
                n += 1
        json.dump(idx, open(IDX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("已把 %d 组的 ref_text 换成 whisper 转写 → %s" % (n, IDX))


if __name__ == "__main__":
    main()
