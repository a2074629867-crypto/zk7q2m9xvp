# -*- coding: utf-8 -*-
"""测 pitch/rate 的「词级兑现」：目标词 F0 半音偏移 + 词时长 + 内容完整性。

用法：
    python _measure_perf.py MP_ P_w_neg,P_w_pos,P_whole,P_mix hair,cosmos

基线用 MKT_L_plain.wav（无标签）。F0 用 parselmouth，窗内取中位；
半音差 = 12*log2(f/f0_base)。
"""
import os
import re
import sys
import wave

import numpy as np
import onnxruntime as ort
import onnx_asr
import parselmouth

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

D = "G:/_setup/dots_edit2/"
BASE = D + "MKT_L_plain.wav"
REF_TXT = D + "L_plain.txt"


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, nf = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def r16(a, sr):
    if sr == 16000:
        return a
    n = int(round(len(a) * 16000 / sr))
    return np.interp(np.linspace(0, len(a) - 1, n),
                     np.arange(len(a), dtype=np.float64), a).astype(np.float32)


def norm(t):
    t = t.lower()
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return " ".join(t.split())


def wc(t):
    return len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", t))


def f0_median(path, t0, t1):
    """窗内 F0 中位（Hz），窗太短或全清音返回 None。"""
    snd = parselmouth.Sound(path)
    pit = snd.to_pitch(pitch_floor=60.0, pitch_ceiling=500.0, time_step=0.01)
    vals = pit.selected_array["frequency"]
    times = pit.xs()
    m = (times >= t0) & (times <= t1) & (vals > 0)
    if m.sum() < 3:
        return None
    return float(np.median(vals[m]))


def words_of(model, path):
    a, sr = rd(path)
    out = model.recognize(r16(a, sr))
    toks = getattr(out, "tokens", None) or []
    ts = getattr(out, "timestamps", None) or []
    ws = []
    cur, t0, t1 = "", None, None
    for tk, tt in zip(toks, ts):
        s = str(tk)
        if s.startswith(" "):
            if cur:
                ws.append((cur, t0, t1))
            cur, t0, t1 = s.strip(), tt, tt
        else:
            cur += s
            t1 = tt
    if cur:
        ws.append((cur, t0, t1))
    txt = "".join(str(t) for t in toks)
    return a, sr, ws, txt


def find_word(ws, target):
    for w, t0, t1 in ws:
        if w.lower().strip(".,;:!?") == target:
            return t0, t1
    return None


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "MP_"
    variants = (sys.argv[2] if len(sys.argv) > 2 else "").split(",")
    targets = (sys.argv[3] if len(sys.argv) > 3 else "hair").split(",")
    targets = [t for t in targets if t]

    so = ort.SessionOptions()
    so.log_severity_level = 3
    model = onnx_asr.load_model(
        "nemo-parakeet-tdt-0.6b-v3", "G:/_setup/models/parakeet-v3-int8",
        quantization="int8", providers=[("CPUExecutionProvider", {})],
        sess_options=so).with_timestamps()

    ref = open(REF_TXT, encoding="utf-8").read().strip()
    rw = wc(ref)

    # 基线：目标词的 F0 与时长
    ba, bsr, bws, btxt = words_of(model, BASE)
    bdur = len(ba) / bsr
    base = {}
    for t in targets:
        pos = find_word(bws, t)
        if pos:
            f = f0_median(BASE, pos[0], pos[1])
            base[t] = dict(f0=f, dur=pos[1] - pos[0])
    print("基线 %s  %.2fs | ASR %d 词" % (os.path.basename(BASE), bdur, wc(btxt)))
    for t, v in base.items():
        print("   %-8s F0 %s Hz | 词长 %.2fs"
              % (t, ("%.1f" % v["f0"]) if v["f0"] else "-", v["dur"]))
    print()

    rows = []
    for v in variants:
        p = D + prefix + v + ".wav"
        if not os.path.exists(p):
            print("MISSING", p)
            continue
        a, sr, ws, txt = words_of(model, p)
        dur = len(a) / sr
        hw = wc(txt)
        line = dict(variant=v, dur=dur, words=hw, ref=rw)
        for t in targets:
            pos = find_word(ws, t)
            if not pos:
                line[t] = None
                continue
            f = f0_median(p, pos[0], pos[1])
            d = pos[1] - pos[0]
            st = (12 * np.log2(f / base[t]["f0"])
                  if (f and base[t]["f0"]) else None)
            line[t] = dict(f0=f, dur=d, semi=st,
                           dr=d / base[t]["dur"] if base[t]["dur"] else None)
        rows.append(line)

    print("%-10s %7s %6s  %s" % ("变体", "总长", "词数", "目标词"))
    for r in rows:
        extra = []
        for t in targets:
            d = r.get(t)
            if not d:
                extra.append("%s: 未找到" % t)
                continue
            semi = ("%+.1f半音" % d["semi"]) if d["semi"] is not None else "半音-"
            extra.append("%s: %s F0 %.1fHz 词长 %.2fs(%+.0f%%)"
                         % (t, semi, d["f0"] or 0, d["dur"],
                            100 * ((d["dr"] or 1) - 1)))
        print("%-10s %6.2fs %3d/%-3d %s"
              % (r["variant"], r["dur"], r["words"], r["ref"], " | ".join(extra)))


if __name__ == "__main__":
    main()
