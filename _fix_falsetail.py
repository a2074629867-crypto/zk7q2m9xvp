# -*- coding: utf-8 -*-
"""修「数字零缺口 + 无基频噪声」伪影（一次性分类，再整段重建）。

分类在**原始音频**上做一次，之后按区间重建，避免反复裁剪造成索引漂移：
- tail：伪噪之后到末尾没有浊音 → 裁到零缺口起点，前接 25ms 淡出
- head：伪噪之前没有浊音 → 从噪声结束点起，5ms 淡入
- mid ：两侧都有浊音 → 用本文件自己的底噪填满同长度（保节奏）
最后：去尾静音（留 0.10s）+ voiced RMS 归一 −24 dBFS。
"""
import os, sys, json, shutil, argparse
import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
SRC = os.path.join(ROOT, "_audio_ch123", "out")


def load(p):
    y, sr = sf.read(p, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    return y, sr


def frame_stats(y, sr):
    w, h = int(0.025 * sr), int(0.010 * sr)
    n = 1 + max(0, (len(y) - w)) // h
    idx = np.clip(np.arange(w)[None, :] + h * np.arange(n)[:, None], 0, len(y) - 1)
    seg = y[idx]
    rms = np.sqrt((seg ** 2).mean(1))
    per = np.zeros(n)
    a, b = int(sr / 400), int(sr / 60)
    for i in range(n):
        if rms[i] < 0.01:
            continue
        f = seg[i] - seg[i].mean()
        ac = np.correlate(f, f, "full")[w - 1:]
        if b < len(ac):
            per[i] = ac[int(np.argmax(ac[a:b])) + a] / (ac[0] + 1e-12)
    return (per > 0.45) & (rms > 0.01), h / sr


def floor_ref(y, sr):
    h = int(0.12 * sr)
    best = (1e9, 0)
    for i in range(0, max(1, len(y) - h), int(0.02 * sr)):
        r = np.sqrt((y[i:i + h] ** 2).mean())
        if r < best[0]:
            best = (r, i)
    return y[best[1]:best[1] + h].copy()


def fade(a, n_in=0, n_out=0):
    a = a.copy()
    if n_in > 0 and len(a) > n_in:
        a[:n_in] *= np.linspace(0, 1, n_in)
    if n_out > 0 and len(a) > n_out:
        a[-n_out:] *= np.linspace(1, 0, n_out)
    return a


def voiced_mean_db(y, sr, rel=25.0):
    """有声段平均电平。**相对阈值**（比最响帧低 rel dB 以内），
    不用绝对 −45dBFS：绝对阈值会随增益漂移，归一化后集合变了，重心就偏
    （c2_0299 原 −29.0 → 归一后反而 −30.1，就是这个坑）。"""
    w, h = int(0.010 * sr), int(0.005 * sr)
    n = 1 + max(0, len(y) - w) // h
    idx = np.clip(np.arange(w)[None, :] + h * np.arange(n)[:, None], 0, len(y) - 1)
    db = 20 * np.log10(np.sqrt((y[idx] ** 2).mean(1)) + 1e-12)
    top = float(db.max())
    if top < -100:
        return -120.0
    return float(db[db > top - rel].mean())


def norm24(y, sr, target=-24.0, ceil=0.97):
    cur = voiced_mean_db(y, sr)
    y = y * 10 ** ((target - cur) / 20.0)
    pk = float(np.abs(y).max())
    if pk > ceil:                      # 限峰优先于电平：宁可低 1dB 也不削顶
        y = y * (ceil / pk)
    return y, voiced_mean_db(y, sr)


def trim_tail(y, sr, keep=0.10):
    w, h = int(0.025 * sr), int(0.010 * sr)
    n = 1 + max(0, len(y) - w) // h
    db = np.array([20 * np.log10(np.sqrt((y[i * h:i * h + w] ** 2).mean()) + 1e-12)
                   for i in range(n)])
    v = np.where(db > -50)[0]
    if not len(v):
        return y
    return y[:min(len(y), v[-1] * h + w + int(keep * sr))]


def fix_one(rid, hits, out_path):
    y, sr = load(os.path.join(SRC, rid + ".wav"))
    dur0 = len(y) / sr
    voiced, step = frame_stats(y, sr)
    nf = floor_ref(y, sr)

    # 分类：注意 e 是**采样点**，转帧号要 / sr / step
    edits = []
    for h in sorted(hits, key=lambda x: x["zero"][0]):
        z0 = int(h["zero"][0] * sr)
        e = int((h["zero"][1] + h["noise_s"]) * sr)
        i0, i1 = int((e / sr + 0.02) / step), len(voiced)
        has_after = bool(np.any(voiced[i0:i1])) if i1 > i0 else False
        j1 = max(1, int((h["zero"][0] - 0.01) / step))
        has_before = bool(np.any(voiced[:j1]))
        if not has_after:
            edits.append(("tail", max(int(0.025 * sr), z0), h["noise_s"]))
        elif not has_before:
            edits.append(("head", e, h["noise_s"]))
        else:
            edits.append(("mid", z0, e, h["noise_s"]))

    # 合并相邻 tail
    merged = []
    for ed in sorted(edits, key=lambda x: x[1]):
        if merged and ed[0] == "tail" and merged[-1][0] == "tail":
            merged[-1] = ("tail", max(merged[-1][1], ed[1]), merged[-1][2] + ed[2])
        else:
            merged.append(list(ed) and tuple(ed))

    out = []
    cur = 0
    for ed in merged:
        if ed[0] == "tail":
            out.append(y[cur:ed[1]])
            cur = len(y)
        elif ed[0] == "head":
            cur = ed[1]
        else:                                     # mid
            z0, e = ed[1], ed[2]
            out.append(y[cur:z0])
            n = e - z0
            rep = nf.copy()
            while len(rep) < n:
                rep = np.concatenate([rep, nf])
            out.append(fade(rep[:n], int(0.010 * sr), int(0.010 * sr)))
            cur = e
    out.append(y[cur:])
    y2 = np.concatenate(out) if len(out) > 1 else out[0]
    y2 = fade(y2, int(0.005 * sr), int(0.025 * sr))
    y2 = trim_tail(y2, sr)
    y2, lv = norm24(y2, sr, -24.0)

    sf.write(out_path, y2.astype(np.float32), sr, subtype="PCM_16")
    ops = ["%s %.3fs" % (e[0], e[-1]) for e in merged]
    return {"id": rid, "dur_before": round(dur0, 3), "dur_after": round(len(y2) / sr, 3),
            "ops": ops}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default="_scan_falsetail2.json")
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default="_sweep/falsetail")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--bak", default="_bak_falsetail_1124")
    a = ap.parse_args()

    res = json.load(open(os.path.join(ROOT, a.scan), encoding="utf-8"))
    ids = [x for x in a.ids.split(",") if x] or [k for k, v in res.items() if v.get("n")]
    od = os.path.join(ROOT, a.out)
    os.makedirs(od, exist_ok=True)
    rows = []
    for rid in ids:
        v = res.get(rid) or {}
        if not v.get("hits"):
            continue
        try:
            rows.append(fix_one(rid, v["hits"], os.path.join(od, rid + ".wav")))
        except Exception as ex:
            print("  FAIL %s: %s" % (rid, ex))
    print("\n%-9s %7s %7s  %s" % ("id", "before", "after", "ops"))
    for r in rows:
        print("%-9s %7.2f %7.2f  %s" % (r["id"], r["dur_before"], r["dur_after"],
                                        "; ".join(r["ops"])))
    json.dump(rows, open(os.path.join(ROOT, "_fix_falsetail.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if a.apply:
        bd = os.path.join(ROOT, a.bak)
        os.makedirs(bd, exist_ok=True)
        for r in rows:
            s0 = os.path.join(SRC, r["id"] + ".wav")
            d0 = os.path.join(bd, r["id"] + ".wav")
            if not os.path.exists(d0):
                shutil.copy2(s0, d0)
            shutil.copy2(os.path.join(od, r["id"] + ".wav"), s0)
        print("\n已回填 %d 条，备份 %s" % (len(rows), a.bak))


if __name__ == "__main__":
    main()
