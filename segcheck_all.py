# -*- coding: utf-8 -*-
"""批量逐段音色检测（需求 3）：全库跑 ch123_segcheck.check()，落盘 json，支持断点续跑。

用法（必须用带 kaldi_native_fbank 的解释器）：
  PY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
  "$PY" segcheck_all.py --dir _audio_ch123/out --out _segcheck_all.json
  "$PY" segcheck_all.py --dir _audio_ch123/out --out _segcheck_all.json --limit 20   # 试跑

判据（照 ch123_segcheck.py 原有阈值，不新造）：
  段与其余段平均相似度 < 0.55 → 偏离；< 0.45 → 严重偏离
  F0 跨度 > 40Hz → 音高跳；相邻段电平差 > 6dB → 电平跳
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_segcheck as SC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="_audio_ch123/out")
    ap.add_argument("--out", default="_segcheck_all.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-single", action="store_true", default=True,
                    help="单段文件（无法段间互比）记为 n=1 跳过")
    a = ap.parse_args()
    os.environ.setdefault("SEGCHK_DIR", "D:/_segchk_tmp")
    os.makedirs(os.environ["SEGCHK_DIR"], exist_ok=True)

    files = sorted(glob.glob(os.path.join(a.dir, "*.wav")))
    if a.limit:
        files = files[:a.limit]

    done = {}
    if os.path.exists(a.out):
        try:
            for r in json.load(open(a.out, encoding="utf-8")):
                done[r["id"]] = r
        except Exception:
            done = {}
    todo = [f for f in files if os.path.splitext(os.path.basename(f))[0] not in done]
    print("总计 %d，已完成 %d，本轮待跑 %d" % (len(files), len(done), len(todo)), flush=True)

    t0 = time.time()
    for k, f in enumerate(todo, 1):
        fid = os.path.splitext(os.path.basename(f))[0]
        rec = {"id": fid, "path": f}
        try:
            r = SC.check(f, verbose=False)
            if r is None:
                rec.update({"n": 1, "min_sim": None, "verdict": "SINGLE",
                            "note": "只有 1 段，无法段间互比"})
            else:
                mn = float(min(r["rows"]))
                rec.update({
                    "n": r["n"],
                    "min_sim": round(mn, 4),
                    "worst_seg": r["worst"],
                    "worst_t0": round(r["info"][r["worst"]]["t0"], 3),
                    "worst_t1": round(r["info"][r["worst"]]["t1"], 3),
                    "f0_span": round(r["f0_span"], 1),
                    "lvl_max": round(r["lvl_max"], 1),
                    "rows": [round(x, 4) for x in r["rows"]],
                    "segs": [{"i": x["i"], "t0": round(x["t0"], 3), "t1": round(x["t1"], 3),
                              "dur": round(x["dur"], 3), "f0": round(x["f0"], 1),
                              "db": round(x["db"], 1)} for x in r["info"]],
                })
                flags = []
                if mn < 0.45:
                    flags.append("SEVERE")
                elif mn < 0.55:
                    flags.append("OFF")
                if r["f0_span"] > 40:
                    flags.append("F0JUMP")
                if r["lvl_max"] > 6:
                    flags.append("LVLJUMP")
                rec["verdict"] = "|".join(flags) if flags else "OK"
        except Exception as e:
            rec.update({"verdict": "ERR", "note": str(e)[:200]})
        done[fid] = rec
        # 临时切段文件不在此删除：批量删除会被安全策略拦截并杀掉进程（2026-11-11 实测）
        # 统一写到 SEGCHK_DIR（默认 D:/_segchk_tmp），跑完由人工清理
        if k % 20 == 0 or k == len(todo):
            el = time.time() - t0
            eta = el / k * (len(todo) - k)
            print("  %d/%d  %.1fs  单条 %.2fs  ETA %.0fmin" % (
                k, len(todo), el, el / k, eta / 60), flush=True)
            with open(a.out, "w", encoding="utf-8") as fh:
                json.dump(list(done.values()), fh, ensure_ascii=False)

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(list(done.values()), fh, ensure_ascii=False)

    allr = list(done.values())
    from collections import Counter
    c = Counter(r["verdict"] for r in allr)
    print("\n=== 结果 %d 条 ===" % len(allr))
    for k, v in c.most_common():
        print("  %-22s %d" % (k, v))
    sims = [r["min_sim"] for r in allr if r.get("min_sim") is not None]
    if sims:
        sims.sort()
        import statistics
        print("最低段间相似度: min %.3f  p05 %.3f  p25 %.3f  med %.3f" % (
            sims[0], sims[int(len(sims) * .05)], sims[len(sims) // 4], statistics.median(sims)))
    print("落盘 %s" % a.out)


if __name__ == "__main__":
    main()
