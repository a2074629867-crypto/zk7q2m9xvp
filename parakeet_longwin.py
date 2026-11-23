# -*- coding: utf-8 -*-
"""
Parakeet 长窗转写（无 VAD）—— 质量最高的方案。

实测：
  - 无 VAD 直接喂 14s  -> 'drifted to the soundest of sleeps'      (丢 off)
  - 无 VAD 直接喂 30s+ -> 'drifted off to the soundest of sleeps'   (全对)
  - 有 VAD 切段喂      -> 'soundest of sleep.' + 'A dream.'         (退化)
=> 窗口越长越准；VAD 切段会伤质量。

做法：120s 窗 + 10s 重叠，每窗 with_timestamps()，词时间戳加窗偏移，
      每窗只贡献 [a+ov/2, b-ov/2]（首窗 a=0、末窗 b=总长），无缝拼接。

输出 json：{slices:[{t0,t1,words:[[a,b,w],...],text}]}  与切片目录对齐
用法：
  python parakeet_longwin.py --wav <16k wav> --slices-json <json> --sliced-dir <dir> --out <前缀>
"""
import argparse
import json
import os
import re
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
        n = w.getnframes()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    assert sr == SR, 'expect 16k, got %d' % sr
    return x


def merge_tokens(tokens, times):
    """子词合并：token 以空格开头 = 新词；否则附着前词（保留标点）"""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wav', required=True, help='16k mono wav（用原始音频，不用降噪版）')
    ap.add_argument('--slices-json', required=True)
    ap.add_argument('--sliced-dir', required=True)
    ap.add_argument('--out', required=True, help='输出前缀（生成 .list / .json）')
    ap.add_argument('--win', type=float, default=120.0)
    ap.add_argument('--ov', type=float, default=10.0)
    args = ap.parse_args()

    so = ort.SessionOptions()
    so.log_severity_level = 3
    t0 = time.time()
    model = onnx_asr.load_model(
        MODEL_NAME, MODEL_DIR, quantization='int8',
        providers=[('DmlExecutionProvider', {'device_id': 0})], sess_options=so,
    ).with_timestamps()
    print('模型加载 %.1fs' % (time.time() - t0), flush=True)

    x = read_wav16k(args.wav)
    total = len(x) / SR
    print('音频 %.1fs' % total, flush=True)

    wins = []
    a = 0.0
    while a < total - 0.5:
        b = min(total, a + args.win)
        wins.append((a, b))
        if b >= total:
            break
        a = b - args.ov
    print('分 %d 窗 (%.0fs + %.0fs 重叠)' % (len(wins), args.win, args.ov), flush=True)

    all_words = []   # (t_start, t_end, word)
    for i, (a, b) in enumerate(wins):
        # 该窗只贡献 [ca, cb]
        ca = 0.0 if i == 0 else a + args.ov / 2
        cb = total if i == len(wins) - 1 else b - args.ov / 2
        chunk = x[int(a * SR):int(b * SR)]
        tt = time.time()
        try:
            r = model.recognize(chunk, sample_rate=SR)
        except Exception as e:
            print('  窗 %d 失败: %s' % (i, str(e)[:80]), flush=True)
            continue
        toks = getattr(r, 'tokens', None)
        times = getattr(r, 'timestamps', None)
        nw = 0
        if toks and times:
            for ws, we, w in merge_tokens(toks, times):
                gs, ge = a + ws, a + we
                if ca <= gs < cb:
                    all_words.append((gs, ge, w))
                    nw += 1
        print('  窗 %2d/%d  %7.1f-%7.1f  贡献 %3d 词  %.1fs  | %s'
              % (i, len(wins), a, b, nw, time.time() - tt,
                 str(getattr(r, 'text', ''))[:60]), flush=True)

    all_words.sort(key=lambda t: t[0])
    print('\n共 %d 词 / %.1fs' % (len(all_words), time.time() - t0), flush=True)

    # ---- 挂到切片 ----
    SJ = json.load(open(args.slices_json, encoding='utf-8'))
    slices = sorted(SJ['slices'], key=lambda s: s['t0'])
    out_slices = []
    used = [False] * len(all_words)
    for s in slices:
        a, b = s['t0'], s['t1']
        ws = []
        for k, (gs, ge, w) in enumerate(all_words):
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
    print('切片 %d | 有词 %d | 空 %d | 词 %d'
          % (len(out_slices), len(out_slices) - n_empty, n_empty, n_words), flush=True)
    print('未归属词 %d' % sum(1 for u in used if not u), flush=True)

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
