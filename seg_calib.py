# -*- coding: utf-8 -*-
"""分段声纹判据标定：0.55 这个阈值到底成不成立。

三个对照：
  A 同条内 段 vs 段      （现判据用的就是这个）
  B 同 voice 跨条 段 vs 段（narrator 全是 narr_mc_1，天然基线）
  C 不同 voice 跨条 段 vs 段（应该明显更低）

若 A ≈ B >> C ⇒ 0.55 有意义，A<0.55 的确实是条内漂移
若 A ≈ B ≈ C ⇒ 这个 embedding 在这批音频上没有区分力，判据作废
"""
import glob
import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_segcheck as SC

os.environ.setdefault("SEGCHK_DIR", "D:/_segchk_calib")
os.makedirs(os.environ["SEGCHK_DIR"], exist_ok=True)
SC.SEGDIR = os.environ["SEGCHK_DIR"]

OUT = "_seg_calib.json"
PLAN = "_castle_en_ch123_plan.jsonl"


def load_plan():
    m = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            r = json.loads(l)
            m[r["id"]] = r
    return m


def seg_embs(path, tag):
    """切成段 → 每段 embedding（与 check() 完全同一条路径）"""
    a, sr = SC.read_wav(path)
    raw = SC.split_at_silence(a, sr)
    out = []
    for i, (s0, s1) in enumerate(raw):
        seg = a[int(s0 * sr):int(s1 * sr)]
        d = len(seg) / sr
        if d < SC.MIN_SEG:
            continue
        p = os.path.join(SC.SEGDIR, "%s_p%d.wav" % (tag, i))
        s = seg
        if d < SC.PAD_TO:
            s = np.tile(seg, int(np.ceil(SC.PAD_TO / d)))
        SC.write_wav(p, s, sr)
        out.append({"i": i, "dur": d, "emb": SC.SPK.embed(p)})
    return out


def cos(a, b):
    return float(SC.SPK.cos(a, b))


def main():
    plan = load_plan()
    files = sorted(glob.glob("_audio_ch123/out/*.wav"))
    narr = [f for f in files if plan.get(os.path.basename(f)[:-4], {}).get("voice") == "narr_mc_1"]
    other = {}
    for f in files:
        v = plan.get(os.path.basename(f)[:-4], {}).get("voice")
        if v and v != "narr_mc_1":
            other.setdefault(v, []).append(f)

    # 取 30 条 narrator，每条保留全部段
    pick = narr[::max(1, len(narr) // 30)][:30]
    recs = []
    for f in pick:
        k = os.path.basename(f)[:-4]
        embs = seg_embs(f, k)
        if len(embs) >= 2:
            recs.append((k, embs))
    print("narrator 可用条 %d" % len(recs))

    # A：同条内
    A = []
    for k, embs in recs:
        for (x, y) in itertools.combinations(embs, 2):
            A.append(cos(x["emb"], y["emb"]))

    # B：同 voice 跨条（每条的段 0 与另一条的段 0..n）
    B = []
    for (k1, e1), (k2, e2) in itertools.combinations(recs, 2):
        B.append(cos(e1[0]["emb"], e2[0]["emb"]))

    # C：不同 voice 跨条
    keys = [v for v, fs in other.items() if len(fs) >= 2][:8]
    C = []
    for v1, v2 in itertools.combinations(keys, 2):
        f1 = other[v1][0]
        f2 = other[v2][0]
        e1 = seg_embs(f1, "x_" + v1)
        e2 = seg_embs(f2, "x_" + v2)
        if e1 and e2:
            C.append(cos(e1[0]["emb"], e2[0]["emb"]))

    def stat(name, arr):
        if not arr:
            print("%-6s 无样本" % name)
            return
        s = sorted(arr)
        print("%-6s n=%-5d min %6.3f  p10 %6.3f  p25 %6.3f  med %6.3f  p75 %6.3f  p90 %6.3f  max %6.3f"
              % (name, len(s), s[0], s[int(len(s) * .1)], s[len(s) // 4], s[len(s) // 2],
                 s[3 * len(s) // 4], s[int(len(s) * .9)], s[-1]))

    print("\n=== 三组对照（CAM++ en-voxceleb 余弦）===")
    stat("A 同条内", A)
    stat("B 同voice跨条", B)
    stat("C 跨voice", C)

    res = {"A_same_utt": A, "B_same_voice": B, "C_diff_voice": C}
    json.dump(res, open(OUT, "w", encoding="utf-8"))
    print("\n落盘 %s" % OUT)

    # 建议阈值：取 B 的 p10 与 C 的 p90 中点（若可分离）
    if B and C:
        lo = sorted(B)[int(len(B) * .10)]
        hi = sorted(C)[int(len(C) * .90)]
        print("B p10 = %.3f ; C p90 = %.3f ; 中点 = %.3f" % (lo, hi, (lo + hi) / 2))
        if lo <= hi:
            print("⚠ 同人下界 <= 异人上界 ⇒ 该 embedding 在此批音频上不可分，0.55 判据无依据")


if __name__ == "__main__":
    main()
