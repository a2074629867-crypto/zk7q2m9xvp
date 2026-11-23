# -*- coding: utf-8 -*-
"""pick_refs.py —— 从 v6 切片划分出的段落里挑参考音频候选

- 段落 = 若干物理相邻的切片合并（6~12s，自带自然句间停顿）
- 所有指标直接从母带 wonder_train_df3hp.wav 的对应区间现算（能量 VAD，-35dB rel peak）
- 避开真人对齐锚点区间（768.5~796.4s），防声纹背题
"""
import re, json, wave
import numpy as np
from pathlib import Path

MASTER = r"G:/_setup/_denoise_full/wonder_train_df3hp.wav"
SLICED = Path(r"G:/GPT-SoVITS/_dataset_v5full/sliced_v6")
LABELS = Path(r"G:/_setup/gsv5probe/logs/mcconaughey_v6/2-name2text.txt")
OUTDIR = Path(r"E:/tts-models/acpp/out/refs")
OUTDIR.mkdir(parents=True, exist_ok=True)
SR = 32000
ANCHOR = (768.5, 796.4)


def load_master():
    with wave.open(MASTER, "rb") as w:
        sr, ch, sw, nf = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nf)
    assert sr == SR and sw == 2, (sr, sw)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a


def vad_stats(x, rel_db=-35.0, hop_s=0.01):
    hop = max(1, int(SR * hop_s))
    n = len(x) // hop
    if n == 0:
        return 0.0, len(x) / SR
    fr = x[:n * hop].reshape(n, hop)
    rms = np.sqrt((fr ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    sp = db > (db.max() + rel_db)
    best = cur = 0
    for v in sp:
        if v:
            cur = 0
        else:
            cur += 1
            best = max(best, cur)
    return float(sp.mean()), best * hop_s


def f0_stats(x):
    hop = int(SR * 0.02); win = int(SR * 0.04)
    lo, hi = int(SR / 400), int(SR / 40)
    f0s = []
    for i in range(0, len(x) - win, hop):
        fr = x[i:i + win]
        if np.sqrt((fr ** 2).mean()) < 0.01:
            continue
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, "full")[win - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        if not len(seg):
            continue
        k = int(np.argmax(seg)) + lo
        if ac[k] / ac[0] < 0.3:
            continue
        f0s.append(SR / k)
    if not f0s:
        return 0.0, 0.0
    a = np.array(f0s)
    return float(np.median(a)), float(np.std(a))


def main():
    labels = {}
    for line in LABELS.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) >= 4:
            labels[Path(p[0]).name] = p[3].strip()

    items = []
    for f in sorted(SLICED.glob("*.wav")):
        m = re.search(r"_(\d+)_(\d+)\.wav$", f.name)
        if m:
            items.append(dict(s=int(m.group(1)) / SR, e=int(m.group(2)) / SR,
                              text=labels.get(f.name, "")))
    items.sort(key=lambda x: x["s"])
    print("v6 切片 %d 个" % len(items))

    groups, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            txt = " ".join(c["text"] for c in cur).strip()
            if len(txt.split()) >= 8:
                groups.append(dict(s=cur[0]["s"], e=cur[-1]["e"], text=txt, nparts=len(cur)))
        cur = []

    for it in items:
        if not cur:
            cur = [it]; continue
        if it["s"] - cur[-1]["e"] > 0.05 or it["e"] - cur[0]["s"] > 12.0:
            flush(); cur = [it]
        else:
            cur.append(it)
    flush()
    print("候选段落 %d 个" % len(groups))

    master = load_master()
    print("母带 %.1fs" % (len(master) / SR))

    scored = []
    for g in groups:
        s, e = int(g["s"] * SR), int(g["e"] * SR)
        seg = master[s:e]
        dur = len(seg) / SR
        voiced, maxsil = vad_stats(seg)
        f0, f0sd = f0_stats(seg)
        nw = len(g["text"].split())
        g.update(dur=dur, voiced=voiced, maxsil=maxsil, f0=f0, f0sd=f0sd, nw=nw,
                 wpm=nw / dur * 60, wpm_v=nw / max(dur * voiced, 1e-6) * 60)
        g["in_anchor"] = not (g["e"] <= ANCHOR[0] or g["s"] >= ANCHOR[1])
        scored.append(g)

    ok = [g for g in scored
          if 4.5 <= g["dur"] <= 12.0 and g["voiced"] >= 0.55 and g["maxsil"] <= 0.90
          and not g["in_anchor"] and 100 <= g["wpm_v"] <= 220]
    print("通过过滤: %d 个  (4.5-12s / voiced>=0.55 / maxsil<=0.90 / 语音内语速 100-220wpm)" % len(ok))

    ok.sort(key=lambda g: (-g["voiced"] - 0.5 * g["maxsil"]))
    buckets = {"4.5-6s": [], "6-8s": [], "8-10s": [], "10-12s": []}
    for g in ok:
        k = ("4.5-6s" if g["dur"] < 6 else ("6-8s" if g["dur"] < 8
             else ("8-10s" if g["dur"] < 10 else "10-12s")))
        g["bucket"] = k
        if len(buckets[k]) < 4:
            buckets[k].append(g)
    picked = sorted([g for v in buckets.values() for g in v], key=lambda g: g["s"])

    print("\n=== 切出候选 ===")
    for i, g in enumerate(picked):
        s, e = int(g["s"] * SR), int(g["e"] * SR)
        seg = master[s:e]
        tag = "ref%02d_%04.1fs_%s" % (i, g["dur"], g["bucket"].replace(".", "p").replace("-", "_"))
        p = OUTDIR / (tag + ".wav")
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(np.clip(seg * 32767, -32768, 32767).astype("<i2").tobytes())
        g.update(tag=tag, path=str(p))
        print("%-24s %5.2fs voi=%.2f ms=%.2f 词=%2d %3.0fwpm F0=%.0f±%.0f | %s" % (
            tag, g["dur"], g["voiced"], g["maxsil"], g["nw"], g["wpm"], g["f0"], g["f0sd"], g["text"][:50]))

    # ---- 两个基准参考 ----
    base = []
    # ① 当前在用的（来自未降噪的 wonder_train.wav，8.3s）
    cur = Path(r"G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav")
    if cur.exists():
        s0, e0 = 18112640, 18378240
        seg = master[s0:e0]
        p = OUTDIR / "baseA_oldnoisy_8.3s.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(np.clip(seg * 32767, -32768, 32767).astype("<i2").tobytes())
        v, ms_ = vad_stats(seg)
        # baseA 的统计要读它自己那份（未降噪）的波形
        with wave.open(str(cur), "rb") as w:
            rawA = w.readframes(w.getnframes())
        aA = np.frombuffer(rawA, dtype="<i2").astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            aA = aA.reshape(-1, w.getnchannels()).mean(axis=1)
        vA, msA = vad_stats(aA)
        base.append(dict(tag="baseA_oldnoisy_8.3s", path=str(cur), dur=len(aA) / SR,
                         text="called Sirius, is reaching Earth after traveling at 186,000 miles per second.",
                         voiced=vA, maxsil=msA, kind="baseline_noisy", bucket="baseline"))
        # ② 同区间但取自 DF3 降噪母带
        p2 = OUTDIR / "baseB_df3hp_8.3s.wav"
        with wave.open(str(p2), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(np.clip(seg * 32767, -32768, 32767).astype("<i2").tobytes())
        base.append(dict(tag="baseB_df3hp_8.3s", path=str(p2), dur=len(seg) / SR,
                         text="called Sirius, is reaching Earth after traveling at 186,000 miles per second.",
                         voiced=v, maxsil=ms_, kind="baseline_denoised_same_seg", bucket="baseline"))
        print("%-24s %5.2fs voi=%.2f ms=%.2f  （基准：原未降噪 / 同段降噪）" % ("baseA/B", len(seg) / SR, v, ms_))

    picked = base + picked
    json.dump(picked, open(OUTDIR / "candidates.json", "w"), ensure_ascii=False, indent=1)
    print("\n已写 %s (%d 个，含 %d 个基准)" % (OUTDIR / "candidates.json", len(picked), len(base)))


if __name__ == "__main__":
    main()
