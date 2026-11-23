# -*- coding: utf-8 -*-
"""指标审计：不变性（invariance）+ 敏感度（sensitivity）。

背景（2026-10-29 两次翻车）：
  旧 energy_span 用「21 段按样本等分 + 丢低于 p90−35 的段」，
  同一个 take 只慢 12%，span 从 26.6 掉到 13.3 —— 量的是「静音落在哪一段」。
  这类错误的共同特征：**没做过不变性测试就定阈值**。

本脚本对每个候选指标做两组实验：

  无关变换（指标应当几乎不动）：
    A 时间伸缩 0.887（rubberband，音高不变）
    B 整体增益 −6dB
    C 加 −56dBFS 底噪
    D 首尾各补 0.5s 静音
    H 空重合成（pyworld 编解码，不改任何参数）← 必须有，否则会把重合成伪影算成劣化响应

  已知劣化（指标应当显著响应）：
    E 轮廓压平（半音轮廓向中位收缩到 0.30 倍）
    F 轮廓乱序（按 0.30s 块打乱顺序，保留幅度分布、破坏走向）
    G 局部跳变（两处 ±8 半音台阶）

判据：SNR = median|Δ_劣化| / median|Δ_无关|，> 2 才算可判，> 3 才算好用。
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, r'G:/_setup')

FP = 5.0          # pyworld frame period (ms)
FFMPEG = r'E:/tool/oopz/ffmpeg.exe'


# ---------------------------------------------------------------- 基础工具
def read(p):
    x, sr = sf.read(p, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    return np.ascontiguousarray(x, dtype=np.float32), sr


def write(p, x, sr):
    sf.write(p, x, sr, subtype='PCM_16')


def world_decomp(x, sr, floor=60.0, ceil=400.0):
    import pyworld as pw
    f0, t = pw.harvest(x.astype(np.float64), sr, f0_floor=floor, f0_ceil=ceil,
                       frame_period=FP)
    f0 = pw.stonemask(x.astype(np.float64), f0, t, sr)
    sp = pw.cheaptrick(x.astype(np.float64), f0, t, sr)
    ap = pw.d4c(x.astype(np.float64), f0, t, sr)
    return f0, sp, ap, t


def world_synth(f0, sp, ap, sr):
    import pyworld as pw
    y = pw.synthesize(f0, sp, ap, sr, frame_period=FP)
    return np.ascontiguousarray(y.astype(np.float32))


# ---------------------------------------------------------------- 无关变换
def tf_time(x, sr, tmpdir, tempo=0.887):
    i = os.path.join(tmpdir, 'i.wav')
    o = os.path.join(tmpdir, 'o.wav')
    write(i, x, sr)
    r = subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', i,
                        '-af', 'rubberband=tempo=%.4f' % tempo, o],
                       capture_output=True)
    if not os.path.exists(o) or os.path.getsize(o) < 1000:
        return None
    y, _ = read(o)
    return y


def tf_gain(x, sr, db=-6.0):
    return (x.astype(np.float64) * (10 ** (db / 20.0))).astype(np.float32)


def tf_noise(x, sr, target=-56.0):
    db, _ = _frame_db(x, sr)
    q10 = float(np.percentile(db, 10))
    cur = -120.0 if q10 < -90 else q10
    if cur >= target - 1.0:
        return x
    p_add = max(10 ** (target / 10.0) - 10 ** (cur / 10.0), 0.0)
    rng = np.random.default_rng(7)
    nz = rng.standard_normal(len(x)).astype(np.float32)
    nz *= np.sqrt(p_add) / max(np.sqrt((nz.astype(np.float64) ** 2).mean()), 1e-12)
    return (x + nz).astype(np.float32)


def tf_pad(x, sr, sec=0.5):
    n = int(sec * sr)
    return np.concatenate([np.zeros(n, np.float32), x, np.zeros(n, np.float32)])


def tf_world_roundtrip(x, sr, cache):
    if 'w' in cache:
        return cache['w']
    f0, sp, ap, t = world_decomp(x, sr)
    y = world_synth(f0, sp, ap, sr)
    cache['w'] = y
    return y


# ---------------------------------------------------------------- 已知劣化
def dg_flatten(x, sr, cache, k=0.30):
    """把半音轮廓向句内中位收缩到 k 倍 —— 幅度变小，走向保留。"""
    f0, sp, ap, t = _decomp(x, sr, cache)
    v = f0 > 0
    if v.sum() < 20:
        return None
    med = np.median(f0[v])
    f0n = f0.copy()
    f0n[v] = med * (f0[v] / med) ** k
    return world_synth(f0n, sp, ap, sr)


def dg_shuffle(x, sr, cache, block=0.30):
    """按 0.30s 块打乱半音轮廓顺序 —— 幅度分布不变，走向被破坏。"""
    f0, sp, ap, t = _decomp(x, sr, cache)
    v = f0 > 0
    if v.sum() < 20:
        return None
    idx = np.where(v)[0]
    nb = max(2, int(block * 1000.0 / FP))
    chunks = [idx[i:i + nb] for i in range(0, len(idx), nb)]
    rng = np.random.default_rng(11)
    order = rng.permutation(len(chunks))
    f0n = f0.copy()
    vals = np.concatenate([f0[c] for c in chunks])
    pos = np.concatenate([chunks[i] for i in order])
    # 块长度不一，按顺序铺回（用拼接后长度对齐）
    pos = pos[:len(vals)]
    f0n[pos] = vals[:len(pos)]
    return world_synth(f0n, sp, ap, sr)


def dg_jump(x, sr, cache, semi=8.0):
    """两处 ±8 半音台阶 —— 局部大幅跳变，其余不动。"""
    f0, sp, ap, t = _decomp(x, sr, cache)
    v = np.where(f0 > 0)[0]
    if len(v) < 40:
        return None
    f0n = f0.copy()
    for frac, sgn in ((0.33, +1), (0.66, -1)):
        c = v[int(len(v) * frac)]
        f0n[c:c + 8] *= 2 ** (sgn * semi / 12.0)
    return world_synth(f0n, sp, ap, sr)


def _decomp(x, sr, cache):
    if 'd' not in cache:
        cache['d'] = world_decomp(x, sr)
    return cache['d']


# ---------------------------------------------------------------- 指标
def _frame_db(x, sr, fl=0.02, hop=0.01):
    n = max(1, int(fl * sr))
    h = max(1, int(hop * sr))
    k = max(1, (len(x) - n) // h + 1)
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    fr = x[idx].astype(np.float64)
    rms = np.sqrt((fr ** 2).mean(1) + 1e-20)
    return 20 * np.log10(rms + 1e-12), h


def _pitch(x, sr, floor=60, ceil=250, vt=0.20):
    import parselmouth
    snd = parselmouth.Sound(x, sampling_frequency=sr)
    p = snd.to_pitch_ac(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceil,
                        voicing_threshold=vt, silence_threshold=0.03)
    f = np.asarray(p.selected_array['frequency'], dtype=float)
    t = np.asarray(p.xs(), dtype=float)
    return f, t


def m_energy_span(x, sr):
    """语音帧口径：剔静音帧后等分 21 段取 p90 极差。"""
    db, _ = _frame_db(x, sr)
    if len(db) < 21 * 2:
        return None
    ref = np.percentile(db, 90)
    v = db[db > ref - 25.0]
    if len(v) < 21 * 2:
        return None
    k = len(v) // 21
    prof = [float(np.percentile(v[i * k:(i + 1) * k], 90)) for i in range(21)]
    return max(prof) - min(prof)


def _slopes(x, sr, win=0.25, hop=0.06):
    f, t = _pitch(x, sr)
    v = f > 0
    if v.sum() < 25:
        return None, None, None
    med = np.median(f[v])
    st = 12 * np.log2(np.maximum(f, 1e-6) / med)
    nw, nh = int(win / 0.01), max(1, int(hop / 0.01))
    sl = []
    for a in range(0, len(st) - nw + 1, nh):
        vv = v[a:a + nw]
        if vv.sum() < nw * 0.7:
            continue
        tt = t[a:a + nw][vv]
        if tt[-1] - tt[0] < win * 0.7:
            continue
        sl.append(np.polyfit(tt - tt[0], st[a:a + nw][vv], 1)[0])
    if len(sl) < 6:
        return None, None, st[v]
    s = np.array(sl)
    k = max(2, len(s) // 4)
    return float(np.mean(s[:k])), float(np.mean(s[-k:])), st[v]


def m_span_st(x, sr):
    _, _, stv = _slopes(x, sr)
    if stv is None:
        return None
    return float(np.percentile(stv, 95) - np.percentile(stv, 5))


def m_head(x, sr):
    h, _, _ = _slopes(x, sr)
    return h


def m_tail(x, sr):
    _, t, _ = _slopes(x, sr)
    return t


def m_rev(x, sr):
    """F0 方向反转率（次/秒），5 点中值平滑后数符号变化。"""
    f, t = _pitch(x, sr)
    v = f > 0
    idx = np.where(v)[0]
    if len(idx) < 40:
        return None
    ys = f[idx]
    sm = np.convolve(ys, np.ones(5) / 5, mode='valid')
    d = np.diff(sm)
    sgn = np.sign(d)
    sgn = sgn[sgn != 0]
    if len(sgn) < 3:
        return None
    rev = int((np.diff(sgn) != 0).sum())
    dur = t[idx[-1]] - t[idx[0]]
    return rev / max(dur, 0.1)


def m_decl(x, sr):
    """全句 F0 线性下降斜率（半音/秒），declination。"""
    f, t = _pitch(x, sr)
    v = f > 0
    if v.sum() < 30:
        return None
    med = np.median(f[v])
    st = 12 * np.log2(np.maximum(f[v], 1e-6) / med)
    tt = t[v]
    if tt[-1] - tt[0] < 0.5:
        return None
    return float(np.polyfit(tt - tt[0], st, 1)[0])


METRICS = [
    ('energy_span', m_energy_span),
    ('span_st', m_span_st),
    ('rev_rate', m_rev),
    ('head_slope', m_head),
    ('tail_slope', m_tail),
    ('decl_slope', m_decl),
]

IRR = ['time0.887', 'gain-6dB', 'noise-56', 'pad0.5s', 'world_rt']
DEG = ['flat0.3', 'shuffle0.3', 'jump8st']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=r'G:/_setup/_mt_raw_s42')
    ap.add_argument('--limit', type=int, default=40)
    ap.add_argument('--out', default=r'G:/_setup/_metric_audit.json')
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, '*.wav')))[:a.limit]
    print('样本 %d 条 ← %s' % (len(files), a.dir), flush=True)

    # 只保留 dur 2.5~9s 的（span 可测、重合成代价可控）
    keep = []
    for f in files:
        x, sr = read(f)
        d = len(x) / sr
        if 2.5 <= d <= 9.0:
            keep.append((f, x, sr))
    print('时长合格 %d 条' % len(keep), flush=True)

    rows = []
    tmpdir = tempfile.mkdtemp()
    for n, (f, x, sr) in enumerate(keep, 1):
        cache = {}
        base = {}
        for name, fn in METRICS:
            try:
                base[name] = fn(x, sr)
            except Exception:
                base[name] = None

        variants = {}
        variants['time0.887'] = tf_time(x, sr, tmpdir)
        variants['gain-6dB'] = tf_gain(x, sr)
        variants['noise-56'] = tf_noise(x, sr)
        variants['pad0.5s'] = tf_pad(x, sr)
        variants['world_rt'] = tf_world_roundtrip(x, sr, cache)
        variants['flat0.3'] = dg_flatten(x, sr, cache)
        variants['shuffle0.3'] = dg_shuffle(x, sr, cache)
        variants['jump8st'] = dg_jump(x, sr, cache)

        rec = dict(key=os.path.basename(f)[:-4], dur=round(len(x) / sr, 2), base=base)
        for vn, y in variants.items():
            if y is None:
                rec[vn] = None
                continue
            vals = {}
            for name, fn in METRICS:
                try:
                    vals[name] = fn(y, sr)
                except Exception:
                    vals[name] = None
            rec[vn] = vals
        rows.append(rec)
        print('[%02d/%02d] %-10s %.2fs' % (n, len(keep), rec['key'], rec['dur']),
              flush=True)

    # ---- 汇总
    print('\n' + '=' * 84, flush=True)
    hdr = '%-13s %8s' % ('metric', 'base p50')
    for vn in IRR + DEG:
        hdr += ' %10s' % vn[:10]
    hdr += ' %8s %8s' % ('SNR_irr', 'SNR_deg')
    print(hdr, flush=True)
    print('-' * 84, flush=True)

    summary = {}
    for name, _ in METRICS:
        b = [r['base'][name] for r in rows if r['base'].get(name) is not None]
        if len(b) < 4:
            print('%-13s 样本不足 n=%d' % (name, len(b)), flush=True)
            continue
        d_irr, d_deg = [], []
        line = '%-13s %8.2f' % (name, float(np.median(b)))
        for vn in IRR + DEG:
            deltas = []
            for r in rows:
                if not r.get(vn) or r['base'].get(name) is None:
                    continue
                v = r[vn].get(name)
                if v is None:
                    continue
                deltas.append(abs(v - r['base'][name]))
            m = float(np.median(deltas)) if deltas else float('nan')
            line += ' %10.2f' % m
            (d_irr if vn in IRR else d_deg).append(m)
        si = float(np.median(d_irr)) if d_irr else float('nan')
        sd = float(np.median(d_deg)) if d_deg else float('nan')
        snr = sd / si if si and si > 1e-9 else float('inf')
        line += ' %8.2f %8.2f' % (si, sd)
        print(line, flush=True)
        summary[name] = dict(base_p50=float(np.median(b)), n=len(b),
                             delta_irr={k: v for k, v in zip(IRR, d_irr)},
                             delta_deg={k: v for k, v in zip(DEG, d_deg)},
                             snr_irr=si, snr_deg=snr)

    print('\nSNR_irr = 无关变换的 |Δ| 中位（越小越好）')
    print('SNR_deg = 劣化的 |Δ| 中位 ÷ 无关变换的 |Δ| 中位（>2 可判，>3 好用）')
    print('\n各指标最怕哪种无关变换：')
    for name, s in summary.items():
        worst = max(s['delta_irr'], key=s['delta_irr'].get)
        print('  %-13s %-11s Δ%.2f' % (name, worst, s['delta_irr'][worst]))

    json.dump(dict(rows=rows, summary=summary), open(a.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n落盘 %s' % a.out)


if __name__ == '__main__':
    main()
