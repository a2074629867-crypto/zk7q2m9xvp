# -*- coding: utf-8 -*-
"""从 48 条实测矩阵里反查：每种情绪应该用哪个音色 + 哪个标签。

不用「pass/fail 数几个」，改成连续拟合度，才能排出名次。
拟合度 = 与真人锚点的归一化距离（跨度、A、V、D、音量），越小越好。

真人锚点（Expresso 745 条，见 analyze_real.py）：
  default  A0.50 V0.54 D0.56  F0 195 跨度138 dBFS-17.8 HNR6.2
  happy    A0.59 V0.56 D0.62  F0 227 跨度153
  sad      A0.32 V0.40 D0.39  F0 199 跨度 84
  laughing A0.68 V0.73 D0.64  F0 233 跨度149
angry / afraid / calm 没有真人锚点（Expresso 只有 8 种 style），
用「构造目标」并在输出里标 *，不可与前三者同权。
"""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# 真人锚点：span / A / V / D
HUMAN = {
    "happy":  dict(span=153, A=0.59, V=0.56, D=0.62),
    "sad":    dict(span=84,  A=0.32, V=0.40, D=0.39),
    "calm":   dict(span=70,  A=0.28, V=0.48, D=0.45),   # * 构造
    "angry":  dict(span=185, A=0.72, V=0.25, D=0.75),   # * 构造
    "afraid": dict(span=120, A=0.62, V=0.28, D=0.45),   # * 构造
}
CONSTRUCTED = {"angry", "afraid", "calm"}

# 归一化尺度：跨度按对数（比值的自然尺度），维度用真人组内 SD
SD_A, SD_V, SD_D = 0.0729, 0.130, 0.10


def load(n):
    p = os.path.join(HERE, "out", n)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def main():
    chk = {(r["ref"], r["emo"] or "base"): r
           for r in json.load(open(os.path.join(HERE, "out", "gen_check.json"),
                                   encoding="utf-8"))}
    gen = {(r["pid"], r["cond"]): r for r in load("gen_index.jsonl")}
    e2v = {r["path"]: r["score"] for r in load("gen_e2v.jsonl") if r.get("score")}
    CN = {"开心/happy": "happy", "难过/sad": "sad", "生气/angry": "angry",
          "中立/neutral": "neutral", "吃惊/surprised": "surprised",
          "恐惧/fearful": "afraid", "厌恶/disgusted": "disgusted",
          "其他/other": "other", "<unk>": "unk", "忧郁/melancholic": "mela",
          "平静/calm": "calm"}
    refs = ["C_normal", "C_soft", "C_excited", "C_angry",
            "E_calm", "E_loud", "E_scold", "E_begging"]
    conds = ["base", "happy", "sad", "angry", "afraid", "calm"]

    for emo, t in HUMAN.items():
        rows = []
        for ref in refs:
            base = chk[(ref, "base")]
            for c in conds:
                r = chk.get((ref, c))
                if not r:
                    continue
                d_span = abs(np.log(max(r["span"], 10) / t["span"]))
                d_A = abs(r["A"] - t["A"]) / SD_A
                d_V = abs(r["V"] - t["V"]) / SD_V
                d_D = abs(r["D"] - t["D"]) / SD_D
                d_db = max(0.0, r["db"] - base["db"] - 6.0) / 3.0   # 超 6dB 才罚
                fit = d_span * 2.0 + d_A + 0.4 * d_V + 0.3 * d_D + d_db
                s = e2v.get(gen[(ref, c)]["path"])
                rows.append((fit, ref, c, r, CN.get(s["_top"], s["_top"]) if s else "-"))
        rows.sort(key=lambda x: x[0])
        star = " *构造目标" if emo in CONSTRUCTED else ""
        print("\n" + "=" * 96)
        print("目标情绪 %s%s   真人锚点：跨度%dHz A%.2f V%.2f D%.2f"
              % (emo, star, t["span"], t["A"], t["V"], t["D"]))
        print("  %-3s %-11s %-7s %-6s %-5s %-6s %-6s %-7s %-6s %-9s"
              % ("#", "ref", "标签", "fit", "跨度", "A", "V", "D", "ΔdB", "e2v"))
        for i, (fit, ref, c, r, e) in enumerate(rows[:5], 1):
            d_db = r["db"] - chk[(ref, "base")]["db"]
            print("  %-3d %-11s %-7s %-6.2f %-5.0f %-6.2f %-6.2f %-7.2f %+-6.1f %-9s"
                  % (i, ref, c, fit, r["span"], r["A"], r["V"], r["D"], d_db, e))
        # 该情绪下各 ref 的最好成绩
        best = {}
        for fit, ref, c, r, e in rows:
            if ref not in best:
                best[ref] = (fit, c, r)
        print("  逐音色最好成绩：")
        for ref, (fit, c, r) in sorted(best.items(), key=lambda x: x[1][0]):
            print("    %-11s %-7s fit=%.2f  跨度%.0f A%.2f" % (ref, c, fit, r["span"], r["A"]))


if __name__ == "__main__":
    main()
