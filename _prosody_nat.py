# -*- coding: utf-8 -*-
"""韵律自然度评测（开源路线，CPU 可跑）。

为什么不用 TTScore / SpeechJudge：
  - TTScore（arXiv 2509.20485）仓库只有一行 "code will be available soon" ⇒ 无代码，判无参考价值。
  - SpeechJudge-GRM 是 Qwen2.5-Omni-7B 微调（11B），本机只有 CPU ⇒ 不可用。
所以走 **SpeechBERTScore**（arXiv 2309.07723）的开源思路：
  用自监督语音模型（WavLM）的第 11 层特征做贪心最大匹配，得到 ref 与 cand 的相似度。
它衡量的是「韵律/音色/内容的整体序列是否还对得上」，不需要文本，不需要 GPU。

再加两个纯物理量的韵律结构指标（这两条是给我们踩过的坑量身定的）：
  gap_in_word  —— 词内部的断裂（N0627 rate 版在词中间插了 0.18s 空档）
  f0_rev       —— 词内 F0 斜率反转率（每 0.1s 反转次数），抓「抖」

⚠️ 任何指标先用 --calib 验证区分度。区分不出来就写进文档说不可用，不许当摆设。
"""
import os
import sys
import json
import math
import hashlib
import argparse

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CACHE = os.path.join(HERE, "_prosody_nat_cache")
os.makedirs(CACHE, exist_ok=True)

SSL_MODEL = "microsoft/wavlm-base-plus"
SSL_LAYER = 11
SR = 16000

_model = None
_fe = None


def _md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _load():
    global _model, _fe
    if _model is not None:
        return _model, _fe
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    import torch
    from transformers import AutoModel, AutoFeatureExtractor
    torch.set_num_threads(4)
    _fe = AutoFeatureExtractor.from_pretrained(SSL_MODEL)
    _model = AutoModel.from_pretrained(SSL_MODEL)
    _model.eval()
    return _model, _fe


def ssl_embed(path, use_cache=True):
    """WavLM 第 11 层隐状态，[T, D]，L2 归一化前。按 md5 缓存。"""
    key = os.path.join(CACHE, _md5(path) + "_l%d.npy" % SSL_LAYER)
    if use_cache and os.path.exists(key):
        return np.load(key)
    import torch
    import librosa
    model, fe = _load()
    y, _sr = librosa.load(path, sr=SR, mono=True)
    if y.size < SR * 0.2:                     # 短于 0.2 s 补零，否则卷积层报错
        y = np.pad(y, (0, int(SR * 0.2) - y.size))
    x = fe(y, sampling_rate=SR, return_tensors="pt")
    with torch.no_grad():
        out = model(**x, output_hidden_states=True)
    h = out.hidden_states[SSL_LAYER][0].numpy().astype(np.float32)
    np.save(key, h)
    return h


def _norm(a):
    n = np.linalg.norm(a, axis=1, keepdims=True)
    n[n < 1e-9] = 1e-9
    return a / n


def ssl_sim(a, b):
    """SpeechBERTScore 式贪心匹配：cos 最大的一对一匹配，取 P/R/F1。"""
    A, B = _norm(ssl_embed(a)), _norm(ssl_embed(b))
    S = A @ B.T
    pa = S.max(axis=1).mean()      # 每个 a 帧都能在 b 里找到对应
    pr = S.max(axis=0).mean()
    f1 = 2 * pa * pr / max(pa + pr, 1e-9)
    return dict(p=round(float(pa), 4), r=round(float(pr), 4), f1=round(float(f1), 4))


# ---------------- 停顿结构 ----------------

def gap_stats(path, prom, text, min_gap=0.06):
    """词内断裂 + 词间停顿。

    gap_in_word_max  一个词内部最大的无声间隔（秒）—— 正常连读不该出现 >0.06 s
    gap_in_word_sum  所有词内断裂之和
    gap_between_med  词与词之间的停顿中位
    """
    import _f0_accent as F
    import _adv_align as A

    ts, fs, dur = F.track(path)
    rows = F.read_prom(prom)
    spans = A.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    tw = A.text_words(text)

    in_word, between = [], []
    prev_end = None
    for i, w in enumerate(tw):
        if not w["is_word"]:
            continue
        sp = spans[i]
        if sp["t0"] is None:
            continue
        seg = ts[(ts >= sp["t0"]) & (ts < sp["t1"])]
        if seg.size >= 2:
            d = np.diff(seg)
            # 只认「真有语音在两侧」的断裂：断开处前后各至少 3 帧有声
            for j in np.where(d >= min_gap)[0]:
                if j >= 2 and (seg.size - j - 1) >= 3:
                    in_word.append(float(d[j]))
        if prev_end is not None:
            between.append(max(0.0, float(sp["t0"]) - prev_end))
        prev_end = float(sp["t1"])

    return dict(
        gap_in_word_n=len(in_word),
        gap_in_word_max=round(max(in_word), 3) if in_word else 0.0,
        gap_in_word_sum=round(sum(in_word), 3),
        gap_between_med=round(float(np.median(between)), 3) if between else None,
        gap_between_max=round(max(between), 3) if between else None,
    )


