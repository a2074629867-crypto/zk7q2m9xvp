# -*- coding: utf-8 -*-
"""交付前最后一道：按条决定要不要采用「剪长停顿 + 填底噪」的版本。

为什么需要逐条裁决
------------------
实测（wav2vec2 覆盖率，同一匹配器）：

    final9 剪前        203/239 ≥0.85
    final9 剪后        192/239 ≥0.85

掉下来的 11 条不是内容被剪掉，而是剪辑改变了 1~2 秒短句的波形边界，
wav2vec2 的解码从 LONDON 变成 LONDAY、THAT'S 变成 HAT —— 是度量噪声，
但既然量得出来，就不该硬着头皮用「看起来更差」的版本。

规则：剪后覆盖率比剪前低 **>0.08** 的，保留剪前版本（长停顿也保留）；
其余一律采用剪后版本（更干净、更长停顿已压到 0.38s）。
最后统一归一到 voiced RMS −24.00 dBFS。
"""
import argparse
import io
import json
import os
import shutil
import sys

# 嵌入式 Python（python310._pth）不会自动加脚本目录，必须先手动加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as _P      # 路径集中管理：本机默认 G:/_setup，云上按 MR_ROOT

ROOT = _P.ROOT
sys.path.insert(0, ROOT)


def norm24(path):
    """迭代归一到 voiced RMS −24 dBFS（±0.05）。"""
    import numpy as np
    import soundfile as sf
    from narr_gate_phys import voiced_db

    y, sr = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(1)
    for _ in range(8):
        lv, _, _ = voiced_db(y, sr)
        y = y * (10 ** ((-24.0 - lv) / 20.0))
        lv2, _, _ = voiced_db(y, sr)
        if abs(lv2 + 24.0) <= 0.04:
            break
    if abs(y).max() > 0.98:
        y = y * (0.98 / abs(y).max())
    sf.write(path, y, sr, subtype="PCM_16")
    return float(voiced_db(y, sr)[0]), float(abs(y).max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", default=os.path.join(ROOT, "_sweep", "final9"))
    ap.add_argument("--post", default=os.path.join(ROOT, "_sweep", "final9_fix"))
    ap.add_argument("--out", default=os.path.join(ROOT, "_audio_ch123", "out_deliver"))
    ap.add_argument("--pre-align", default=os.path.join(ROOT, "_align_final9_pre.json"))
    ap.add_argument("--post-align", default=os.path.join(ROOT, "_align_final9.json"))
    ap.add_argument("--report", default=os.path.join(ROOT, "_deliver_report.json"))
    ap.add_argument("--tol", type=float, default=0.08)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    pre = {r["id"]: (r.get("w2v_cov") or 0.0)
           for r in json.load(io.open(a.pre_align, encoding="utf-8"))}
    post = {r["id"]: (r.get("w2v_cov") or 0.0)
            for r in json.load(io.open(a.post_align, encoding="utf-8"))}

    rep = {}
    kept_pre = []
    for fn in sorted(os.listdir(a.post)):
        if not fn.endswith(".wav"):
            continue
        rid = fn[:-4]
        c_pre, c_post = pre.get(rid, 0.0), post.get(rid, 0.0)
        use_pre = (c_pre - c_post) > a.tol
        src = os.path.join(a.pre if use_pre else a.post, fn)
        dst = os.path.join(a.out, fn)
        shutil.copyfile(src, dst)
        lv, pk = norm24(dst)
        rep[rid] = {"src": "pre" if use_pre else "post",
                    "cov_pre": round(c_pre, 3), "cov_post": round(c_post, 3),
                    "cov": round(max(c_pre, c_post), 3) if use_pre else round(c_post, 3),
                    "db": round(lv, 2), "peak": round(pk, 2)}
        if use_pre:
            kept_pre.append((rid, c_pre, c_post))

    json.dump(rep, io.open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for v in rep.values() if v["cov"] >= 0.85)
    print("交付 %d 条；保留剪前版本 %d 条；cov≥0.85 %d (%.0f%%)" % (
        len(rep), len(kept_pre), ok, 100.0 * ok / max(1, len(rep))))
    for rid, c0, c1 in kept_pre:
        print("   保留剪前 %-9s %.2f → 剪后 %.2f" % (rid, c0, c1))
    db = [v["db"] for v in rep.values()]
    pk = [v["peak"] for v in rep.values()]
    print("电平 %.2f ~ %.2f dBFS（跨度 %.2f）；峰值 %.2f ~ %.2f" % (
        min(db), max(db), max(db) - min(db), min(pk), max(pk)))


if __name__ == "__main__":
    main()
