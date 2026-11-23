# -*- coding: utf-8 -*-
"""整片长音轨 → 切句 → 声纹聚类 → 报「有几个人声、各是什么声部」。

用途：从一部没字幕、没时间码的电影里，把某个角色的可用句子挖出来。
不需要任何模板（冷启动），也不依赖字幕——先按声音分堆，再靠文本点名。

与 voice_cluster.py 的分工：
  voice_cluster.py 吃「已切好的 cue 目录」（有字幕时用）
  film_seg.py      吃「一整条音轨」（没字幕 / 只想拿音轨时用）

切句判据（都在实测里调过，改之前先想清楚）：
  - 帧长 25ms / 帧移 10ms，能量阈值取「底噪 +6dB」与「语音峰 −30dB」的较大者
  - 短于 0.30s 的静音不切（连读的句中停顿不能断句，否则毁整句弧线）
  - 短于 0.9s 的段丢掉（不够判声纹，也做不了参考音）
  - 长于 12s 的段在内部最静处切开（避免一段里塞进两三个人）

用法:
  python film_seg.py --wav films/wav/hopegap.wav --out out/hope_seg --kmax 6
"""
import argparse
import collections
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")


def frames_db(x, sr, win=0.025, hop=0.010):
    w = int(win * sr)
    h = int(hop * sr)
    n = max(1, (len(x) - w) // h + 1)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    idx = np.clip(idx, 0, len(x) - 1)
    fr = x[idx]
    rms = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9), hop


def segment(x, sr, min_gap=0.30, min_dur=0.90, max_dur=12.0, pad=0.06):
    db, hop = frames_db(x, sr)
    floor = np.percentile(db, 20)
    peak = np.percentile(db, 95)
    thr = max(floor + 6.0, peak - 30.0)
    v = db > thr

    # 合并短静音
    gap = int(min_gap / hop)
    run = 0
    for i in range(len(v)):
        if v[i]:
            if 0 < run < gap and i - run - 1 >= 0:
                v[i - run:i] = True
            run = 0
        else:
            run += 1

    # 找出连续段
    segs = []
    i = 0
    while i < len(v):
        if v[i]:
            j = i
            while j + 1 < len(v) and v[j + 1]:
                j += 1
            segs.append((i, j + 1))
            i = j + 1
        else:
            i += 1

    out = []
    for a, b in segs:
        t0, t1 = a * hop - pad, b * hop + pad
        t0, t1 = max(0.0, t0), min(len(x) / sr, t1)
        if t1 - t0 < min_dur:
            continue
        while t1 - t0 > max_dur:
            # 在 [0.35, 0.65] 区间找最静的一帧当切点
            lo = int((t0 + (t1 - t0) * 0.35) / hop)
            hi = int((t0 + (t1 - t0) * 0.65) / hop)
            lo, hi = max(a, lo), min(b - 1, hi)
            k = lo + int(np.argmin(db[lo:hi])) if hi > lo else (lo + hi) // 2
            out.append((t0, k * hop))
            t0 = k * hop
        if t1 - t0 >= min_dur:
            out.append((t0, t1))
    return out, thr, floor, peak


def median_f0(x, sr, fmin=60, fmax=450):
    import parselmouth
    if len(x) < sr * 0.2:
        return 0.0
    snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=sr)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=fmin, pitch_ceiling=fmax)
    f = pit.selected_array["frequency"]
    f = f[f > 0]
    return float(np.median(f)) if len(f) else 0.0


