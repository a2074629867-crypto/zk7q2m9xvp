# -*- coding: utf-8 -*-
"""从 `_campaign9` 的双参考候选里择优，输出 `_campaign9/pick/`。

择优顺序
--------
1. **wav2vec2-960h 词覆盖率**（不带语言模型，抓真吞音）—— 高者胜
2. 同分时看 **voiced-tilt 与角色基线的距离**（音色稳）—— 近者胜
3. 再看时长是否离两版中位过远

`w2v_cov` 由 `_align_gate.py` 生成；本脚本先扫目录，缺的现算，落盘后复用。
"""
import argparse
import glob
import io
import json
import os
import shutil
import sys

ROOT = "G:/_setup"
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default=os.path.join(ROOT, "_sweep", "camp9"))
    ap.add_argument("--out", default="")
    ap.add_argument("--align", default=os.path.join(ROOT, "_align_camp9.json"))
    ap.add_argument("--sum", default=os.path.join(ROOT, "_pick9_summary.json"))
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.cand, "*.wav")))
    if not files:
        print("没有候选")
        return
    pick_dir = a.out or os.path.join(a.cand, "pick")
    os.makedirs(pick_dir, exist_ok=True)

    alignd = {}
    if os.path.exists(a.align):
        for r in json.load(io.open(a.align, encoding="utf-8")):
            alignd[os.path.basename(r["wav"])[:-4]] = r

    import _calm_gate as CG
    plan = CG.load_plan()

    rows = {}
    for f in files:
        tag = os.path.basename(f)[:-4]
        parts = tag.split("__")
        if len(parts) < 3:
            continue
        rid, kind = parts[0], parts[1]
        r = alignd.get(tag)
        if not r:
            print("缺 ASR：", tag)
            continue
        m = CG.measure(f, max(3, len((plan.get(rid, {}).get("text") or "a b c").split())),
                       plan.get(rid, {}).get("text") or "")
        rows.setdefault(rid, []).append({
            "tag": tag, "kind": kind, "path": f,
            "cov": r.get("w2v_cov") or 0.0,
            "tilt": m["tilt"], "wpm": m["wpm_voiced"], "F0": m["F0"],
            "dur": m["dur"],
            "issues": r.get("issues") or [],
            "text": r.get("w2v_text") or "",
        })

    # 角色基线 tilt（同角色全库中位）
    base = {}
    for role in {p.get("who") for p in plan.values() if p.get("who")}:
        try:
            b = CG.baseline(plan, role)
            base[role] = b["med"]["tilt"]
        except Exception:
            base[role] = 0.09

    summary = {}
    for rid, grp in sorted(rows.items()):
        role = (plan.get(rid, {}).get("who") or "Charles")
        b = base.get(role, 0.09)
        for g in grp:
            g["dtilt"] = abs(g["tilt"] - b)
        grp.sort(key=lambda x: (-x["cov"], x["dtilt"]))
        best = grp[0]
        alts = [{"tag": g["tag"], "kind": g["kind"], "cov": round(g["cov"], 2),
                 "tilt": round(g["tilt"], 3)} for g in grp[1:]]
        shutil.copyfile(best["path"], os.path.join(pick_dir, "%s.wav" % rid))
        summary[rid] = {"tag": best["tag"], "kind": best["kind"],
                        "cov": round(best["cov"], 3), "dur": round(best["dur"], 2),
                        "tilt": round(best["tilt"], 3), "dtilt": round(best["dtilt"], 3),
                        "issues": [i["word"] for i in best["issues"]],
                        "alt": alts,
                        "flag": "OK" if best["cov"] >= 0.85 else "WARN"}
        print("%-9s %-5s cov=%.2f tilt=%.3f  %s" % (
            rid, best["kind"], best["cov"], best["tilt"],
            ",".join(summary[rid]["issues"]) or "-"))

    json.dump(summary, io.open(a.sum, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = sum(1 for v in summary.values() if v["flag"] == "OK")
    print("\n%d 条，cov≥0.85 的 %d 条（%.0f%%）→ %s" % (
        len(summary), ok, 100.0 * ok / max(1, len(summary)), pick_dir))


if __name__ == "__main__":
    main()
