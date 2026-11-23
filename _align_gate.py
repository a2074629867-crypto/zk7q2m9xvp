# -*- coding: utf-8 -*-
"""吞字 / 发音不准检测（CTC 强制对齐）。

为什么不能再靠 ASR
------------------
用户 2026-11-21：「很多字都吞了，很多音没发好」。
但我们自己的双 ASR（Parakeet 覆盖率 + whisper 召回）把这 10 条全判成 1.00/0.94 ——
因为**语言模型会替吞掉的音补上下文**：一段只发了半个音的词，ASR 照样输出正确单词。
业界（Forced Alignment for TTS，2026）对此的原话是：
  «Round-Trip ASR … Word Skipping Detection: Poor (language model fills gap)»
  «Forced Alignment … Phoneme-Level Accuracy: High (Sub-millisecond resolution)»

所以改用「把 gold 文本硬对齐到声学帧」的做法：
  wav2vec2-960h 输出逐帧字符后验 → torchaudio.forced_align 求单调路径
  → merge_tokens 得到每个字符的 [起始帧, 结束帧, 该段平均后验]

三个量直接对应三种病症：
  · 字符跨度异常短（1 帧 = 20ms）  → 吞音（口型没做完就过去了）
  · 字符平均后验低（<0.35）        → 发音含糊/含糊带过
  · 整个词的所有字符跨度之和 < 60ms → 整词被吞

用法：
  G:/Python310/python.exe -u _align_gate.py --wav X.wav --text "原文"
  G:/Python310/python.exe -u _align_gate.py --ids c2_0246,c3_0922 --dir _audio_ch123/out_paused
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import torch
import torchaudio

# 本机是嵌入式 Python（G:/Python310/python310._pth），**不会**自动把脚本目录加进 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as _P      # 路径集中管理：本机默认 G:/_setup，云上按 MR_ROOT

ROOT = _P.ROOT
MODEL = "facebook/wav2vec2-base-960h"
FRAME_MS = 20.0


def load_model():
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
    proc = Wav2Vec2Processor.from_pretrained(MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    return proc, model


def norm_text(text):
    """只留 A-Z 与单个空格。

    2026-11-21 实测：撇号在 960h 词表里不是独立字母，会变成 <unk>，
    对齐时 <unk> 的分数被拉到 −31.9，假的「吞音」。而撇号本来就不发音，
    去掉它不影响音素判断（THEY'RE → THEYRE）。
    """
    t = (text or "").upper().replace("\u2019", "'")
    t = re.sub(r"[^A-Z ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def to_tokens(proc, text):
    """gold 文本 → (字符列表, token id 列表)。只用模型词表里存在的字符。"""
    t = norm_text(text)
    ids = proc.tokenizer(t).input_ids
    vocab = proc.tokenizer.get_vocab()
    special = {vocab.get("<s>"), vocab.get("</s>"), vocab.get("</s>")}
    ids = [i for i in ids if i not in special]
    chars = [proc.tokenizer.convert_ids_to_tokens(i) for i in ids]
    return chars, ids


def align(proc, model, wav_path, text):
    wav, sr = torchaudio.load(wav_path)
    wav = wav.mean(0, keepdim=True).float()
    if sr != 16000:
        wav = torchaudio.functional.resample(wav, sr, 16000)
    if wav.abs().max() > 1.0:
        wav = wav / (wav.abs().max() + 1e-8)
    with torch.no_grad():
        logits = model(wav).logits          # (1, T, V)
    logp = torch.log_softmax(logits, dim=-1)

    # 贪心解码：这是一个"不看语言模型"的纯声学朗读结果。
    # 它比 Parakeet/whisper 更能暴露吞音 —— 后两者会用上下文把没发的音补上。
    argm = torch.argmax(logits, dim=-1)[0].tolist()
    greedy = proc.tokenizer.decode(argm)

    # 贪心路径的**逐字符时间戳**：连续同 id 的帧合成一个字符。
    # forced_align 的 tokens 只包含 gold 文本里的字符，测不出「多念的词」，
    # 而 lead（把参考文本也念出来）恰恰是多出来的 —— 只能从贪心路径取。
    gspans = []
    prev, beg = None, 0
    for i, t in enumerate(argm + [-1]):
        if t != prev:
            if prev not in (None, proc.tokenizer.pad_token_id, 0):
                gspans.append({"tok": proc.tokenizer.convert_ids_to_tokens(prev),
                               "start": beg, "end": i})
            prev, beg = t, i

    chars, ids = to_tokens(proc, text)
    if not ids:
        return None
    targets = torch.tensor([ids], dtype=torch.int32)
    if targets.shape[1] >= logp.shape[1]:
        return None

    aligned, scores = torchaudio.functional.forced_align(logp, targets, blank=0)
    spans = torchaudio.functional.merge_tokens(aligned[0], scores[0])
    vocab = proc.tokenizer.get_vocab()
    inv = {v: k for k, v in vocab.items()}

    toks = []
    for sp in spans:
        tk = inv.get(sp.token, "?")
        toks.append({"tok": tk, "start": sp.start, "end": sp.end,
                     "frames": sp.end - sp.start,
                     "ms": round((sp.end - sp.start) * FRAME_MS, 1),
                     "score": round(float(sp.score), 3)})
    # 整句对齐得分：所有有 token 帧的平均分
    total = float(aligned.shape[1])
    covered = sum(t["frames"] for t in toks)
    return {"tokens": toks, "greedy": greedy, "greedy_spans": gspans,
            "frames": int(total),
            "dur": round(float(total) * FRAME_MS / 1000, 2),
            "covered_ratio": round(covered / max(total, 1), 3)}


def judge(res, word_low=-3.0, char_low=-6.0):
    """判据只用**后验分数**，不用字符跨度。

    2026-11-21 实测结论：wav2vec2-960h 在干净语音上的 CTC 后验非常尖 ——
    每个字符只占 1~2 帧（20~40ms），130 个字符的总跨度也就 3 秒。
    所以「字符跨度短」是模型的正常形态，拿它判吞音会把所有音频判死（实测 13/15 词全中）。
    真正有区分度的是 merge_tokens 给的 segment score（该字符所在帧的平均 log 后验）：
      · 正常字符  −0.00 ~ −2
      · 含糊/漏发 −3 ~ −10
      · 完全没这个音 −10 以下
    词级取该词所有字符的平均分与最低分。
    """
    bad, allw = [], []
    word = []
    words = []
    for t in res["tokens"]:
        if t["tok"] == "|":
            if word:
                words.append(word)
            word = []
        else:
            word.append(t)
    if word:
        words.append(word)

    for w in words:
        txt = "".join(x["tok"] for x in w)
        # 单字符 token 不判：文本去掉撇号后 HAVEN'T → HAVEN T、YOU'LL → YOU LL，
        # 这个 T / LL 本身就是一个塞音或边音，CTC 后验天然低（实测 −11~−13），
        # 报出来全是假警（c2_0487 / c3_0853 各 2 条全是这种）。
        if len(txt) <= 1:
            continue
        sc = float(np.mean([x["score"] for x in w]))
        lo = min(x["score"] for x in w)
        worst = min(w, key=lambda x: x["score"])
        allw.append({"word": txt, "mean": round(sc, 2), "min": round(lo, 2)})
        if sc < word_low or lo < char_low:
            bad.append({"word": txt,
                        "why": "发音含糊 均分%.1f 最低%.1f(%s)" % (sc, lo, worst["tok"]),
                        "score": round(sc, 2)})
    return bad, allw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--text")
    ap.add_argument("--ids", default="")
    ap.add_argument("--dir", default="_audio_ch123/out_paused")
    ap.add_argument("--plan-text", action="store_true", help="从 plan 取原文")
    ap.add_argument("--out", default="")
    ap.add_argument("--dump", action="store_true", help="打印每个词的分数（校准阈值用）")
    a = ap.parse_args()

    proc, model = load_model()

    jobs = []
    if a.wav:
        jobs.append((os.path.basename(a.wav)[:-4], a.wav, a.text))
    else:
        sys.path.insert(0, ROOT)
        import _calm_gate as CG
        plan = CG.load_plan()
        ids = [x.strip() for x in a.ids.split(",") if x.strip()]
        if ids:
            for i in ids:
                p = os.path.join(ROOT, a.dir, "%s.wav" % i)
                if os.path.exists(p):
                    jobs.append((i, p, plan.get(i, {}).get("text") or a.text or ""))
        else:
            # 不给 --ids 就扫整个目录（候选目录里是 c2_0246__s42.wav 这种多 seed 命名，
            # tag 用完整 basename 才不会互相覆盖；rid 取前 7 字符查台词）
            import glob as _g
            for p in sorted(_g.glob(os.path.join(ROOT, a.dir, "*.wav"))):
                b = os.path.basename(p)[:-4]
                rid = b[:7]
                if rid not in plan:
                    continue
                jobs.append((b, p, plan[rid].get("text") or a.text or ""))

    report = []
    for tag, path, text in jobs:
        r = align(proc, model, path, text)
        if r is None:
            print("%-9s 对齐失败（文本过长或为空）" % tag)
            continue
        bad, allw = judge(r)
        r["words"] = allw
        sys.path.insert(0, ROOT)
        import _pick52 as PK
        gold = PK.norm_words(text)
        hyp = PK.norm_words(r["greedy"])
        r["w2v_cov"] = round(PK.coverage(gold, hyp), 3)
        r["w2v_sim"] = round(PK.sim(gold, hyp), 3)
        r["w2v_text"] = r["greedy"]
        r.update(id=tag, rid=tag[:7], wav=path, text=text, issues=bad,
                 ok=not bad)
        report.append(r)
        print("%-9s dur=%.2f 声学覆盖%.0f%% w2v_cov=%.2f 问题%d %s" % (
            tag, r["dur"], r["covered_ratio"] * 100, r["w2v_cov"], len(bad),
            "OK" if not bad else ""))
        print("     w2v: %s" % r["w2v_text"][:120])
        for b in bad:
            print("     %-14s %s (均分%.2f)" % (b["word"], b["why"], b["score"]))
        if a.dump:
            for w in r["words"]:
                print("        %-13s mean%6.2f min%6.2f" % (w["word"], w["mean"], w["min"]))
        if a.out:
            json.dump(report, open(a.out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