def band(f0):
    if f0 <= 0:
        return "?"
    if f0 < 145:
        return "成年男"
    if f0 < 175:
        return "界(男/女)"
    if f0 < 225:
        return "成年女"
    if f0 < 240:
        return "界(女/童)"
    return "儿童"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--out", required=True, help="输出目录（json + 切出的 wav）")
    ap.add_argument("--kmax", type=int, default=7)
    ap.add_argument("--kmin", type=int, default=2)
    ap.add_argument("--model", default="r34")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 分钟（调试用）")
    ap.add_argument("--target-k", type=int, default=0, help="直接指定 k 落盘")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    wav_dir = os.path.join(a.out, "seg")
    os.makedirs(wav_dir, exist_ok=True)

    x, sr = sf.read(a.wav, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if a.limit:
        x = x[: int(a.limit * 60 * sr)]
    print("音轨 %.1f 分钟 sr=%d" % (len(x) / sr / 60, sr), flush=True)

    segs, thr, floor, peak = segment(x, sr)
    print("切出 %d 段（阈值 %.1f dBFS，底噪 %.1f，峰 %.1f）" % (len(segs), thr, floor, peak), flush=True)

    from chain_check import EmoVoice
    m = EmoVoice(model=a.model).m

    from sklearn.cluster import AgglomerativeClustering
    emb, rows = [], []
    for i, (t0, t1) in enumerate(segs, 1):
        sub = x[int(t0 * sr):int(t1 * sr)]
        p = os.path.join(wav_dir, "s%05d_%08.2f_%08.2f.wav" % (i, t0, t1))
        sf.write(p, sub, sr, subtype="PCM_16")
        emb.append(m.embed(p))
        rows.append({"i": i, "t0": round(t0, 2), "t1": round(t1, 2),
                     "dur": round(t1 - t0, 2), "path": p, "f0": 0.0})
        if i % 100 == 0:
            print("  提特征 %d/%d" % (i, len(segs)), flush=True)

    E = np.array(emb, dtype=np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9

    # F0 只抽样算（parselmouth 慢），每簇后面再补
    print("\n%-4s %s" % ("k", "各簇 (条数 / F0中位 / 声部)"))
    labs = {}
    for k in range(a.kmin, a.kmax + 1):
        lab = AgglomerativeClustering(n_clusters=k, metric="cosine",
                                      linkage="average").fit_predict(E)
        labs[k] = lab
        sizes = collections.Counter(lab)
        parts = []
        for c in sorted(sizes, key=lambda z: -sizes[z]):
            idx = [i for i in range(len(lab)) if lab[i] == c][:12]
            f0 = np.median([median_f0(x[int(rows[i]["t0"] * sr):int(rows[i]["t1"] * sr)], sr)
                            for i in idx])
            parts.append("%d/%0.0fHz/%s" % (sizes[c], f0, band(f0)))
        print("%-4d %s" % (k, "  ".join(parts)), flush=True)

    k = a.target_k or int(os.environ.get("K", 4))
    k = min(max(k, a.kmin), a.kmax)
    lab = labs[k]
    for r, c in zip(rows, lab):
        r["cl"] = int(c)
    # 每簇全量算 F0（只算有限条，够判断声部）
    for c in sorted(set(lab)):
        idx = [i for i in range(len(lab)) if lab[i] == c]
        for i in idx:
            r = rows[i]
            r["f0"] = round(median_f0(x[int(r["t0"] * sr):int(r["t1"] * sr)], sr), 1)

    json.dump({"wav": a.wav, "k": k, "thr": thr, "rows": rows},
              open(os.path.join(a.out, "segments.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\n=== k=%d 落盘 %s/segments.json ===" % (k, a.out))
    for c in sorted(set(lab), key=lambda z: -int((lab == z).sum())):
        idx = [i for i in range(len(lab)) if lab[i] == c]
        f0s = [rows[i]["f0"] for i in idx if rows[i]["f0"] > 0]
        print("簇 %d：%d 条  F0 中位 %0.0f  %s" % (
            c, len(idx), np.median(f0s) if f0s else 0, band(np.median(f0s) if f0s else 0)))
        for i in idx[:5]:
            r = rows[i]
            print("    %8.1fs %4.1fs %s" % (r["t0"], r["dur"], os.path.basename(r["path"])))


if __name__ == "__main__":
    main()
