# -*- coding: utf-8 -*-
"""Stage A：逐词产出「音高突出度 + 依存句法角色」，供 Stage B 套规则。

突出度口径（改过一版，记一下为什么）：
  prom = 该词 F0 的 **p50**（半音,rel 100Hz） − 全句 F0 中位（半音）
  · 原打算用 p95 当「词内峰」，实测被单帧八度跳毁掉：c1_0001 的 "Three" p95=+18.7st
    （p50 只有 −0.7st）⇒ p95 只取第 2 高的帧，一个毛刺就爆。改用 p50。
  · p90 仍存着做参考，但不进判决。

数据可信度门槛（`_check_wl.py` 实测得出）：
  · 旧词表 `_wl_words.json` 有 93/952 条词数与时长对不上（最高 1071wpm）
    ⇒ 只保留 wpm≤260 且末词结束 ≤ 音频时长×1.02 的条目
  · 新词表 `_wl_regen1123.json` 714 条，最高 321wpm，只有 11 条超 260

用法：
  G:/Python310/python.exe -u _accent_feat.py --dir _audio_ch123/out --wl _wl_words.json --out _accent_feat_old.jsonl
  G:/Python310/python.exe -u _accent_feat.py --dir _regen_final     --wl _wl_regen1123.json --out _accent_feat_new.jsonl
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

ROOT = r"G:/_setup"
sys.path.insert(0, ROOT)

import parselmouth  # noqa: E402
import spacy  # noqa: E402

NLP = None
ABBR = re.compile(r"\b(mr|mrs|ms|dr|st|jr|sr|prof|rev)\s+\.", re.I)


def get_nlp():
    global NLP
    if NLP is None:
        NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    return NLP


def to_text(words):
    s = " ".join(w["w"] for w in words)
    s = ABBR.sub(lambda m: m.group(1).capitalize() + ".", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[0].upper() + s[1:]) if s else s


def semis(f):
    return 12.0 * np.log2(f / 100.0)


def f0_track(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    s = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr)
    p = s.to_pitch_ac(time_step=0.01, pitch_floor=60.0, pitch_ceiling=500.0)
    n = p.get_number_of_frames()
    ts = np.array([p.get_time_from_frame_number(i + 1) for i in range(n)])
    fs = np.array([p.get_value_in_frame(i + 1) for i in range(n)], dtype=float)
    ok = np.isfinite(fs) & (fs > 0)
    return ts[ok], fs[ok], len(y) / float(sr)


def align(words, doc):
    out, ti = [], 0
    for w in words:
        key = re.sub(r"[^a-z']", "", w["w"].lower())
        if not key:
            out.append((w, None))
            continue
        found = None
        for j in range(ti, min(ti + 4, len(doc))):
            if re.sub(r"[^a-z']", "", doc[j].text.lower()) == key:
                found = j
                break
        if found is None:
            out.append((w, None))
        else:
            out.append((w, doc[found]))
            ti = found + 1
    return out


def n_words(words):
    return len([w for w in words if any(c.isalpha() for c in w["w"])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--wl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", default="_narr_blocks.json")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    wl = json.load(open(os.path.join(ROOT, a.wl), encoding="utf-8"))
    wl = {os.path.basename(k).rsplit(".", 1)[0]: v for k, v in wl.items()}

    want = None
    if a.ids:
        b = json.load(open(os.path.join(ROOT, a.ids), encoding="utf-8"))
        want = set()
        for blk in b:
            want.update(blk["ids"])
    ids = sorted(want & set(wl.keys())) if want else sorted(wl.keys())
    if a.limit:
        ids = ids[: a.limit]

    outp = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    done = set()
    if os.path.exists(outp):
        for ln in open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(ln)["id"])
            except Exception:  # noqa: BLE001
                pass
    print("目标 %d 条，已完成 %d 条" % (len(ids), len(done)), flush=True)

    nlp = get_nlp()
    fh = open(outp, "a", encoding="utf-8")
    nerr = nskip = 0
    for i, sid in enumerate(ids):
        if sid in done:
            continue
        path = os.path.join(ROOT, a.dir, sid + ".wav")
        if not os.path.exists(path):
            nerr += 1
            continue
        try:
            words = wl[sid].get("words") or []
            info = sf.info(path)
            nw = n_words(words)
            if not nw or nw / info.duration * 60.0 > 260 or \
                    float(words[-1]["end"]) > info.duration * 1.02:
                nskip += 1
                continue
            ts, fs, dur = f0_track(path)
            if len(fs) < 10:
                nerr += 1
                continue
            fst = semis(fs)
            med = float(np.median(fst))
            doc = nlp(to_text(words))
            rows = []
            for w, tok in align(words, doc):
                t0, t1 = float(w["start"]), float(w["end"])
                sel = (ts >= t0) & (ts < t1)
                if sel.sum() >= 4:
                    v = fst[sel]
                    p50 = float(np.median(v))
                    p90 = float(np.percentile(v, 90))
                    pmin = float(v.min())
                    pmax = float(v.max())
                    nfr = int(sel.sum())
                else:
                    p50 = p90 = pmin = pmax = None
                    nfr = int(sel.sum())
                rows.append(dict(
                    w=w["w"], t0=round(t0, 3), t1=round(t1, 3), nfr=nfr,
                    pos=(tok.pos_ if tok else None),
                    dep=(tok.dep_ if tok else None),
                    head=(tok.head.text if tok and tok.head is not tok else None),
                    hi=(tok.head.i if tok else None),
                    i=(tok.i if tok else None),
                    p50=None if p50 is None else round(p50, 2),
                    p90=None if p90 is None else round(p90, 2),
                    lo=None if pmin is None else round(pmin, 2),
                    hi_f0=None if pmax is None else round(pmax, 2),
                ))
            fh.write(json.dumps(dict(id=sid, dir=a.dir, text=to_text(words),
                                     dur=round(dur, 3), med=round(med, 2),
                                     nw=len(rows), words=rows), ensure_ascii=False) + "\n")
            fh.flush()
        except Exception as e:  # noqa: BLE001
            nerr += 1
            print("ERR %s %r" % (sid, e), flush=True)
        if (i + 1) % 50 == 0:
            print("... %d/%d  err %d  skip %d" % (i + 1, len(ids), nerr, nskip), flush=True)
    fh.close()
    print("完成：err %d / 词表不可信跳过 %d" % (nerr, nskip), flush=True)


if __name__ == "__main__":
    main()
