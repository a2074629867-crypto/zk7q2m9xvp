# -*- coding: utf-8 -*-
"""步数对重音位置的影响评估（G:/Python310 跑，需要 parselmouth）。

判据：
- top1 词是否随步数改变
- top1 归一化位置 pos_norm 的跨步数极差
- 目标副词的名次是否随步数改变
- 跨步数两两一致率（|Δpos|<=0.10），与跨 seed 基线 32.4% 对照
- 逐词突出度向量的跨步数相关（轮廓是否只是被整体重排）
"""
import json
import math
import os
import re

import numpy as np
import parselmouth

ROOT = "G:/_setup"
WORDS = os.path.join(ROOT, "_step_words.json")
MIN_WIN = 0.06
POS_TOL = 0.10

TARGET = {"n0167": "coldly", "n0112": "deliberately", "n0194": "slowly"}
TEXTS = {
    "n0167": "Moonlight came through the window, coldly, on to the glass.",
    "n0112": "He went forward quite deliberately, being sure of his way, and unafraid.",
    "n0194": "Edmund Hooper went slowly up the four flights of stairs to his own bedroom.",
}


def rd(path):
    import wave
    with wave.open(path, "rb") as w:
        sr, ch, nf = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def rz(x):
    x = np.asarray(x, dtype=np.float64)
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    if mad < 1e-9:
        sd = float(np.std(x))
        return (x - med) / sd if sd > 1e-9 else np.zeros_like(x)
    return 0.6734 * (x - med) / mad


def norm(w):
    return "".join(c for c in w.lower() if c.isalnum())


def gaps(y, sr, thr=-40.0, minlen=0.06):
    hop = max(1, int(0.01 * sr))
    k = len(y) // hop
    r = np.sqrt(np.mean(y[:k * hop].reshape(k, hop) ** 2, axis=1) + 1e-12)
    db = 20.0 * np.log10(r + 1e-12)
    sil = db < thr
    idx = np.where(~sil)[0]
    if not len(idx):
        return [], len(y) / sr
    s, e = idx[0], idx[-1] + 1
    out, i = [], 0
    sil = sil[s:e]
    while i < len(sil):
        if sil[i]:
            j = i
            while j < len(sil) and sil[j]:
                j += 1
            if (j - i) * hop / sr >= minlen:
                out.append(round((j - i) * hop / sr, 2))
            i = j
        else:
            i += 1
    return out, (e - s) * hop / sr


def feats(path, words):
    y, sr = rd(path)
    n = len(y)
    gl, act = gaps(y, sr)
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    pitch = snd.to_pitch(time_step=0.01, pitch_floor=60.0, pitch_ceiling=400.0)
    f = np.asarray(pitch.selected_array["frequency"], dtype=np.float64)
    pt = np.asarray(pitch.xs(), dtype=np.float64)

    rows = []
    for w in words:
        s, e = float(w["start"]), float(w["end"])
        if e - s < MIN_WIN:
            continue
        a, b = int(s * sr), min(n, int(e * sr))
        if b - a < int(MIN_WIN * sr):
            continue
        seg = y[a:b]
        hop = max(1, int(0.02 * sr))
        k = len(seg) // hop
        if k < 1:
            continue
        rms = np.sqrt(np.mean(seg[:k * hop].reshape(k, hop) ** 2, axis=1) + 1e-12)
        e_db = 20.0 * math.log10(float(rms.max()) + 1e-12)
        m = (pt >= s) & (pt <= e) & (f > 0)
        f0 = float(np.median(f[m])) if m.sum() >= 2 else 0.0
        rows.append(dict(w=w["w"], start=s, end=e, dur=e - s, f0=f0, e_db=e_db))

    if len(rows) < 3:
        return None
    durs = np.array([r["dur"] for r in rows])
    dur_ratio = durs / max(1e-6, float(np.median(durs)))
    f0s = np.array([r["f0"] if r["f0"] > 0 else np.nan for r in rows])
    okf = np.isfinite(f0s)
    if okf.sum() >= 2:
        med = float(np.median(f0s[okf]))
        f0_st = np.where(okf, 12.0 * np.log2(np.where(okf, f0s, med) / med), 0.0)
        span = float(np.nanmax(f0_st) - np.nanmin(f0_st))
    else:
        f0_st = np.zeros(len(rows))
        span = 0.0
    e_db = np.array([r["e_db"] for r in rows])
    prom = 0.5 * rz(f0_st) + 0.3 * rz(e_db) + 0.2 * rz(dur_ratio)
    k = int(np.argmax(prom))
    for i, r in enumerate(rows):
        r["f0_st"] = round(float(f0_st[i]), 2)
        r["prom"] = round(float(prom[i]), 3)
    return dict(words=rows, prom=[round(float(v), 3) for v in prom], top=k,
                top_w=rows[k]["w"], pos=round(k / max(1, len(rows) - 1), 3),
                span=round(span, 2), n=len(rows), dur=round(act, 2),
                raw_dur=round(n / sr, 2),
                gaps=gl, vdur=round(act - sum(gl), 2),
                big=[g for g in gl if g > 0.3],
                top3=sorted(range(len(rows)), key=lambda i: -prom[i])[:3])