def f0_smooth(path, prom, text):
    """词内 F0 斜率反转率：每 0.1 s 内一阶差分改变符号的次数。抖 = 高。

    低频段（<80Hz）parselmouth 容易出错，反转率会虚高，所以同时给出低频帧占比。
    """
    import _f0_accent as F
    import _adv_align as A

    ts, fs, dur = F.track(path)
    rows = F.read_prom(prom)
    spans = A.word_spans(text, [(r[2], r[0], r[1], 0.0, 0.0) for r in rows])
    tw = A.text_words(text)

    rev, n_words, low = 0, 0, 0
    st = 12.0 * np.log2(np.maximum(fs, 1e-6) / max(float(np.median(fs)), 1e-6))
    for i, w in enumerate(tw):
        if not w["is_word"]:
            continue
        sp = spans[i]
        if sp["t0"] is None:
            continue
        sel = (ts >= sp["t0"]) & (ts < sp["t1"])
        if sel.sum() < 5:
            continue
        n_words += 1
        s = st[sel]
        d = np.diff(s)
        d = d[np.abs(d) > 0.05]                     # 忽略平坦段
        if d.size >= 2:
            rev += int((np.diff(np.sign(d)) != 0).sum())
        low += int((fs[sel] < 80).sum())
    voiced = int(np.isfinite(fs).sum())
    speech = max(float(voiced) * F.FRAME, 1e-9)
    return dict(
        f0_rev=rev,
        f0_rev_per100ms=round(rev / max(speech * 10.0, 1e-9), 3),
        low_hz_share=round(low / max(voiced, 1), 4),
        n_words=n_words,
    )


def naturalness(path, prom, text, ref=None):
    """一条的完整自然度画像。ref 给定时附上 SSL 相似度。"""
    out = dict(wav=path)
    try:
        out.update(gap_stats(path, prom, text))
    except Exception as e:
        out["gap_err"] = str(e)[:120]
    try:
        out.update(f0_smooth(path, prom, text))
    except Exception as e:
        out["f0_err"] = str(e)[:120]
    if ref:
        try:
            out["ssl"] = ssl_sim(ref, path)
        except Exception as e:
            out["ssl_err"] = str(e)[:120]
    return out


# ---------------- 标定：同一条音频切半互比，得到 SSL 相似度的噪声底 ----------------

def calib(paths, out=None):
    rows = []
    for k, p in enumerate(paths, 1):
        try:
            import librosa
            y, _ = librosa.load(p, sr=SR, mono=True)
            n = len(y)
            if n < SR * 1.0:
                rows.append(dict(wav=p, skip="太短"))
                continue
            half = n // 2
            tmpdir = os.path.join(CACHE, "half")
            os.makedirs(tmpdir, exist_ok=True)
            import soundfile as sf
            a = os.path.join(tmpdir, _md5(p)[:10] + "_a.wav")
            b = os.path.join(tmpdir, _md5(p)[:10] + "_b.wav")
            sf.write(a, y[:half], SR)
            sf.write(b, y[half:], SR)
            rows.append(dict(wav=os.path.basename(p),
                             half_ssl=ssl_sim(a, b),
                             self_ssl=ssl_sim(p, p)))
        except Exception as e:
            rows.append(dict(wav=p, err=str(e)[:100]))
        if k % 10 == 0:
            print("  %d/%d" % (k, len(paths)), flush=True)
    ok = [r["half_ssl"]["f1"] for r in rows if r.get("half_ssl")]
    if ok:
        ok.sort()
        print("\n同一条音频 前半 vs 后半  SSL-F1：")
        print("  n=%d  中位 %.3f  p5 %.3f  p25 %.3f  最低 %.3f"
              % (len(ok), float(np.median(ok)), ok[int(0.05 * (len(ok) - 1))],
                 ok[int(0.25 * (len(ok) - 1))], ok[0]))
    if out:
        json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("写出 %s" % out)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calib", nargs="*", help="标定：给一批 wav，测切半 SSL 相似度")
    ap.add_argument("--out", default=None)
    ap.add_argument("--wav")
    ap.add_argument("--prom")
    ap.add_argument("--text")
    ap.add_argument("--ref", default=None, help="参照 wav（算 SSL 相似度）")
    a = ap.parse_args()

    if a.calib:
        calib(a.calib, a.out)
        return
    if a.wav and a.prom and a.text:
        r = naturalness(a.wav, a.prom, a.text, a.ref)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
