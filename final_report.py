"""合并体检表：情绪到位度（VAD 判据）+ 音色归属（1-NN Z-norm）。

输入：
  emo_bench/out/final_judge.json   情绪到位度（verdict 侧）
  out_sv/final_eval.json           音色归属（声纹侧）
输出：
  out_sv/final_report.json / .csv / 控制台摘要
"""
import json, os, collections

J = "G:/_setup/emo_bench/out/final_judge.json"
S = "G:/_setup/out_sv/final_eval.json"
OUT = "G:/_setup/out_sv/final_report"


def main():
    judge = {d["wid"]: d for d in json.load(open(J, encoding="utf-8"))}
    sv = {d["name"].replace(".wav", ""): d for d in json.load(open(S, encoding="utf-8"))}

    ids = sorted(set(judge) & set(sv))
    rows = []
    for i in ids:
        j, s = judge[i], sv[i]
        # 两项都过 = 可用；任一不过 = 需处理
        emo_ok = j["tier"] in ("到位", "勉强")
        voice_ok = s["ok"]
        if not voice_ok:
            verdict = "串人"          # 音色都不对，先修这个
        elif not emo_ok:
            verdict = "情绪不到位"     # 人是这个人，但情绪没演出来
        elif not s["conf"]:
            verdict = "通过(低置信)"   # 结论成立，但建议抽检
        else:
            verdict = "通过"
        rows.append({
            "id": i, "who": j.get("who"), "target": j.get("emo"),
            "emo_pct": round(j.get("pct", 0) * 100, 0), "emo_tier": j.get("tier"),
            "ref_auc": round(j.get("auc", 0), 3),
            "voice_top1": s.get("top1"), "voice_z": s.get("z1"),
            "voice_margin": s.get("margin"), "voice_conf": s.get("conf"),
            "voice_ok": s.get("ok"),
            "verdict": verdict,
            "text": (j.get("text") or "")[:60],
        })

    json.dump(rows, open(OUT + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(OUT + ".csv", "w", encoding="utf-8-sig") as f:
        cols = list(rows[0])
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join('"%s"' % r[c] if isinstance(r[c], str) else str(r[c]) for c in cols) + "\n")

    print("=== 总计 %d 条 ===" % len(rows))
    for k, v in collections.Counter(r["verdict"] for r in rows).most_common():
        print("  %-10s %3d  (%.0f%%)" % (k, v, 100 * v / len(rows)))
    print()
    print("=== 按目标情绪 ===")
    for tgt in ("平静", "委屈", "兴奋", "警惕"):
        sub = [r for r in rows if r["target"] == tgt]
        if not sub:
            continue
        c = collections.Counter(r["verdict"] for r in sub)
        print("  %-4s n=%-3d %s" % (tgt, len(sub), dict(c)))
    print()
    print("=== 需要处理的清单 ===")
    bad = [r for r in rows if r["verdict"] != "通过"]
    print("  %-6s %-7s %-5s %-16s %6s %-10s %s" % ("id", "真角色", "目标", "音色判定", "z", "情绪", "问题"))
    for r in bad:
        print("  %-6s %-7s %-5s %-16s %6.2f %-10s %s" %
              (r["id"], "C" if r["who"] == "C" else "E", r["target"],
               r["voice_top1"], r["voice_z"], r["emo_tier"], r["verdict"]))
    print()
    print("写 -> %s.json / .csv" % OUT)


if __name__ == "__main__":
    main()
