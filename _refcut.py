# -*- coding: utf-8 -*-
"""_refcut.py —— 从《我是城堡之王》原片重切参考音候选（48kHz，静音对齐边界）。

为什么要重切，不是修旧切片
--------------------------
旧 `castle_cues/*.wav` 是 `castle_cut_cues.py` 按**字幕时间轴**硬切的：
  1. 固定 pad 0.12/0.20s，边界落在词中间（字幕时间轴与语音本来就有偏差）；
  2. 全部降采样到 **16kHz 单声道**，而源是 48kHz eac3 ⇒ 8kHz 以上全丢，
     NISQA 对这种带限是直接扣分的（参考库 MOS 中位 2.34 有这部分原因）；
  3. `multi` cue（196/403）整条切出来是两个人拼的，当参考音必然串味。

本脚本三件事
------------
  A 切：从 48kHz 整轨按**局部最低能量点**对齐边界（不靠字幕硬切），
        多说话人 cue 按字符数比例拆开，拆完再用说话人验证兜底。
  B 测：每段跑 说话人(r34 余弦) / 情绪(emotion2vec) / 自然度(NISQA) / F0 / 有声占比。
  C 判：三重验证都过的才进候选表，不自动入库（教训见 emo_cut.py 抬头）。

用法
----
  G:/Python310/python.exe _refcut.py cut     # 只切，出 _refs_new/cand/*.wav
  G:/Python310/python.exe _refcut.py meas    # 测量，出 _refs_new/meas.json
  G:/Python310/python.exe _refcut.py table   # 出候选表 _refs_new/table.md
"""
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

HERE = "G:/_setup"
SRC = os.path.join(HERE, "_castle_48k.wav")
CUES = os.path.join(HERE, "castle_srt_cues.json")
OUT = os.path.join(HERE, "_refs_new")
CAND = os.path.join(OUT, "cand")
MEAS = os.path.join(OUT, "meas.json")

MIN_DUR, MAX_DUR = 1.8, 9.0
SR = 48000


def load_audio():
    y, sr = sf.read(SRC, dtype="float32", always_2d=True)
    assert sr == SR, sr
    return y.mean(axis=1)


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def align(y, t_lo, t_hi, pick="min", win=0.03):
    """在 [t_lo, t_hi] 里找 win 秒窗口能量最低（或最高）的位置，返回其中点。"""
    a, b = int(max(0, t_lo) * SR), int(min(len(y) / SR, t_hi) * SR)
    if b - a < int(win * SR) * 2:
        return (t_lo + t_hi) / 2
    n = int(win * SR)
    seg = y[a:b]
    # 用 10ms 步长的滑动 RMS，取最低/最高
    hop = int(0.01 * SR)
    e = np.array([np.sqrt(np.mean(seg[i:i + n] ** 2)) for i in range(0, len(seg) - n, hop)])
    if not len(e):
        return (t_lo + t_hi) / 2
    idx = int(np.argmin(e) if pick == "min" else np.argmax(e))
    return a / SR + (idx * hop + n / 2) / SR


def split_parts(text):
    """按字幕里的换说话人标记 '-' 拆句。返回 [(text, 权重)]"""
    t = text.strip()
    # 字幕惯例：' -' 或 '-\"' 开头表示换人；行内 ' -' 也换人
    pieces = re.split(r"\s+-\s*|^-\s*", t)
    pieces = [p.strip().strip('"').strip() for p in pieces if p.strip()]
    if not pieces:
        return []
    ws = [max(1, len(p)) for p in pieces]
    return list(zip(pieces, ws))


