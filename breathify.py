# -*- coding: utf-8 -*-
"""气声化 / 去电音后处理。

诊断依据（实测）：
  原声(wonder)      HNR = 0.493   ← 气声低语，含大量噪声成分
  GPT-SoVITS 生成   HNR = 0.580   ← 声码器输出"过于周期/规整"
  + Praat 重合成    HNR = 0.614   ← 更规整
  ⇒ 听感上的"电音/金属感" = 周期性过强。修法是**加回非周期性成分**（不是压高频）。

做法：
  在**有声帧**上，按语音包络注入高通噪声（噪声源用"谐波间残差"更自然），
  自动二分搜索注入强度，使输出 HNR 逼近目标（默认取原声的 HNR）。

两种噪声源：
  --source residual : 从参考原声提取"谐波残差"的频谱形状（推荐，最像气声）
  --source hpnoise  : 高通白噪（无需参考，通用）

用法:
  python -u breathify.py --in X.wav --out Y.wav --target-hnr 0.50
  python -u breathify.py --in X.wav --out Y.wav --target-hnr 0.50 --ref wonder.wav
"""
import argparse
import os

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt


# ---------- 基础工具 ----------
def _frame_rms(x, sr, fl=0.02, hop=0.01):
    fl_n = max(1, int(fl * sr))
    hop_n = max(1, int(hop * sr))
    n = max(1, (len(x) - fl_n) // hop_n + 1)
    idx = np.arange(fl_n)[None, :] + hop_n * np.arange(n)[:, None]
    np.clip(idx, 0, len(x) - 1, out=idx)
    return np.sqrt((x[idx] ** 2).mean(1) + 1e-20), fl_n, hop_n


def _up_to_samples(v, hop_n, total):
    y = np.repeat(v, hop_n)[:total]
    if len(y) < total:
        y = np.pad(y, (0, total - len(y)), constant_values=float(v[-1]))
    return y


def hnr(x, sr, fmin=60, fmax=400, top=20):
    """与 diag_noise.py 同一实现，保证可比。"""
    fl = int(0.040 * sr)
    hop = int(0.020 * sr)
    n = max(1, (len(x) - fl) // hop)
    best = []
    for i in range(n):
        fr = x[i * hop:i * hop + fl]
        if len(fr) < fl:
            break
        e = np.sqrt((fr ** 2).mean())
        if e < 1e-4:
            continue
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, 'full')[len(fr) - 1:]
        ac = ac / (ac[0] + 1e-12)
        lo, hi = int(sr / fmax), int(sr / fmin)
        if hi >= len(ac) or hi <= lo:
            continue
        best.append((e, ac[lo:hi].max()))
    if not best:
        return 0.0
    best.sort(reverse=True)
    return float(np.mean([p for _, p in best[:top]]))


def _highpass(x, sr, hz):
    nyq = sr / 2.0
    w = min(0.95, hz / nyq)
    if w <= 0:
        return x
    sos = butter(2, w, btype='high', output='sos')
    return sosfilt(sos, x)


# ---------- 噪声源 ----------
def make_noise(x, sr, ref=None, hp_hz=1500, seed=42):
    """生成与语音等长的噪声源（高通白噪 / 参考残差形状）。"""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(len(x))
    if ref is not None:
        # 参考的"谐波残差"频谱形状：参考谱 / 参考谱的谐波平滑包络
        try:
            r, srr = sf.read(ref)
            if r.ndim > 1:
                r = r.mean(1)
            if srr != sr:
                import librosa
                r = librosa.resample(r.astype(np.float32), orig_sr=srr, target_sr=sr)
            L = min(len(r), len(x))
            S = np.abs(np.fft.rfft(r[:L] * np.hanning(L), n=2 * L))
            f = np.fft.rfftfreq(2 * L, 1.0 / sr)
            # 谐波平滑：用滑动最大近似包络
            k = max(3, int(0.10 * len(S)))
            env = np.convolve(S, np.ones(k) / k, mode='same')
            shape = S / (env + 1e-12)              # 谐波间凹陷 → 残差形状
            shape = np.clip(shape, 0, None)
            N = np.abs(np.fft.rfft(n, n=2 * len(n)))
            N = N * shape[:len(N)]
            n = np.fft.irfft(N)[:len(x)]
        except Exception as e:
            print('  [warn] 参考残差失败(%s)，退回高通白噪' % e)
            n = _highpass(n, sr, hp_hz)
    else:
        n = _highpass(n, sr, hp_hz)
    return n


def breathify(x, sr, target_hnr, noise, amount=None, iters=8, hi_gain=None):
    """按语音包络注入噪声，自动搜索强度使 HNR 逼近 target。"""
    env, hop_n, fl_n = _frame_rms(x, sr)
    env_s = _up_to_samples(env, hop_n, len(x))
    env_s = env_s / (env_s.mean() + 1e-12)
    rms_x = np.sqrt((x ** 2).mean() + 1e-20)

    def mix(a):
        return x + noise * env_s * rms_x * a

    if amount is not None:
        return mix(amount), float(amount)

    # 二分搜索
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        h = hnr(mix(mid), sr)
        if h > target_hnr:
            lo = mid
        else:
            hi = mid
    a = 0.5 * (lo + hi)
    return mix(a), float(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--out', dest='outp', required=True)
    ap.add_argument('--ref', default=None, help='参考原声（提取气声频谱形状）')
    ap.add_argument('--target-hnr', type=float, default=0.50)
    ap.add_argument('--amount', type=float, default=None, help='固定强度（跳过自动搜索）')
    ap.add_argument('--hp', type=float, default=1500.0, help='高通截止(无 ref 时)')
    a = ap.parse_args()

    x, sr = sf.read(a.inp)
    if x.ndim > 1:
        x = x.mean(1)
    x = np.asarray(x, dtype=np.float64)

    h0 = hnr(x, sr)
    noise = make_noise(x, sr, ref=a.ref, hp_hz=a.hp)
    y, amt = breathify(x, sr, a.target_hnr, noise, amount=a.amount)
    h1 = hnr(y, sr)
    sf.write(a.outp, y, sr)
    print('[ok] HNR %.3f -> %.3f (target %.3f)  注入强度 %.4f  -> %s'
          % (h0, h1, a.target_hnr, amt, os.path.basename(a.outp)), flush=True)


if __name__ == '__main__':
    main()
