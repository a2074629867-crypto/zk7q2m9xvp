# -*- coding: utf-8 -*-
"""_gap_cand.py —— 统计旁白里「两个有效窗之间夹着 >=3 窗失声」的候选，
记录左翼窗 voiced 值，用来定「失声」判据的左翼门槛。

背景：插停顿后 c1_0001 从 WARN 变 FAIL，但两条音频的静音段完全一样，
      唯一差别是左翼窗 voiced 0.50 vs 0.62 —— 旧门槛 VOICED_OK=0.60 正好卡在抖动区。
用法：G:/Python310/python.exe -u _gap_cand.py --dir _audio_ch123/out -j 6
"""
import sys, os, json, argparse, glob, collections
import concurrent.futures as cf

sys.path.insert(0, "G:/_setup")
import mt_seg_drift as M


def one(p):
    try:
        a, sr = M.read_wav(p)
        S = M.series(a, sr)
        ws = M.windows(a, sr, S)
    except Exception as e:  # noqa: BLE001
        return os.path.basename(p)[:-4], {"err": str(e)}
    lv = [w["rms"] for w in ws if w["rms"] is not None]
    loud = max(lv) if lv else None
    usable = [i for i, w in enumerate(ws)
              if w["voiced"] >= M.VOICED_USABLE and w["f0"]
              and (loud is None or w["rms"] is None or w["rms"] >= loud - 25.0)]
    cands = []
    for a_i, b_i in zip(usable, usable[1:]):
        if b_i - a_i < 2:
            continue
        A = ws[a_i]
        mid = ws[a_i + 1:b_i]
        if not mid:
            continue
        if max(m["voiced"] for m in mid) <= M.VOICED_BAD:
            cands.append(dict(t=round(mid[0]["t0"], 2), n=len(mid),
                              a=round(A["voiced"], 2), b=round(ws[b_i]["voiced"], 2),
                              rmsmid=round(max((m["rms"] or -99) for m in mid), 1)))
    return os.path.basename(p)[:-4], {"dur": round(len(a) / sr, 2), "cands": cands}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="G:/_setup/_audio_ch123/out")
    ap.add_argument("--ids", default="G:/_setup/_narr_ids.txt")
    ap.add_argument("-j", type=int, default=6)
    ap.add_argument("--out", default="G:/_setup/_gap_cand.json")
    a = ap.parse_args()

    ids = open(a.ids).read().split(",") if os.path.exists(a.ids) else []
    files = [os.path.join(a.dir, i + ".wav") for i in ids if i]
    files = [f for f in files if os.path.exists(f)]
    print("文件 %d" % len(files), flush=True)

    res = {}
    with cf.ProcessPoolExecutor(max_workers=a.j) as ex:
        for k, (sid, r) in enumerate(ex.map(one, files), 1):
            res[sid] = r
            if k % 100 == 0:
                print("  %d/%d" % (k, len(files)), flush=True)

    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    big = [(sid, c) for sid, r in res.items() for c in (r.get("cands") or []) if c["n"] >= 3]
    print("总候选 %d；>=3 窗的 %d 条分布在 %d 个文件"
          % (sum(len(r.get("cands") or []) for r in res.values()), len(big),
             len(set(x[0] for x in big))))
    c = collections.Counter()
    for sid, x in big:
        av = x["a"]
        c["<0.65" if av < 0.65 else ("0.65~0.75" if av < 0.75 else ">=0.75")] += 1
    print("按左翼 voiced 分档：", dict(c))
    for sid, x in sorted(big, key=lambda y: y[1]["a"])[:15]:
        print("   %-9s t=%5.2f n=%d a=%.2f b=%.2f mid_rms=%s" % (sid, x["t"], x["n"], x["a"], x["b"], x["rmsmid"]))


if __name__ == "__main__":
    main()