def main():
    raw = json.load(open(WORDS, encoding="utf-8"))
    data = {}
    for fn, v in raw.items():
        m = re.match(r"(\w+)_s(\d+)\.wav$", fn)
        if not m or "words" not in v:
            continue
        tag, steps = m.group(1), int(m.group(2))
        ft = feats(os.path.join(ROOT, "_step_test", fn), v["words"])
        if not ft:
            continue
        ft["steps"] = steps
        ft["asr"] = v.get("text", "")
        data.setdefault(tag, {})[steps] = ft

    for tag in sorted(data):
        d = data[tag]
        tgt = TARGET.get(tag)
        print("\n" + "=" * 78)
        print("%s  (%d 词)  %s" % (tag.upper(), d[min(d)]["n"], TEXTS.get(tag, "")[:60]))
        print("-" * 78)
        print("%5s %6s %6s %6s %-13s %5s %7s %7s %6s"
              % ("步数", "总长s", "语音s", "停顿数", "top1词", "位置", "目标名次", "目标F0", "目标时长"))
        ranks = {}
        for s in sorted(d):
            v = d[s]
            rk = "-"
            tf0 = tdur = "-"
            if tgt:
                for i, w in enumerate(v["words"]):
                    if norm(w["w"]).startswith(norm(tgt)[:6]):
                        rk = 1 + sum(1 for x in v["words"] if x["prom"] > w["prom"])
                        ranks[s] = (rk, v["n"])
                        tf0 = "%+.2f" % w["f0_st"]
                        tdur = "%.2f" % w["dur"]
                        break
            print("%5d %6.2f %6.2f %6s %-13s %5.3f %7s %7s %6s"
                  % (s, v["dur"], v["vdur"], "%d/%d" % (len(v["gaps"]), len(v["big"])),
                     v["top_w"][:13], v["pos"],
                     ("%d/%d" % ranks[s]) if s in ranks else rk, tf0, tdur))

        ss = sorted(d)
        # 跨步数一致性
        pairs = same = 0
        topsame = 0
        tpairs = 0
        for i in range(len(ss)):
            for j in range(i + 1, len(ss)):
                pairs += 1
                if abs(d[ss[i]]["pos"] - d[ss[j]]["pos"]) <= POS_TOL:
                    same += 1
                tpairs += 1
                if norm(d[ss[i]]["top_w"]) == norm(d[ss[j]]["top_w"]):
                    topsame += 1
        poses = [d[s]["pos"] for s in ss]
        print("-" * 78)
        print("跨步数：位置两两一致 %.0f%%（%d/%d） | top1 同词 %.0f%%（%d/%d） | pos 极差 %.3f"
              % (100.0 * same / pairs, same, pairs, 100.0 * topsame / tpairs, topsame, tpairs,
                 max(poses) - min(poses)))
        print("F0 跨度随步数 %s 半音" % ["%.1f" % d[s]["span"] for s in ss])
        print("大停顿随步数 %s" % [d[s]["big"] for s in ss])
        if len({d[s]["n"] for s in ss}) == 1:
            ov = []
            for i in range(len(ss)):
                for j in range(i + 1, len(ss)):
                    a = set(d[ss[i]]["top3"])
                    b = set(d[ss[j]]["top3"])
                    ov.append(len(a & b) / 3.0)
            print("top3 集合重叠 平均 %.0f%%（100%%=前三名完全一致）" % (100.0 * sum(ov) / len(ov)))
        if ranks:
            rv = [ranks[s][0] for s in sorted(ranks)]
            print("目标词名次序列 %s（越小越好，n=%d）" % (rv, ranks[sorted(ranks)[0]][1]))

        # 逐词突出度轮廓相关（词数需一致）
        ns = {s: d[s]["n"] for s in ss}
        if len(set(ns.values())) == 1:
            base = d[ss[0]]["prom"]
            cs = []
            for s in ss[1:]:
                a = np.array(base)
                b = np.array(d[s]["prom"])
                if a.std() > 1e-9 and b.std() > 1e-9:
                    cs.append(float(np.corrcoef(a, b)[0, 1]))
            if cs:
                print("突出度轮廓 vs %d步：中位 r=%.2f  最低 r=%.2f"
                      % (ss[0], float(np.median(cs)), min(cs)))
        else:
            print("词数不一致 %s（ASR 切词差异，轮廓相关跳过）" % ns)

    print("\n" + "=" * 78)
    print("参照：跨 seed 位置一致率 32.4%（ch1 545 条候选实测）")


if __name__ == "__main__":
    main()
