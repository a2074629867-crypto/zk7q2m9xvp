# -*- coding: utf-8 -*-
"""S1 分角色双向参考带：真人原声 → _rhythm_bands.json

为什么必须分角色、且必须先切句：
  旁白（马修）与对白（夏尔）的能量 span 不在一个尺度上；而 castle_fr_ref 的
  真人素材每条约 10s、含多句，直接测会把「句间」起伏算进「句内」，与我们对白
  （每条 2.7s 单句）不可比。所以先按静音切句，再逐句测。

指标（每条一句）：
  energy_span  21 点能量轮廓 p90 极差（dB）—— 双向主判据
  span_st      F0 p5–p95（半音，相对句内浊音中位）
  head_slope   前 1/4 窗斜率均值（st/s）
  tail_slope   后 1/4 窗斜率均值（st/s）
  rev_rate     F0 方向反转次数 / 秒
  oct_err      帧间跳变落在 10.5–13.5st 的次数（八度跟踪伪影）
  cut_drop     结尾 5ms 相对前 20ms 的跌落（dB）

用法：
  python mt_rhythm_bands.py                 # 建三条带
  python mt_rhythm_bands.py --show          # 只打印不落盘
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from narr_check import cut_units, frame_db, NPT

OUT_DEFAULT = r'G:/_setup/_rhythm_bands.json'

# 角色 → F0 提取参数（已踩过的坑：旁白 ceil=500 会把清音抓成 490Hz）
F0P = {
    'narr':    dict(floor=60.0, ceil=250.0, vt=0.20),
    'charles': dict(floor=70.0, ceil=500.0, vt=0.25),
    'hooper':  dict(floor=70.0, ceil=500.0, vt=0.25),
}

WIN, HOP = 0.25, 0.06
# ★ 底噪归一（2026-10-29 实测）：我们生成的音频是数字零底噪，真人是 −56dB。
#   同一批 120 条旁白：不补 span p50 37.9 / 补到 −58 → 36.1 / 补到 −50 → 30.6。
#   ⇒ 不补会把「低底噪」误判成「起伏过大」；补太狠（−50）又会把真实起伏压掉 7dB。
#   ★ 目标值取「真人带的实测底噪中位」而不是 −58：真人 80 条 p50 = −56.5，
#     我们 raw −58.9 / ch123_final_llm −59.3。真人不能去噪，所以只能把我们的抬到它那档。
FLOOR_TARGET = -56.0
VOICED_REL = -25.0   # 语音帧判定：高于 p90 这么多 dB（静音帧一律不参与 span）
OCT_LO, OCT_HI = 10.5, 13.5
PCTS = [5, 10, 25, 50, 75, 90, 95]

# ★ 单元口径必须与「被闸门的音频」一致，否则 span 不可比：
#   旁白我们按文本块生成（p50 5.3s、1~3 句），真人 ref_human 本身就是 4~7s 整段
#   ⇒ 旁白带 **不切句**（切了会把 37 打到 22，纯口径问题）。
#   对白我们一句一条（p50 2.7s），而 castle_fr_ref 每条 10s 含多句
#   ⇒ 对白带 **必须切句**（不切是拿 10s 的起伏比 2.7s 的起伏）。
SOURCES = {
    'narr':    dict(patterns=[r'E:/ttsds/data/ref_human/*.wav'], split=False),
    'charles': dict(patterns=[r'G:/_setup/castle_fr_ref/*charles*.wav'], split=True,
                    exclude='_tight'),
    'hooper':  dict(patterns=[r'G:/_setup/castle_fr_ref/*hooper*.wav'], split=True,
                    exclude='_tight'),
}
CROSS = {
    'narr_sliced': dict(patterns=[r'G:/GPT-SoVITS/_dataset/sliced/*.wav'], split=False),
}


def f0_metrics(y, sr, role):
    import parselmouth
    p = F0P[role]
    snd = parselmouth.Sound(np.ascontiguousarray(y), sampling_frequency=sr)
    pt = snd.to_pitch_ac(time_step=0.01, pitch_floor=p['floor'],
                         pitch_ceiling=p['ceil'], voicing_threshold=p['vt'],
                         silence_threshold=0.03)
    f0 = np.asarray(pt.selected_array['frequency'], dtype=float)
    t = np.asarray(pt.xs(), dtype=float)
    v = f0 > 0
    if v.sum() < 25:
        return None
    med = float(np.median(f0[v]))
    st = 12 * np.log2(np.maximum(f0, 1e-6) / med)

    # 八度跟踪伪影
    octs = 0
    for i in range(1, len(f0)):
        if v[i] and v[i - 1] and abs(t[i] - t[i - 1]) < 0.03:
            d = abs(st[i] - st[i - 1])
            if OCT_LO <= d <= OCT_HI:
                octs += 1

    # 窗斜率
    nw, nh = int(WIN / 0.01), max(1, int(HOP / 0.01))
    sl = []
    for a in range(0, len(st) - nw + 1, nh):
        vv = v[a:a + nw]
        if vv.sum() < nw * 0.7:
            continue
        tt = t[a:a + nw][vv]
        yy = st[a:a + nw][vv]
        if tt[-1] - tt[0] < WIN * 0.7:
            continue
        sl.append(float(np.polyfit(tt - tt[0], yy, 1)[0]))

    # 方向反转率（5 点平滑后符号变化）
    idx = np.where(v)[0]
    ys = st[idx]
    sm = np.convolve(ys, np.ones(5) / 5, mode='valid') if len(ys) >= 5 else ys
    dd = np.diff(sm)
    sgn = np.sign(dd)
    sgn = sgn[sgn != 0]
    rev = int((np.diff(sgn) != 0).sum()) if len(sgn) > 2 else 0
    dur_v = max(t[idx[-1]] - t[idx[0]], 0.1)

    out = dict(
        f0_med=round(med, 1),
        span_st=round(float(np.percentile(st[v], 95) - np.percentile(st[v], 5)), 2),
        oct_err=octs,
        rev_rate=round(rev / dur_v, 2),
        n_win=len(sl),
        head_slope=None, tail_slope=None, mid_slope=None,
    )
    if len(sl) >= 6:
        s = np.array(sl)
        k = max(2, len(s) // 4)
        out['head_slope'] = round(float(np.mean(s[:k])), 2)
        out['tail_slope'] = round(float(np.mean(s[-k:])), 2)
        out['mid_slope'] = round(float(np.mean(s[k:-k])), 2) if len(s) > 2 * k else None
    return out


def floor_norm(x, sr, target=FLOOR_TARGET):
    """把低于 target 的底噪补到 target，使 energy_span 跨源可比。返回 (y, 原底噪)。"""
    db, _ = frame_db(x, sr)
    # ★ 底噪估计必须用「含零帧」的全量分位，不能先剔掉 <-90 的帧：
    #   实测 L068 的 ch123 版本 15.5% 帧是数字零，剔掉后 p5 变成 −42.1（那是语音），
    #   于是「不需要补噪」，而下游 final_llm 补到 −58.9 —— 两个阶段不在同一底噪上，
    #   span 直接差 7.4dB（23.2 vs 15.8），看起来像「处理把起伏吃了」，其实是量错了。
    q10 = float(np.percentile(db, 10))
    cur = -120.0 if q10 < -90 else q10
    if cur >= target - 1.0:
        return x, cur
    p_add = max(10 ** (target / 10.0) - 10 ** (cur / 10.0), 0.0)
    rms = np.sqrt(p_add)
    rng = np.random.default_rng(12345)
    nz = rng.standard_normal(len(x)).astype(np.float32)
    nz *= rms / max(np.sqrt((nz.astype(np.float64) ** 2).mean()), 1e-12)
    return (x.astype(np.float32) + nz), cur


def cut_drop_db(y, sr):
    """结尾 5ms 相对前 20ms 的跌落（dB）。硬切会掉 50dB 以上。"""
    n5 = max(1, int(0.005 * sr))
    n20 = max(1, int(0.020 * sr))
    if len(y) < n5 + n20:
        return None
    tail = float(np.sqrt((y[-n5:].astype(np.float64) ** 2).mean()) + 1e-12)
    prev = float(np.sqrt((y[-(n5 + n20):-n5].astype(np.float64) ** 2).mean()) + 1e-12)
    return round(20 * np.log10(prev / tail), 1)


def voiced_mask(y, sr, role):
    """浊音帧 mask（0.01s 步），用于 span 选帧。"""
    import parselmouth
    p = F0P[role]
    snd = parselmouth.Sound(np.ascontiguousarray(y), sampling_frequency=sr)
    pt = snd.to_pitch_ac(time_step=0.01, pitch_floor=p['floor'],
                         pitch_ceiling=p['ceil'], voicing_threshold=p['vt'],
                         silence_threshold=0.03)
    return np.asarray(pt.selected_array['frequency'], dtype=float) > 0


def span_only(y, sr, role="narr", span_voiced=False, normalize=True):
    """energy_span 的**唯一实现**（2026-11-11 抽出来，防止量尺与带不同源）。

    判据层（`narr_check.py`）与带构建层（`measure()`）必须调用同一个函数，
    否则带和判定会用两把尺子 —— 本项目已经因此出现三套数（13.1 / 16.5 / 38.9）。
    """
    if normalize:
        y, _ = floor_norm(y, sr)
    db, _ = frame_db(y, sr)
    span = None
    # ★ 只在「语音帧」上算 span（2026-10-29 修正）
    #   旧写法把 21 段按样本等分、再丢掉低于 ref−35 的段。问题是：静音落在哪一段边界上
    #   会直接改变 min，实测同一个 take 只是慢了 12%，span 就从 26.6 掉到 13.3（差 13dB），
    #   而它和「起伏」毫无关系 —— 这是分段边界伪影，比要测的效应还大。
    #   改成先剔掉静音帧、再把语音帧等分 21 段：同一 take 跨阶段 12.7/15.4/15.4/15.5 稳定。
    #
    # ★★ 2026-10-31 补：`db > p90-25` 仍是**相对**阈值，整条被压平时 p90 会跟着往下掉，
    #   静音帧反被选进来，极差被静音撑大 ⇒ 方向反判（实测 5 条慢包络等响：3 降 2 升）。
    #   加浊音条件后 5 条里 4 条明确下降（中位 9.7 → 4.9 dB）。默认仍用旧口径，
    #   开关 --span-voiced 才启用；切换必须重标带，否则全部会被判 FIX_LOW。
    if len(db) >= NPT * 4:
        ref = np.percentile(db, 90)
        M = db > ref + VOICED_REL
        if span_voiced:
            try:
                vm = voiced_mask(y, sr, role)
                vm2 = vm[::2][:len(db)]          # frame_db hop=0.02 / pitch 0.01
                if len(vm2) < len(M):
                    vm2 = np.pad(vm2, (0, len(M) - len(vm2)), constant_values=True)
                M = M & vm2
            except Exception:
                pass
        v = db[M]
        # 门槛取 2 帧/段：对白真人碎片只有 1.3s（≈55 个语音帧），用 4 帧/段会把
        # Charles 整条带判成不可测（实测 21 条全 None）。
        if len(v) >= NPT * 2:
            k = len(v) // NPT
            prof = [float(np.percentile(v[i * k:(i + 1) * k], 90)) for i in range(NPT)]
            span = round(max(prof) - min(prof), 1)
    return span


def measure(y, sr, role, span_voiced=False):
    dur = len(y) / sr
    cut = cut_drop_db(y, sr)          # 硬切必须在补底噪之前测（补了就不掉了）
    y, floor0 = floor_norm(y, sr)
    span = span_only(y, sr, role, span_voiced, normalize=False)
    d = dict(dur=round(dur, 2), energy_span=span, cut_drop=cut,
             floor_db=None if floor0 is None else round(floor0, 1))
    f = f0_metrics(y, sr, role)
    if f:
        d.update(f)
    else:
        d.update(f0_med=None, span_st=None, oct_err=0, rev_rate=None,
                 n_win=0, head_slope=None, tail_slope=None, mid_slope=None)
    return d


def collect(patterns, role, split=True, min_dur=2.5, cap=None, exclude=None):
    rows = []
    files = []
    for pat in patterns:
        files.extend(sorted(glob.glob(pat)))
    if exclude:
        files = [f for f in files if exclude not in os.path.basename(f)]
    for f in files:
        try:
            x, sr = sf.read(f, dtype='float32')
        except Exception:
            continue
        if x.ndim > 1:
            x = x.mean(1)
        units = cut_units(x, sr) if split else [(0.0, len(x) / sr)]
        for a, b in units:
            y = x[int(a * sr):int(b * sr)]
            if len(y) / sr < 0.8:
                continue
            m = measure(y, sr, role)
            m['file'] = os.path.basename(f)
            m['t0'] = round(a, 2)
            rows.append(m)
    if cap and len(rows) > cap:
        rows = rows[:cap]
    return rows


def summarize(rows, key):
    v = [r[key] for r in rows if r.get(key) is not None]
    if len(v) < 5:
        return None
    a = np.array(v, dtype=float)
    return dict(n=len(a), **{'p%02d' % p: round(float(np.percentile(a, p)), 2) for p in PCTS})


def build():
    out = {'_meta': dict(
        npt=NPT, win=WIN, hop=HOP, oct_band=[OCT_LO, OCT_HI],
        f0_params=F0P, split='narr_check.cut_units (p90-30dB, min_sil 0.22, min_unit 0.60)',
        min_dur_for_span=2.5, floor_target=FLOOR_TARGET,
        note='energy_span 只在 dur>=2.5s 时作判定；span 与时长无关（r=-0.03，863 条实测）',
    )}
    for role, cfg in SOURCES.items():
        rows = collect(cfg['patterns'], role, split=cfg['split'],
                       exclude=cfg.get('exclude'))
        band = {'n': len(rows)}
        for k in ('energy_span', 'span_st', 'head_slope', 'tail_slope',
                  'mid_slope', 'rev_rate', 'oct_err', 'cut_drop', 'dur'):
            s = summarize(rows, k)
            if s:
                band[k] = s
        out[role] = band
        print('[%s] %d 句  时长 p50 %.1fs  energy_span p50 %.1f (n=%d)'
              % (role, len(rows), np.median([r['dur'] for r in rows]),
                 band.get('energy_span', {}).get('p50', float('nan')),
                 band.get('energy_span', {}).get('n', 0)), flush=True)
    for tag, cfg in CROSS.items():
        rows = collect(cfg['patterns'], 'narr', split=cfg['split'], cap=300)
        band = {'n': len(rows)}
        for k in ('energy_span', 'span_st', 'rev_rate', 'dur'):
            s = summarize(rows, k)
            if s:
                band[k] = s
        out[tag] = band
        print('[%s] %d 句  energy_span p50 %.1f（交叉校验，不作主带）'
              % (tag, len(rows), band.get('energy_span', {}).get('p50', float('nan'))),
              flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=OUT_DEFAULT)
    ap.add_argument('--show', action='store_true')
    a = ap.parse_args()
    bands = build()
    if a.show:
        print(json.dumps(bands, ensure_ascii=False, indent=1)[:4000])
        return
    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump(bands, fh, ensure_ascii=False, indent=1)
    print('\n写出 %s' % a.out)
    print('\n%-10s %5s | %-32s | %-24s' % ('带', 'n', 'energy_span p05/p25/p50/p75/p95', 'span_st p05/p50/p95'))
    for k in ('narr', 'narr_sliced', 'charles', 'hooper'):
        if k not in bands:
            continue
        e = bands[k].get('energy_span') or {}
        s = bands[k].get('span_st') or {}
        print('%-10s %5d | %6s %6s %6s %6s %6s | %6s %6s %6s'
              % (k, bands[k]['n'],
                 e.get('p05', '-'), e.get('p25', '-'), e.get('p50', '-'),
                 e.get('p75', '-'), e.get('p95', '-'),
                 s.get('p05', '-'), s.get('p50', '-'), s.get('p95', '-')))


if __name__ == '__main__':
    main()
