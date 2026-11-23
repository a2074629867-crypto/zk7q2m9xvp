# -*- coding: utf-8 -*-
"""_excited_pick.py —— 用「闸自己的尺子」给 Thomas 全段打兴奋分，挑参考。

为什么不用 e2v 挑（2026-11-13 17:55 实测教训）：
  兴奋档的信号是 vox 的 `a_x_v = arousal × valence`，不是 e2v 的 happy。
  两者会给出相反结论：现役 loud 参考 e2v happy 0.555（像开心），
  但 a_x_v 只有 0.169 —— 因为 arousal 0.87 × valence 0.20，听感是「凶」不是「兴奋」。
  按 e2v 排序挑参考 = 在看错的指标上优化。

做法：
  遍历 `_refs_new/meas.json` 里 role=Thomas 的全部段，逐段算 vox 三维 + a_x_v，
  按 a_x_v 排序，并带上 MOS / 时长 / F0 / 文本，便于人工看语境。
  目标：valence ≥0.38 且 MOS ≥2.2 的段（valence 是 loud 缺的那一维）。

输出 `_excited_pick.json`，供第二轮 A/B 挑 3~5 条。
"""
import json, os, sys

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")

HERE = "G:/_setup"
CAND = os.path.join(HERE, "_refs_new/cand")


def main():
    import ser as S
    import verdict as V
    from concurrent.futures import ThreadPoolExecutor

    rows = [r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"), encoding="utf-8"))
            if r.get("role") == "Thomas"]
    print("Thomas 段 %d 条，开始打 vox 三维…" % len(rows), flush=True)
    vox = S.VoxDim()

    def one(r):
        p = os.path.join(CAND, r["cid"] + ".wav")
        if not os.path.exists(p):
            return None
        sc = vox.score(p) or {}
        if not sc:
            return None
        return dict(cid=r["cid"], a_x_v=round(V.vox_feat(sc, "a_x_v"), 4),
                    A=round(float(sc.get("arousal", 0)), 3),
                    Vv=round(float(sc.get("valence", 0)), 3),
                    D=round(float(sc.get("dominance", 0)), 3),
                    mos=r.get("mos"), f0=r.get("f0"), dur=r.get("dur"),
                    e2v=r.get("e2v"), eprob=r.get("eprob"),
                    text=(r.get("text") or "")[:70])

    out = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for k, x in enumerate(ex.map(one, rows), 1):
            if x:
                out.append(x)
            if k % 30 == 0:
                print("  %d/%d" % (k, len(rows)), flush=True)

    out.sort(key=lambda x: -x["a_x_v"])
    json.dump(out, open(os.path.join(HERE, "_excited_pick.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\na_x_v 前 15：")
    print("%-10s %-7s %-5s %-5s %-5s %-5s %-6s %s"
          % ("cid", "a_x_v", "A", "V", "MOS", "时长", "F0", "文本"))
    for x in out[:15]:
        print("%-10s %-7.3f %-5.2f %-5.2f %-5.2f %-6.1f %-6.0f %s"
              % (x["cid"], x["a_x_v"], x["A"], x["Vv"], x["mos"] or 0, x["dur"] or 0,
                 x["f0"] or 0, x["text"]))

    good = [x for x in out if x["Vv"] >= 0.38 and (x["mos"] or 0) >= 2.2]
    print("\n效价 ≥0.38 且 MOS ≥2.2 的候选 %d 条：" % len(good))
    for x in good[:10]:
        print("  %-10s a_x_v %.3f  V %.2f  MOS %.2f  %.1fs" % (x["cid"], x["a_x_v"], x["Vv"],
                                                              x["mos"], x["dur"]))


if __name__ == "__main__":
    main()
