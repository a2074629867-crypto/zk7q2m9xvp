"""判断音高变化是"整体平移"还是"换了一种演法"。

方法：把 F0 轮廓重采样到 100 点归一化时间轴，各自减去自身中位数（去掉电平差），
再算两两相关。相关高 = 轮廓形状不变、只是整体抬高/压低 → 真·变调。
相关低 = 换了一次表演，音高中位数变了但没有系统性变调。
"""
import glob
import os
import sys
import wave

import numpy as np
import parselmouth

D = sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/_pitch_test"
GRID = 100


def rd(p):
    w = wave.open(p)
    sr = w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    if w.getnchannels() > 1:
        a = a.reshape(-1, w.getnchannels()).mean(axis=1)
    w.close()
    return a, sr


def contour(a, sr):
    p = parselmouth.Sound(a, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=40.0, pitch_ceiling=400.0)
    v = p.selected_array["frequency"].astype(float)
    v[v <= 0] = np.nan
    # 用有效段归一化时间轴
    idx = np.where(~np.isnan(v))[0]
    if len(idx) < 20:
        return None
    v = v[idx[0]:idx[-1] + 1]
    st = 12 * np.log2(v / 100.0)
    # 线性插值到固定网格
    x = np.linspace(0, 1, len(st))
    xi = np.linspace(0, 1, GRID)
    out = np.interp(xi, x[np.isfinite(st)], st[np.isfinite(st)])
    return out


def main():
    files = sorted(glob.glob(os.path.join(D, "*.wav")))
    data = {}
    for f in files:
        a, sr = rd(f)
        c = contour(a, sr)
        if c is not None:
            data[os.path.basename(f)[:-4]] = c
    if not data:
        print("no data")
        return
    keys = sorted(data)
    print("轮廓相关（去中位数后，越高越说明只是整体平移）")
    hdr = "%-14s" % ""
    print(hdr + "".join("%-8s" % k[-7:] for k in keys))
    for k1 in keys:
        row = "%-14s" % k1
        for k2 in keys:
            c1 = data[k1] - np.median(data[k1])
            c2 = data[k2] - np.median(data[k2])
            r = np.corrcoef(c1, c2)[0, 1]
            row += "%-8.2f" % r
        print(row)


if __name__ == "__main__":
    main()
