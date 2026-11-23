# -*- coding: utf-8 -*-
"""逐段音色检测：定位"前面没问题、后面炸了"。

同一条音频内部切段 → 每段循环补长到 2s（CAM++ 需要 >=1.5s 才稳）
→ 段间两两余弦相似度 → 每段「与其余段的平均相似度」。
内部互比，避开跨锚点偏差和循环补长的系统性偏差。

判据：某段与其余段平均相似度 < 0.55 ⇒ 该段音色偏离
      < 0.45 ⇒ 严重偏离，必须单独重生成该段

本脚本只用 numpy + wave + onnxruntime（不依赖 soundfile/parselmouth），
需用装有 kaldi_native_fbank 的解释器运行：
    C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe

用法：
    python ch123_segcheck.py ch123_clean/L068.wav [more.wav ...]
    python ch123_segcheck.py --dir ch123_clean
"""
import os, sys, glob, json, itertools, wave, subprocess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
LAB = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab"
sys.path.insert(0, LAB)
import spk_embed as SPK

FF = r"E:/tool/oopz/ffmpeg.exe"
MIN_SEG = 0.25
PAD_TO = 2.0
SIL_DB = -45.0
SEGDIR = os.environ.get("SEGCHK_DIR", "_segchk")   # 2026-11-11 可外部指定临时目录
GAP_MIN = 0.12          # 段间最小静音


def read_wav(path):
    """任意 wav -> (float32 单声道, sr)。非 48k/非单声道先转。"""
    try:
        w = wave.open(path)
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
        w.close()
        if sw == 2:
            a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif sw == 4:
            a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        elif sw == 3:
            b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            v = np.where(v >= 1 << 23, v - (1 << 24), v)
            a = v.astype(np.float32) / 8388608.0
        else:
            raise ValueError("sampwidth %d" % sw)
        if ch > 1:
            a = a.reshape(-1, ch).mean(1)
        return a, sr
    except Exception:
        dst = os.path.join(SEGDIR, "_tmp16.wav")
        os.makedirs(SEGDIR, exist_ok=True)
        subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", path,
                        "-ac", "1", "-c:a", "pcm_s16le", dst], capture_output=True)
        return read_wav(dst)


def write_wav(path, a, sr):
    a = np.clip(a, -1.0, 1.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((a * 32767).astype("<i2").tobytes())


def frame_db(a, sr, win=0.02, hop=0.01):
    w = int(win * sr)
    h = int(hop * sr)
    out = []
    for i in range(0, max(1, len(a) - w), h):
        s = a[i:i + w]
        out.append(20 * np.log10(np.sqrt((s ** 2).mean()) + 1e-12))
    return np.array(out)


def split_at_silence(a, sr, min_gap=GAP_MIN):
    db = frame_db(a, sr)
    voiced = db > SIL_DB
    segs = []
    i = 0
    n = len(voiced)
    while i < n:
        if not voiced[i]:
            i += 1
            continue
        j = i
        while j < n and voiced[j]:
            j += 1
        segs.append((i * 0.01, min(len(a) / sr, j * 0.01)))
        i = j
    # 合并间隔 < min_gap 的段
    merged = []
    for s0, s1 in segs:
        if merged and s0 - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], s1)
        else:
            merged.append((s0, s1))
    return [(s0, s1) for s0, s1 in merged if s1 - s0 >= MIN_SEG]


def f0_med(a, sr, s0, s1):
    """自相关估计该段 F0 中位（60-500Hz）"""
    seg = a[int(s0 * sr):int(s1 * sr)]
    if len(seg) < 1024:
        return 0.0
    seg = seg - seg.mean()
    vals = []
    w = int(0.04 * sr)
    h = int(0.02 * sr)
    for i in range(0, len(seg) - w, h):
        f = seg[i:i + w]
        e = (f ** 2).sum()
        if e < 1e-7:
            continue
        ac = np.correlate(f, f, "full")[len(f) - 1:]
        lo, hi = int(sr / 500), int(sr / 60)
        if hi >= len(ac):
            continue
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] / ac[0] < 0.3:
            continue
        vals.append(sr / k)
    return float(np.median(vals)) if vals else 0.0


def rms_voiced_db(a, sr):
    db = frame_db(a, sr)
    v = db[db > SIL_DB]
    return float(v.mean()) if len(v) else -120.0


