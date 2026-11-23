# -*- coding: utf-8 -*-
"""Parakeet 词级时间戳 → 挂到 DF3 切片 → 出 GSV 训练用 .list

思路：
  1. 读 wonder_parakeet.json 的 486 个 VAD 段边界（文本已交叉验证 94.4% 一致）
  2. 在**原始音频**上逐段重跑 with_timestamps()（VAD 链会丢时间戳，所以自己分段）
  3. 子词 token 合并成词（token 以空格开头 = 新词；否则附着到前词，保留标点）
  4. 每个词按**中点**归属到 slices_df3 的某个切片
  5. 每片按序拼词 → .list（file|Calm|en|text）+ .json（含诊断信息）
"""
import argparse
import json
import os
import re
import time
import wave

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402

MODEL_DIR = "G:/_setup/models/parakeet-v3-int8"


def read_wav16(p):
    with wave.open(p, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, "需要 16k 单声道"
        n = w.getnframes()
        raw = w.readframes(n)
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0, 16000


def merge_tokens(tokens, times):
    """子词 → 词。返回 [(word, t_start, t_end)]"""
    words = []
    cur, cs, ce = "", None, None
    for tok, t in zip(tokens, times):
        if tok.startswith(" ") or cur == "":
            if cur:
                words.append((cur, cs, ce))
            cur, cs, ce = tok.strip(), t, t
        else:
            cur += tok
            ce = t
    if cur:
        words.append((cur, cs, ce))
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr-json", default="G:/GPT-SoVITS/_dataset_v5full/wonder_parakeet.json")
    ap.add_argument("--wav", default="G:/_setup/_verify/wonder_full_16k.wav")
    ap.add_argument("--slices-json", default="G:/GPT-SoVITS/_dataset_v5full/slices_df3.json")
    ap.add_argument("--out", default="G:/GPT-SoVITS/_dataset_v5full/wonder_v5full_parakeet.list")
    ap.add_argument("--json", default="G:/GPT-SoVITS/_dataset_v5full/wonder_parakeet_words.json")
    args = ap.parse_args()

    so = ort.SessionOptions()
    so.log_severity_level = 3
    import onnx_asr  # noqa: E402
    model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", MODEL_DIR, quantization="int8",
                                providers=[("DmlExecutionProvider", {"device_id": 0})],
                                sess_options=so).with_timestamps()
    print("模型就绪", flush=True)

    segs = json.load(open(args.asr_json, encoding="utf-8"))["segments"]
    x, sr = read_wav16(args.wav)
    print("音频 %.1fs | VAD 段 %d" % (len(x) / sr, len(segs)), flush=True)

    all_words = []   # (t_start, t_end, word)
    nfail = 0
    t0 = time.time()
    # 实测坑：1.19s 长度的输入会产出空结果；不加 pad 或用较大 pad 都正常。
    # 所以先按 VAD 原边界跑，空则逐级加大上下文重试。
    PADS = [0.0, 0.6, 1.2]
    for i, s in enumerate(segs):
        got = None
        for pad in PADS:
            a = max(0.0, s["start"] - pad)
            b = min(len(x) / sr, s["end"] + pad)
            chunk = x[int(a * sr): int(b * sr)]
            if len(chunk) < sr // 10:
                continue
            try:
                r = model.recognize(chunk, sample_rate=sr)
            except Exception as e:
                print("  段 %d pad=%.1f 失败: %s" % (i, pad, str(e)[:60]), flush=True)
                continue
            tk = getattr(r, "tokens", None)
            ts = getattr(r, "timestamps", None)
            if tk and ts:
                got = (a, tk, ts)
                break
        if got is None:
            nfail += 1
            continue
        a, tk, ts = got
        for w, ws, we in merge_tokens(tk, ts):
            all_words.append((a + ws, a + we, w))
        if i % 100 == 0:
            print("  %3d/%d  已用 %.0fs  累计词 %d  失败 %d"
                  % (i, len(segs), time.time() - t0, len(all_words), nfail), flush=True)

    all_words.sort(key=lambda t: t[0])
    print("\n取到 %d 词 / %.0fs / 失败段 %d" % (len(all_words), time.time() - t0, nfail), flush=True)

    # 挂到切片
    SJ = json.load(open(args.slices_json, encoding="utf-8"))
    slices = sorted(SJ["slices"], key=lambda s: s["t0"])
    bounds = [s["t0"] for s in slices] + [slices[-1]["t1"]]
    for s in slices:
        s["words"] = []
    dropped = 0
    for ws, we, w in all_words:
        mid = (ws + we) / 2
        k = None
        for j in range(len(slices)):
            if slices[j]["t0"] <= mid < slices[j]["t1"]:
                k = j
                break
        if k is None:
            if mid < bounds[0] or mid >= bounds[-1]:
                dropped += 1
                continue
            k = len(slices) - 1
        slices[k]["words"].append(w)

    # 输出
    nw, nempty = 0, 0
    with open(args.out, "w", encoding="utf-8") as f:
        for s in slices:
            txt = " ".join(s["words"]).strip()
            txt = re.sub(r"\s+", " ", txt)
            s["text"] = txt
            if not txt:
                nempty += 1
                continue
            nw += len(txt.split())
            f.write("%s|Calm|en|%s\n" % (s["file"], txt))
    print("写出 %s" % args.out, flush=True)
    print("切片 %d | 有词 %d | 空片 %d | 总词 %d | 落在切片外被丢 %d"
          % (len(slices), len(slices) - nempty, nempty, nw, dropped), flush=True)

    json.dump(dict(slices=slices, n_words=nw, n_empty=nempty, dropped=dropped),
              open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s" % args.json, flush=True)

    print("\n前 8 片：", flush=True)
    for s in slices[:8]:
        print("  [%7.2f-%7.2f] %s" % (s["t0"], s["t1"], s["text"][:100]), flush=True)
    print("\n空片文件:", [s["file"] for s in slices if not s["text"]][:15], flush=True)


if __name__ == "__main__":
    main()
