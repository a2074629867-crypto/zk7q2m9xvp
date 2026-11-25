# -*- coding: utf-8 -*-
"""P0-6：全库词内 F0 覆盖率（判据 3.4）—— 两版同尺子。

cover(w) = 词 span 内「既有声又可跟踪」帧数 ÷ 词 span 内有声帧数
命中：cover < 0.20 → SUSPECT

防呆（照 PROSODY_ACTION §5.3b）：
  · 分母只算有声帧（阈值 p90−20dB，不低于 −60），否则停顿多的句子全被冤枉
  · fmin=50（男声旁白中位 72–75Hz，60 会贴边）
  · 短词（<0.12s 或有声帧 <3）不出结论，标 n/a，不许当 0

用法：
  python _f0cover.py --ver old --dir _audio_ch123/out --feat _accent_feat_old.jsonl --out _f0cover_old.json
  python _f0cover.py --ver new --dir _regen_final      --feat _accent_feat_new.jsonl --out _f0cover_new.json
"""
import argparse
import io
import json
import os
import time

import librosa
import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
SR16 = 16000
HOP = 160          # 10ms
FL = 0.02          # 20ms 帧
COVER_MIN = 0.20
MIN_DUR = 0.12
MIN_VF = 3


def load16(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    return librosa.resample(y, orig_sr=sr, target_sr=SR16)


def voiced(y):
    n = int(FL * SR16)
    k = 1 + (len(y) - n) // HOP if len(y) > n else 1
    idx = np.arange(n)[None, :] + HOP * np.arange(k)[:, None]
    seg = y[idx].astype(np.float64)
    db = 20 * np.log10(np.sqrt((seg ** 2).mean(1)) + 1e-12)
    thr = max(-60.0, float(np.percentile(db, 90)) - 20.0)
    return db > thr, thr


def one(wav, words):
    y = load16(wav)
    vm, thr = voiced(y)
    f0, vf, _ = librosa.pyin(y, fmin=50, fmax=400, sr=SR16,
                            frame_length=1024, hop_length=HOP)
    ok = vf & np.isfinite(f0)
    n = min(len(vm), len(ok))
    vm, ok, f0 = vm[:n], ok[:n], f0[:n]

    rows, sus = [], []
    for w in words:
        a = int(round(w["t0"] * SR16 / HOP))
        b = int(round(w["t1"] * SR16 / HOP))
        a, b = max(0, a), min(n, b)
        if b - a < 2:
            rows.append(dict(w=w["w"], pos=w.get("pos"), t0=w["t0"], cover=None,
                             note="n/a 太短"))
            continue
        v = vm[a:b]
        nv = int(v.sum())
        if nv < MIN_VF:
            rows.append(dict(w=w["w"], pos=w.get("pos"), t0=w["t0"], cover=None,
                             note="n/a 有声帧不足"))
            continue
        c = float((ok[a:b] & v).sum()) / nv
        rows.append(dict(w=w["w"], pos=w.get("pos"), t0=w["t0"],
                         cover=round(c, 3), nv=nv))
        if c < COVER_MIN:
            sus.append(dict(w=w["w"], pos=w.get("pos"), cover=round(c, 3)))

    good = [r["cover"] for r in rows if r["cover"] is not None]
    return dict(thr=round(thr, 1),
                frame_cover=round(float((ok & vm).sum()) / max(1, int(vm.sum())), 3),
                n_word=len(rows), n_judged=len(good),
                med=round(float(np.median(good)), 3) if good else None,
                sus=sus, words=rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--feat", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    d = a.dir if os.path.isabs(a.dir) else os.path.join(ROOT, a.dir)
    fp = a.feat if os.path.isabs(a.feat) else os.path.join(ROOT, a.feat)

    recs = [json.loads(l) for l in io.open(fp, encoding="utf-8") if l.strip()]
    if a.limit:
        recs = recs[:a.limit]
    print("[%s] %d 句 → %s" % (a.ver, len(recs), a.out), flush=True)

    out, t0 = {}, time.time()
    for i, r in enumerate(recs, 1):
        wav = os.path.join(d, r["id"] + ".wav")
        if not os.path.exists(wav):
            out[r["id"]] = dict(note="缺音频")
            continue
        try:
            out[r["id"]] = one(wav, r["words"])
        except Exception as e:  # noqa: BLE001
            out[r["id"]] = dict(note="异常 %s" % type(e).__name__)
        if i % 50 == 0 or i == 1:
            el = time.time() - t0
            print("  %4d/%d  %.1fs  ETA %.0f min"
                  % (i, len(recs), el, (len(recs) - i) * el / i / 60), flush=True)

    json.dump(out, io.open(os.path.join(ROOT, a.out), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    ok = [v for v in out.values() if v.get("med") is not None]
    meds = [v["med"] for v in ok]
    nsus = sum(len(v.get("sus") or []) for v in ok)
    njud = sum(v["n_judged"] for v in ok)
    print()
    print("[%s] 完成 %d 句（可判 %d）" % (a.ver, len(out), len(ok)))
    if meds:
        print("  句级中位覆盖 p10/p50/p90 = %.2f / %.2f / %.2f"
              % tuple(np.percentile(meds, [10, 50, 90])))
    print("  SUSPECT 词 %d / 可判词 %d = %.1f%%"
          % (nsus, njud, 100.0 * nsus / max(1, njud)))


if __name__ == "__main__":
    main()
