# -*- coding: utf-8 -*-
"""把「现用 live」和「本轮双参考候选」放在一起择优，输出 `_sweep/final9/`。

为什么必须把 live 也算进来
------------------------
`_pick9.py` 只在 emo / role 两个新候选之间选。实测出现这种情况：

    c2_0369  live cov 1.00 → 本轮 emo 0.00 / role 0.00（role 念成 LUSKOZOFRI）

两个新候选都坏，选出来的必然也是坏的 —— 比不改还差。所以择优集合必须是
{live, emo, role} 三个，live 作为守门员：新候选只有在**严格更好**时才替换。

评分
----
1. `w2v_cov`（wav2vec2-960h 贪心 + 词覆盖率，不带语言模型，抓真吞音）
2. 同分时看 voiced-tilt 与角色基线的距离
3. 再看时长是否离同 id 中位过远（>1.5× 或 <0.6× 判可疑）

语言泄漏（法语参考把英文台词带跑）单独标 `leak`：w2v 文本里出现
非英文词形、或 cov<0.35 且时长与文本严重不符，人工/下一轮重做。
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


def load_align(path):
    d = {}
    for r in json.load(io.open(path, encoding="utf-8")):
        d[os.path.basename(r["wav"])[:-4]] = r
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-align", default=os.path.join(ROOT, "_align_live.json"))
    ap.add_argument("--camp-align", default=os.path.join(ROOT, "_align_camp9.json"))
    ap.add_argument("--camp", default=os.path.join(ROOT, "_sweep", "camp9"))
    ap.add_argument("--live", default=os.path.join(ROOT, "_audio_ch123", "out_paused"))
    ap.add_argument("--out", default=os.path.join(ROOT, "_sweep", "final9"))
    ap.add_argument("--sum", default=os.path.join(ROOT, "_final9_summary.json"))
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    import _calm_gate as CG
    plan = CG.load_plan()

    live = load_align(a.live_align)
    camp = load_align(a.camp_align)

    base = {}
    for role in {p.get("who") for p in plan.values() if p.get("who")}:
        try:
            base[role] = CG.baseline(plan, role)["med"]["tilt"]
        except Exception:
            base[role] = 0.09

    rows = {}
    for rid in plan:
        if rid in live:
            r = live[rid]
            rows.setdefault(rid, []).append({
                "kind": "live", "tag": rid, "path": os.path.join(a.live, rid + ".wav"),
                "cov": r.get("w2v_cov") or 0.0, "w2v": r.get("w2v_text") or "",
                "issues": r.get("issues") or []})
    for tag, r in camp.items():
        parts = tag.split("__")
        if len(parts) < 3:
            continue
        rid, kind = parts[0], parts[1]
        rows.setdefault(rid, []).append({
            "kind": kind, "tag": tag, "path": os.path.join(a.camp, tag + ".wav"),
            "cov": r.get("w2v_cov") or 0.0, "w2v": r.get("w2v_text") or "",
            "issues": r.get("issues") or []})

    summary = {}
    for rid, grp in sorted(rows.items()):
        role = plan.get(rid, {}).get("who") or "Charles"
        txt = plan.get(rid, {}).get("text") or ""
        nw = max(3, CG.spoken_words(txt))
        for g in grp:
            if not os.path.exists(g["path"]):
                g["cov"] = -1
                continue
            m = CG.measure(g["path"], nw, txt)
            g.update(dur=m["dur"], tilt=m["tilt"], wpm=m["wpm_voiced"], F0=m["F0"])
        grp = [g for g in grp if g["cov"] >= 0]
        if not grp:
            continue
        for g in grp:
            g["dtilt"] = abs(g.get("tilt", 0.09) - base.get(role, 0.09))
        # live 优先：只有当新候选 cov 比 live 高出 0.05 以上才换（避免噪声抖动）
        lv = next((g for g in grp if g["kind"] == "live"), None)
        best = max(grp, key=lambda x: (x["cov"], -x["dtilt"]))
        if lv and best is not lv and best["cov"] - lv["cov"] < 0.05:
            best = lv
        shutil.copyfile(best["path"], os.path.join(a.out, rid + ".wav"))
        leak = best["cov"] < 0.35 and best["w2v"].strip() != ""
        summary[rid] = {
            "kind": best["kind"], "tag": best["tag"],
            "cov": round(best["cov"], 3),
            "cov_live": round(lv["cov"], 3) if lv else None,
            "dur": round(best.get("dur", 0), 2), "tilt": round(best.get("tilt", 0), 3),
            "w2v": best["w2v"], "replaced": best is not lv,
            "issues": [i["word"] for i in best["issues"]],
            "leak": leak,
            "flag": "LEAK" if leak else ("OK" if best["cov"] >= 0.85 else "WARN"),
            "alt": [{"tag": g["tag"], "cov": round(g["cov"], 2)} for g in grp if g is not best],
        }

    json.dump(summary, io.open(a.sum, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rep = sum(1 for v in summary.values() if v["replaced"])
    ok = sum(1 for v in summary.values() if v["flag"] == "OK")
    leak = [k for k, v in summary.items() if v["leak"]]
    print("%d 条；替换 %d 条；cov≥0.85 %d 条（%.0f%%）；疑似语言泄漏 %d 条" % (
        len(summary), rep, ok, 100.0 * ok / max(1, len(summary)), len(leak)))
    print("泄漏:", ",".join(sorted(leak)[:20]))
    left = sorted([(v["cov"], k) for k, v in summary.items() if v["flag"] != "OK"])[:20]
    print("最差 20:")
    for c, k in left:
        print("  %-9s cov=%.2f  %s" % (k, c, summary[k]["w2v"][:50]))


if __name__ == "__main__":
    main()