def cmd_cut():
    y = load_audio()
    cues = json.load(open(CUES, encoding="utf-8"))
    os.makedirs(CAND, exist_ok=True)
    meta = []
    for c in cues:
        txt = c["text"].strip()
        if txt.startswith("("):      # 音效/拟声
            continue
        parts = split_parts(txt)
        if not parts:
            continue
        tot = sum(w for _, w in parts)
        acc = 0.0
        for k, (pt, w) in enumerate(parts):
            frac0 = acc / tot
            acc += w
            frac1 = acc / tot
            t0 = c["t0"] + (c["t1"] - c["t0"]) * frac0
            t1 = c["t0"] + (c["t1"] - c["t0"]) * frac1
            # 边界：起点在其前 0.45s 内找最低能量；终点在其后 0.45s 内找最低能量
            s = align(y, max(c["t0"] - 0.20, t0 - 0.45), min(t0 + 0.10, t1), "min")
            e = align(y, max(t1 - 0.10, s + 0.3), min(t1 + 0.45, len(y) / SR), "min")
            dur = e - s
            if dur < MIN_DUR or dur > MAX_DUR:
                continue
            cid = "c%03d_p%d" % (c["i"], k)
            seg = y[int(s * SR):int(e * SR)]
            # 两端各加 20ms 淡入淡出，避免切点爆音
            n = int(0.02 * SR)
            if len(seg) > 2 * n:
                seg = seg.copy()
                seg[:n] *= np.linspace(0, 1, n)
                seg[-n:] *= np.linspace(1, 0, n)
            sf.write(os.path.join(CAND, cid + ".wav"), seg, SR, subtype="PCM_16")
            meta.append(dict(cid=cid, src_idx=c["i"], part=k, n_parts=len(parts),
                             t0=round(s, 3), t1=round(e, 3), dur=round(dur, 2),
                             text=pt, multi=bool(c.get("multi")), start_cue=round(c["t0"], 2)))
    json.dump(meta, open(os.path.join(OUT, "cut_meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("切出 %d 段（来自 %d 条 cue）" % (len(meta), len(cues)))
    import collections
    print("  多说话人拆分占 %d 段" % sum(1 for m in meta if m["n_parts"] > 1))
    print("  时长 p10 %.1f p50 %.1f p90 %.1f" % tuple(np.percentile([m["dur"] for m in meta], [10, 50, 90])))


def cmd_meas():
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.join(HERE, "emo_bench"))
    from _mut_all import M, to16, fbank
    import parselmouth
    import ser as S
    import _nat_guard as NG

    def nrm(v):
        return v / (np.linalg.norm(v) + 1e-9)

    meta = json.load(open(os.path.join(OUT, "cut_meta.json"), encoding="utf-8"))
    m = M("r34")
    # 角色中心：只用「组内自洽」的档建，剔掉已知污染的 begging（F0 67~463 跨一个人不可能）
    import glob
    trust_skip = ("Thomas_begging", "Thomas_nervous_2")
    lib = {}
    for p in sorted(glob.glob(os.path.join(HERE, "_cloud_backup/voice_lib/*.wav"))):
        k = os.path.basename(p)[:-4]
        if k.startswith(trust_skip):
            continue
        lib[k] = nrm(m.emb_f(fbank(to16(p), m.cmn)))
    import collections
    G = collections.defaultdict(list)
    for k, e in lib.items():
        G[k.split("_")[0]].append(e)
    cen = {r: nrm(np.mean(v, 0)) for r, v in G.items()}

    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))
    out = []
    for i, mm in enumerate(meta, 1):
        p = os.path.join(CAND, mm["cid"] + ".wav")
        y, sr = sf.read(p, dtype="float32", always_2d=True)
        y = y.mean(axis=1)
        # 有声占比
        f = int(0.02 * sr)
        n = len(y) // f
        db = np.array([rms_db(y[j * f:(j + 1) * f]) for j in range(n)]) if n else np.array([-99.0])
        thr = max(db.max() - 30, -60)
        voiced = float((db > thr).mean())
        # F0
        snd = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr)
        pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=500)
        fv = pit.selected_array["frequency"]
        fv = fv[fv > 0]
        f0 = float(np.median(fv)) if len(fv) else 0.0
        # 说话人
        e = nrm(m.emb_f(fbank(to16(p), m.cmn)))
        sc = {r: float(e @ c) for r, c in cen.items()}
        order = sorted(sc.items(), key=lambda x: -x[1])
        # 情绪
        try:
            es = e2v.score(p) or {}
            top = es.get("_top", "")
            eprob = float(es.get(top, 0)) if top else 0.0
        except Exception:
            top, eprob = "", 0.0
        # 自然度
        try:
            nat = NG.raw(p)
            mos = nat.get("nq_mos")
        except Exception:
            mos = None
        out.append(dict(mm, voiced=round(voiced, 3), f0=round(f0, 1),
                        role=order[0][0], rcos=round(order[0][1], 3),
                        role2=order[1][0], rcos2=round(order[1][1], 3),
                        margin=round(order[0][1] - order[1][1], 3),
                        e2v=top, eprob=round(eprob, 3), mos=(round(mos, 2) if mos else None)))
        if i % 25 == 0:
            print("  %d/%d" % (i, len(meta)), flush=True)
    json.dump(out, open(MEAS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("测完 %d 段 -> %s" % (len(out), MEAS))


def cmd_table():
    rows = json.load(open(MEAS, encoding="utf-8"))
    # 候选门槛：有声≥0.55、MOS≥2.0、角色 margin≥0.05
    ok = [r for r in rows if r["voiced"] >= 0.55 and (r["mos"] or 0) >= 2.0 and r["margin"] >= 0.05]
    print("总 %d | 过基础门 %d" % (len(rows), len(ok)))
    import collections
    print("角色分布:", dict(collections.Counter(r["role"] for r in ok)))
    print()
    print("%-12s %-9s %-9s %5s %5s %5s %5s %5s  %s" %
          ("cid", "role", "e2v", "dur", "f0", "cos", "marg", "MOS", "text"))
    for r in sorted(ok, key=lambda x: (-x["margin"], -(x["mos"] or 0)))[:60]:
        print("%-12s %-9s %-9s %5.1f %5.0f %5.2f %5.2f %5.2f  %s" %
              (r["cid"], r["role"], (r["e2v"] or "-")[:9], r["dur"], r["f0"],
               r["rcos"], r["margin"], r["mos"] or 0, r["text"][:44]))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cut"
    {"cut": cmd_cut, "meas": cmd_meas, "table": cmd_table}[cmd]()
