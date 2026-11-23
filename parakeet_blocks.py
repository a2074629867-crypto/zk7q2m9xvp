# -*- coding: utf-8 -*-
"""
Parakeet 分块转写（VAD 段合并）—— 兼顾上下文长度与不漏段。

背景（实测）：
  - 无 VAD 喂 14s  -> 丢词（'drifted to' 少一个 off）
  - 无 VAD 喂 30s  -> 全对
  - 无 VAD 喂 120s -> 低能量段整段跳过（1196.5-1212.9s 16 秒丢失）
  - VAD 逐段喂    -> 退化（'sleeps'->'sleep'、'of dreams'->'A dream'）
=> 块要"够长但不过长"。做法：用 VAD 段边界做切点，把连续 VAD 段合并成 <=MAXS 的块，
   块内不加 VAD 直接转写。块边界落在真实停顿上 => 不会切在词中间。

用法：
  python parakeet_blocks.py --wav <16k> --vad-json <VAD段json> --slices-json <json>
                            --sliced-dir <dir> --out <前缀> [--maxs 28]
"""
import argparse
import json
import os
import time

import numpy as np
import wave

import onnxruntime as ort
import onnx_asr

MODEL_NAME = 'nemo-parakeet-tdt-0.6b-v3'
MODEL_DIR = 'G:/_setup/models/parakeet-v3-int8'
SR = 16000


def read_wav16k(path):
    with wave.open(path, 'rb') as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    assert sr == SR
    return np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0


def merge_tokens(tokens, times):
    """子词合并：token 以空格开头 = 新词；否则附着前词"""
    words = []
    cur = ''
    ws = we = None
    for tok, t in zip(tokens, times):
        if tok.startswith(' ') or not cur:
            if cur.strip():
                words.append((ws, we, cur.strip()))
            cur = tok.strip()
            ws = we = t
        else:
            cur += tok
            we = t
    if cur.strip():
        words.append((ws, we, cur.strip()))
    return words


def build_blocks(vad_segs, maxs, total):
    """把 VAD 段合并成 <= maxs 的块（块边界取 VAD 段边界）"""
    blocks = []
    cur_a = None
    cur_b = None
    for s in vad_segs:
        a, b = s['start'], s['end']
        if cur_a is None:
            cur_a, cur_b = a, b
            continue
        if b - cur_a <= maxs:
            cur_b = b
        else:
            blocks.append((cur_a, cur_b))
            cur_a, cur_b = a, b
    if cur_a is not None:
        blocks.append((cur_a, cur_b))
    return blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wav', required=True)
    ap.add_argument('--vad-json', required=True, help='VAD 段 json（parakeet_full.py 产出）')
    ap.add_argument('--slices-json', required=True)
    ap.add_argument('--sliced-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--maxs', type=float, default=28.0)
    args = ap.parse_args()

    so = ort.SessionOptions()
    so.log_severity_level = 3
    t00 = time.time()
    model = onnx_asr.load_model(
        MODEL_NAME, MODEL_DIR, quantization='int8',
        providers=[('DmlExecutionProvider', {'device_id': 0})], sess_options=so,
    ).with_timestamps()
    print('模型加载 %.1fs' % (time.time() - t00), flush=True)

    x = read_wav16k(args.wav)
    total = len(x) / SR

    segs = json.load(open(args.vad_json, encoding='utf-8'))['segments']
    blocks = build_blocks(segs, args.maxs, total)
    print('VAD 段 %d -> 合并为 %d 块 (<=%.0fs)' % (len(segs), len(blocks), args.maxs), flush=True)

    all_words = []
    for i, (a, b) in enumerate(blocks):
        # 边界留 0.25s 余量，避免把块外音头切掉
        ca = max(0.0, a - 0.25)
        cb = min(total, b + 0.25)
        chunk = x[int(ca * SR):int(cb * SR)]
        tt = time.time()
        try:
            r = model.recognize(chunk, sample_rate=SR)
        except Exception as e:
            print('  块 %d 失败: %s' % (i, str(e)[:80]), flush=True)
            continue
        toks = getattr(r, 'tokens', None)
        times = getattr(r, 'timestamps', None)
        nw = 0
        if toks and times:
            for ws, we, w in merge_tokens(toks, times):
                all_words.append((ca + ws, ca + we, w))
                nw += 1
        if i % 10 == 0 or i == len(blocks) - 1:
            print('  块 %3d/%d  %7.2f-%7.2f (%4.1fs)  %3d 词  %.1fs | %s'
                  % (i, len(blocks), a, b, b - a, nw, time.time() - tt,
                     str(getattr(r, 'text', ''))[:50]), flush=True)

    all_words.sort(key=lambda t: t[0])
    # 去重：相邻且文本相同、时间差很小 => 重复
    ded = []
    for w in all_words:
        if ded and abs(w[0] - ded[-1][0]) < 0.06 and w[2].lower() == ded[-1][2].lower():
            continue
        ded.append(w)
    print('\n共 %d 词（去重前 %d）/ %.1fs' % (len(ded), len(all_words), time.time() - t00), flush=True)

    # ---- 挂到切片 ----
    SJ = json.load(open(args.slices_json, encoding='utf-8'))
    slices = sorted(SJ['slices'], key=lambda s: s['t0'])
    out_slices = []
    used = [False] * len(ded)
    for s in slices:
        a, b = s['t0'], s['t1']
        ws = []
        for k, (gs, ge, w) in enumerate(ded):
            if used[k]:
                continue
            mid = (gs + ge) / 2
            if a <= mid < b:
                ws.append([round(gs, 3), round(ge, 3), w])
                used[k] = True
        out_slices.append(dict(file=s['file'], t0=a, t1=b, words=ws,
                               text=' '.join(w for _, _, w in ws)))

    n_empty = sum(1 for s in out_slices if not s['words'])
    n_words = sum(len(s['words']) for s in out_slices)
    print('切片 %d | 有词 %d | 空 %d | 词 %d | 未归属 %d'
          % (len(out_slices), len(out_slices) - n_empty, n_empty, n_words,
             sum(1 for u in used if not u)), flush=True)

    json.dump(dict(slices=out_slices, n_words=n_words),
              open(args.out + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(args.out + '.list', 'w', encoding='utf-8') as f:
        for s in out_slices:
            if not s['words']:
                continue
            p = os.path.join(args.sliced_dir, s['file']).replace('\\', '/')
            f.write('%s|Calm|en|%s\n' % (p, s['text']))
    print('写出 %s.list / .json' % args.out, flush=True)


if __name__ == '__main__':
    main()
