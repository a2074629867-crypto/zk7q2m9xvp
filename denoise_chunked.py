# -*- coding: utf-8 -*-
"""denoise_chunked.py —— DeepFilterNet3 分块降噪（低内存）

要点：
  · 模型只加载一次，逐块处理（默认 240s/块），峰值内存 < 1GB
  · 块间 1.0s 线性交叉淡化，避免边界不连续
  · 采样率往返：源 32k -> DF 48k 处理 -> 回 32k（与官方 CLI 行为一致）
  · 时间轴严格不变（不裁剪、不补零），因此切片帧号与已有标注全部复用
"""
import os
import sys
import time
import argparse

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly
from df.enhance import init_df, enhance

SRC = 'G:/GPT-SoVITS/_dataset/wonder_train.wav'
OUTDIR = 'G:/_setup/_denoise_full'
MODEL = 'G:/asr_models/df3/DeepFilterNet3'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=SRC)
    ap.add_argument('--out', default=OUTDIR + '/wonder_train_df3.wav')
    ap.add_argument('--model', default=MODEL)
    ap.add_argument('--chunk', type=float, default=240.0, help='每块秒数')
    ap.add_argument('--overlap', type=float, default=1.0, help='交叉淡化秒数')
    ap.add_argument('--atten-lim-db', type=float, default=None)
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    t0 = time.time()
    model, state, device = init_df(model_base_dir=a.model, log_file=None)
    try:
        DSR = state.sr()
    except Exception:
        DSR = 48000
    print('[init] %.1fs  DF_sr=%d  device=%s' % (time.time() - t0, DSR, device), flush=True)

    info = sf.info(a.src)
    SR, N = info.samplerate, info.frames
    print('[src ] %s  %d Hz  %d frames  %.1fs' % (os.path.basename(a.src), SR, N, N / SR), flush=True)

    chunk_n = int(a.chunk * SR)
    ov_n = int(a.overlap * SR)
    step = chunk_n - ov_n

    def enhance_block(x):
        x48 = resample_poly(x, DSR, SR)
        t = torch.from_numpy(np.ascontiguousarray(x48, dtype=np.float32)).unsqueeze(0)  # [1, T]
        with torch.no_grad():
            y = enhance(model, state, t, atten_lim_db=a.atten_lim_db)
        y = y.detach().cpu().numpy().astype(np.float64).reshape(-1)
        return resample_poly(y, SR, DSR)

    with sf.SoundFile(a.src) as fin, \
         sf.SoundFile(a.out, 'w', samplerate=SR, channels=1, subtype='PCM_16') as fout:
        pos = 0
        tail = None          # 上一块末尾 ov 段（已增强，待与下一块交叉）
        k = 0
        while pos < N:
            end = min(pos + chunk_n, N)
            fin.seek(pos)
            x = fin.read(end - pos, dtype='float64', always_2d=True).mean(1)
            y = enhance_block(x)

            if tail is not None and len(tail) > 0 and len(y) > 0:
                m = min(len(tail), ov_n, len(y))
                if m > 0:
                    w = np.linspace(0.0, 1.0, m)
                    y[:m] = tail[-m:] * (1.0 - w) + y[:m] * w

            if end < N and len(y) > ov_n:
                fout.write(y[:-ov_n].astype(np.float32))
                tail = y[-ov_n:].copy()
            else:
                fout.write(y.astype(np.float32))
                tail = None

            pos += step
            k += 1
            print('  blk %2d  %6.1f/%6.1fs  %5.1f%%  elapsed %.0fs'
                  % (k, min(pos, N) / SR, N / SR, 100.0 * min(pos, N) / N, time.time() - t0), flush=True)

    oi = sf.info(a.out)
    print('[done] %.1fs -> %s' % (time.time() - t0, a.out), flush=True)
    print('  out: %d Hz  %d frames  %.2fs  (src %.2fs)' % (oi.samplerate, oi.frames, oi.duration, N / SR), flush=True)


if __name__ == '__main__':
    main()
