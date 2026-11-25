"""词尾塞音（/t/ 等）释放爆破的量化

背景：用户听 `c3_0853` 说 seed46 的 "can't" 读成 "cam"（/t/ 没了）。
ASR 两版都转成 can't，靠 ASR 分不出来，只能看声学：

    爆破 = 极短（10~30ms）的高频宽带瞬态

所以看两件事：
1. **高频占比跃升**：词尾 40ms 的 3.5k+ 能量占比 vs 词腹（元音主体）
2. **谱重心跃升**：词尾谱重心 vs 词腹谱重心

两者都上升 ⇒ 有释放；基本不变 ⇒ /t/ 被吞（成鼻音 /m/ 或直接省略）。
"""
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")


def frames(y, sr, a, b, win_ms=10.0):
    n = int(win_ms / 1000.0 * sr)
    if n < 16:
        n = 16
    i0, i1 = int(a * sr), int(b * sr)
    seg = y[i0:i1]
    c = len(seg) // n
    if c < 2:
        return None
    out = []
    w = np.hanning(n)
    for i in range(c):
        f = seg[i * n:(i + 1) * n]
        sp = np.abs(np.fft.rfft(f * w))
        fr = np.fft.rfftfreq(n, 1.0 / sr)
        e = float((sp ** 2).sum()) + 1e-12
        hf = float((sp[fr >= 3500] ** 2).sum()) / e
        cen = float((sp * fr).sum() / (sp.sum() + 1e-12))
        db = 10 * np.log10(e + 1e-12)
        out.append((db, hf, cen))
    return out


def burst(path, a, b, tail_ms=40.0, body_pad_ms=30.0):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    fr = frames(y, sr, a, b)
    if not fr:
        return None
    step = 10.0
    ntail = max(2, int(tail_ms / step))
    nbody_start = max(1, int(body_pad_ms / step))
    tail = fr[-ntail:]
    body = fr[nbody_start:max(nbody_start + 2, len(fr) - ntail)]
    if not body:
        body = fr[:max(1, len(fr) // 2)]
    ht = float(np.mean([x[1] for x in tail]))
    hb = float(np.mean([x[1] for x in body]))
    ct = float(np.mean([x[2] for x in tail]))
    cb = float(np.mean([x[2] for x in body]))
    # 包络：词尾有没有「先静后爆」（闭合+释放）
    dbs = [x[0] for x in fr]
    peak = max(dbs)
    dip = min(dbs[-ntail:]) if len(dbs) >= ntail else peak
    return dict(dur=round((b - a) * 1000),
                hf_tail=round(ht, 3), hf_body=round(hb, 3),
                hf_jump=round(ht / max(hb, 1e-6), 2),
                cen_tail=round(ct), cen_body=round(cb),
                cen_jump=round(ct / max(cb, 1e-6), 2),
                closure_db=round(peak - dip, 1))


if __name__ == "__main__":
    import json

    import _align_gate as AG
    import _pause_gap as PG

    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
    rid = sys.argv[1] if len(sys.argv) > 1 else "c3_0853"
    word = sys.argv[2] if len(sys.argv) > 2 else "cant"
    text = PG.clean(rows[rid]["text"])
    proc, model = AG.load_model()
    print("%-28s %5s %6s %6s %6s %5s %5s %s" % (
        "file", "ms", "hfT", "hfB", "hfJump", "cenT", "cenB", "closure"))
    import glob
    import os
    cands = [("now", "G:/_setup/_audio_ch123/out/%s.wav" % rid)]
    for p in sorted(glob.glob("G:/_setup/_seedpick/%s/s*.wav" % rid)):
        cands.append((os.path.basename(p)[:-4], p))
    base = "G:/_setup/_seedpick2/%s" % rid
    for p in sorted(glob.glob(base + "/s*.wav")):
        cands.append((os.path.basename(p)[:-4], p))
    for tag, p in cands:
        if not os.path.exists(p):
            continue
        sp = PG.align_spans(p, text, proc, model)
        tgt = [x for x in sp if x[0].startswith(word)]
        if not tgt:
            print("%-28s 未找到 %s" % (tag, word))
            continue
        _, a, b = tgt[0]
        r = burst(p, a, b)
        print("%-28s %5d %6.3f %6.3f %6.2f %5d %5d %5.1f" % (
            tag, r["dur"], r["hf_tail"], r["hf_body"], r["hf_jump"],
            r["cen_tail"], r["cen_body"], r["closure_db"]))