def check(path, verbose=True):
    a, sr = read_wav(path)
    raw = split_at_silence(a, sr)
    if len(raw) < 2:
        if verbose:
            print("\n%s  只有 %d 段，无法段间互比" % (os.path.basename(path), len(raw)))
        return None
    os.makedirs(SEGDIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    info = []
    for i, (s0, s1) in enumerate(raw):
        seg = a[int(s0 * sr):int(s1 * sr)]
        d = len(seg) / sr
        p = os.path.join(SEGDIR, "%s_p%d.wav" % (base, i))
        if d < PAD_TO:
            seg = np.tile(seg, int(np.ceil(PAD_TO / d)))
        write_wav(p, seg, sr)
        info.append({"i": i, "t0": s0, "t1": s1, "dur": d,
                     "f0": f0_med(a, sr, s0, s1),
                     "db": rms_voiced_db(a[int(s0 * sr):int(s1 * sr)], sr), "p": p})

    embs = [SPK.embed(x["p"]) for x in info]
    n = len(info)
    sim = np.eye(n)
    for i, j in itertools.combinations(range(n), 2):
        c = SPK.cos(embs[i], embs[j])
        sim[i, j] = sim[j, i] = c
    rows = [float(np.mean([sim[i, j] for j in range(n) if j != i])) for i in range(n)]
    worst = int(np.argmin(rows))

    # 附加判据：F0 跨度、相邻段电平差
    f0s = [x["f0"] for x in info if x["f0"] > 0]
    f0_span = (max(f0s) - min(f0s)) if len(f0s) >= 2 else 0.0
    lvl = [x["db"] for x in info]
    lvl_max = max(abs(lvl[i] - lvl[i - 1]) for i in range(1, len(lvl))) if len(lvl) >= 2 else 0.0

    if verbose:
        print("\n%s  (%d 段, %.2fs)" % (os.path.basename(path), n, len(a) / sr))
        print("  %-4s %11s %7s %6s %7s %8s" % ("段", "起-止", "时长", "F0", "dB", "相似度"))
        for i, x in enumerate(info):
            v = rows[i]
            tag = "OK" if v >= 0.55 else ("⚠ 偏离" if v >= 0.45 else "✗ 严重偏离")
            print("  p%-3d %5.2f-%5.2f %6.2fs %6.0f %6.1f %8.3f  %s"
                  % (x["i"], x["t0"], x["t1"], x["dur"], x["f0"], x["db"], v, tag))
        flag = []
        if f0_span > 40:
            flag.append("F0 跨度 %.0fHz（>40，音高跳）" % f0_span)
        if lvl_max > 6:
            flag.append("相邻段电平差 %.1fdB（>6）" % lvl_max)
        if flag:
            print("  ⚠ " + " / ".join(flag))
        if min(rows) < 0.55:
            print("  段间相似度矩阵：")
            for i in range(n):
                print("    " + " ".join("%.2f" % sim[i, j] for j in range(n)))
            print("  → 问题段 p%d（%.2f-%.2fs, F0 %.0f）"
                  % (info[worst]["i"], info[worst]["t0"], info[worst]["t1"], info[worst]["f0"]))
    return {"path": path, "n": n, "rows": rows, "worst": worst, "info": info,
            "f0_span": f0_span, "lvl_max": lvl_max}


def main():
    args = [x for x in sys.argv[1:]]
    if args and args[0] == "--dir":
        files = sorted(glob.glob(os.path.join(args[1], "*.wav")))
    elif args and args[0] == "--json":
        files = [x for x in args[1:]]
    else:
        files = args
    bad = []
    for f in files:
        try:
            r = check(f)
        except Exception as e:
            print("%s ERR %s" % (f, e))
            continue
        if r and min(r["rows"]) < 0.55:
            bad.append((os.path.basename(f), min(r["rows"]), r["info"][r["worst"]]["i"]))
    print("\n" + "=" * 62)
    if bad:
        print("有问题（段相似度 < 0.55）：")
        for b, v, p in sorted(bad, key=lambda x: x[1]):
            print("  %-10s 最低 %.3f  问题段 p%d" % (b, v, p))
    else:
        print("全部通过（每段与其他段相似度 >= 0.55）")


if __name__ == "__main__":
    main()
