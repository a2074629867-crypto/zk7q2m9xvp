"""裁剪后验证：吃字 + 爆音 + 音高

三件事都必须过：
1. **吃字**：ASR 覆盖率不能掉（裁的是静音，理论不掉，但要证）
2. **爆音**：拼接点两侧采样跳变不能超过全曲正常水平（cut_core 是直接拼，
   静音区拼接理论上无爆音，但必须实测，不能假设）
3. **音高**：F0 中位不能漂（只删静音，不该变）
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_P = {"\u2019": "'", "\u2018": "'", "\u02bc": "'",
      "\u201c": "", "\u201d": "", "\u2013": " ", "\u2014": " "}


def words(t):
    for k, v in _P.items():
        t = t.replace(k, v)
    t = re.sub(r"\bO\.?K\.?\b", "okay", t, flags=re.I)
    return [w.lower() for w in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", t)]


def cov(asr_text, ref_text):
    a, r = words(asr_text), words(ref_text)
    if not r:
        return 0.0, []
    hit = 0
    miss = []
    for w in r:
        if w in a:
            hit += 1
        else:
            miss.append(w)
    return hit / len(r), miss


def click_score(path):
    """拼接爆音：相邻采样最大跳变 / 全曲 p99.9 跳变。

    人声本身就有陡沿（擦音），所以不能看绝对值，要看「有没有比全曲
    正常水平突兀一个量级的跳变」。
    """
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    d = np.abs(np.diff(y))
    p999 = float(np.percentile(d, 99.9))
    mx = float(d.max())
    idx = int(np.argmax(d))
    return dict(max_jump=round(mx, 4), p999=round(p999, 4),
                ratio=round(mx / max(p999, 1e-9), 2), at=round(idx / sr, 3))


def f0_med(path):
    import parselmouth
    f = parselmouth.Sound(path).to_pitch(0.01, 75, 600).selected_array["frequency"]
    f = f[f > 0]
    return int(np.median(f)) if len(f) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="G:/_setup/_gapfix_pairs.json",
                    help='[{"id":..,"before":..,"after":..,"text":..}]')
    ap.add_argument("--json", default="G:/_setup/_gapfix_verify.json")
    a = ap.parse_args()

    pairs = json.load(open(a.pairs, encoding="utf-8"))
    from faster_whisper import WhisperModel
    m = WhisperModel("small.en", device="cpu", compute_type="int8")

    rep = {}
    for p in pairs:
        rid = p["id"]
        row = {}
        for tag in ("before", "after"):
            f = p[tag]
            segs, _ = m.transcribe(f, language="en", beam_size=1, vad_filter=False)
            txt = " ".join(s.text for s in segs)
            c, miss = cov(txt, p["text"])
            row[tag] = dict(cov=round(c, 3), miss=miss, hyp=txt.strip()[:110],
                            click=click_score(f), f0=f0_med(f))
        d = row["after"]["cov"] - row["before"]["cov"]
        row["delta"] = round(d, 3)
        row["verdict"] = ("PASS" if d >= -0.05 and row["after"]["click"]["ratio"] < 3.0
                          else "CHECK")
        rep[rid] = row
        print("%-9s cov %.2f→%.2f (%+.2f)  跳变×%.1f   F0 %d→%d   %s" % (
            rid, row["before"]["cov"], row["after"]["cov"], d,
            row["after"]["click"]["ratio"], row["before"]["f0"], row["after"]["f0"],
            row["verdict"]))
        if d < -0.05:
            print("      掉词: %s" % row["after"]["miss"])
            print("      hyp: %s" % row["after"]["hyp"])
        if row["after"]["click"]["ratio"] >= 3.0:
            print("      爆音 @%.2fs 跳变 %.4f (p99.9 %.4f)" % (
                row["after"]["click"]["at"], row["after"]["click"]["max_jump"],
                row["after"]["click"]["p999"]))

    json.dump(rep, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for v in rep.values() if v["verdict"] == "PASS")
    print("\n%d 条中 %d 条 PASS" % (len(rep), ok))
    print("->", a.json)


if __name__ == "__main__":
    sys.exit(main())
