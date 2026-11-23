# -*- coding: utf-8 -*-
"""把单次生成的整句按句间静音切开，逐段对齐电平，再按需要加长停顿后拼回。

不重新合成 ⇒ 保留模型一次生成的连贯语调曲线（拆句重生成会让每句各演各的）。
"""
import numpy as np

import ch123_level as L


def rms_voiced_db(a, sr):
    db, _ = L._env_db(a, sr)
    loud = np.percentile(db, 90)
    v = db[db > loud - 32.0]
    if len(v) == 0:
        v = db
    return float(np.mean(v))


def split_at_silence(a, sr, min_gap=0.25, thresh=-42.0):
    """按静音切成语音段，返回 [(start,end)] 秒。"""
    nf = int(0.01 * sr)
    k = len(a) // nf
    e = np.array([np.sqrt(np.mean(a[i * nf:(i + 1) * nf] ** 2) + 1e-12) for i in range(k)])
    db = 20 * np.log10(e + 1e-9)
    on = db > thresh
    segs, st = [], None
    for i, x in enumerate(on):
        if x and st is None:
            st = i
        if not x and st is not None:
            segs.append([st * 0.01, i * 0.01])
            st = None
    if st is not None:
        segs.append([st * 0.01, k * 0.01])
    # 合并过短的静音（<0.12s 不算断句）
    merged = []
    for s0, s1 in segs:
        if merged and s0 - merged[-1][1] < 0.12:
            merged[-1][1] = s1
        else:
            merged.append([s0, s1])
    # 只保留真正够长的间隙作为切点
    out = [merged[0]]
    for s0, s1 in merged[1:]:
        if s0 - out[-1][1] >= min_gap:
            out.append([s0, s1])
        else:
            out[-1][1] = s1
    return out


def rebuild(a, sr, gaps=None, target_db=-24.0, max_level_db=6.0, trim_head=0.0, level_after=True):
    """a: mono float32。gaps: 每段之后要插入的静音秒数（长度 = 段数-1）。
    gaps=None 时沿用原生成里各段之间的静音长度（只做电平对齐）。"""
    segs = split_at_silence(a, sr)
    if gaps is None:
        gaps = [max(0.0, segs[i + 1][0] - segs[i][1]) for i in range(len(segs) - 1)]
    pieces = []
    info = []
    for i, (s0, s1) in enumerate(segs):
        seg = a[int(s0 * sr):int(s1 * sr)].copy()
        cur = rms_voiced_db(seg, sr)
        g = 10 ** ((target_db - cur) / 20.0)
        g = float(np.clip(g, 10 ** (-max_level_db / 20), 10 ** (max_level_db / 20)))
        seg = seg * g
        info.append((s0, s1, cur, 20 * np.log10(g)))
        pieces.append(seg)
        if i < len(segs) - 1:
            pieces.append(np.zeros(int(gaps[min(i, len(gaps) - 1)] * sr), dtype=np.float32))
    y = np.concatenate(pieces)
    if trim_head > 0:
        y = np.concatenate([np.zeros(int(trim_head * sr), dtype=np.float32), y])
    y = np.concatenate([y, np.zeros(int(0.16 * sr), dtype=np.float32)])
    if level_after:
        y = L.level(y, sr, max_db=4.0, target_rms_db=target_db)
    pk = float(np.max(np.abs(y)))
    if pk > 0.95:
        y *= 0.95 / pk
    return y.astype(np.float32), info
