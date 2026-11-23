"""_aes_pref_eval.py —— 用 Meta audiobox-aesthetics 预测人工 A/B 偏好。

数据：_mt_labels_live.json（60 条人工标注，pick = 42 / 1234 / rate / none）
方法：对每条单元的两个候选分别打 CE/CU/PC/PQ 四维分，
      看哪个候选分数高，与人工 pick 是否一致。
基线：随机 50%。此前 sep 判据只有 27%（比随机差）。

跑法（G:/Python310，需要 torch + audiobox_aesthetics）：
  G:/Python310/python.exe _aes_pref_eval.py --out _aes_pref.json
"""
import argparse
import glob
import json
import os
import statistics
import warnings

warnings.filterwarnings("ignore")

ROOT = "G:/_setup"
LABELS = os.path.join(ROOT, "_mt_labels_live.json")
DIMS = ["CE", "CU", "PC", "PQ"]


def find_wav(uid, seed):
    """按 seed 找候选 wav；也兼容降速版命名。"""
    for d in ("_mt_raw_s%s" % seed, "_mt_raw_%s" % seed):
        p = os.path.join(ROOT, d, uid + ".wav")
        if os.path.exists(p):
            return p
    return None


def score_batch(pred, paths, bs=8):
    out = {}
    for i in range(0, len(paths), bs):
        chunk = paths[i:i + bs]
        try:
            ro = pred.forward([{"path": p} for p in chunk])
        except Exception as e:
            print("  !! batch fail %s" % e)
            continue
        for p, o in zip(chunk, ro):
            out[p] = {k: float(o[k]) for k in DIMS if k in o}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_aes_pref.json"))
    ap.add_argument("--seeds", default="42,1234")
    a = ap.parse_args()

    seeds = a.seeds.split(",")
    lab = json.load(open(LABELS, encoding="utf-8"))

    # 只保留被比较的两个 seed 都在标注里、且文件都存在的单元
    pairs = []
    miss = 0
    for uid, v in lab.items():
        pick = str(v.get("pick"))
        if pick not in seeds:
            continue
        got = {}
        for s in seeds:
            p = find_wav(uid, s)
            if p:
                got[s] = p
        if len(got) < len(seeds):
            miss += 1
            continue
        pairs.append(dict(uid=uid, pick=pick, **got))

    print("可比单元 %d（缺文件跳过 %d）" % (len(pairs), miss))
    if not pairs:
        return

    allp = [p[s] for p in pairs for s in seeds]
    print("待打分音频 %d 条" % len(allp))

    from audiobox_aesthetics.infer import initialize_predictor
    pred = initialize_predictor()
    sc = score_batch(pred, allp)
    print("打分成功 %d 条" % len(sc))

    rows = []
    for p in pairs:
        if any(p[s] not in sc for s in seeds):
            continue
        d = {}
        for s in seeds:
            d[s] = sc[p[s]]
        rows.append(dict(uid=p["uid"], pick=p["pick"], **{s: d[s] for s in seeds}))

    print("\n=== 各维度预测人工偏好的命中率（n=%d）===" % len(rows))
    print("%-6s %-10s %-10s %-10s" % ("dim", "higher", "lower", "best"))
    res = {}
    for k in DIMS:
        hi = sum(1 for r in rows if (r[r["pick"]][k] > r[[s for s in seeds if s != r["pick"]][0]][k]))
        lo = len(rows) - hi
        res[k] = dict(higher=hi / len(rows), lower=lo / len(rows),
                      best=max(hi, lo) / len(rows))
        print("%-6s %-10.3f %-10.3f %-10.3f" % (k, hi / len(rows), lo / len(rows), max(hi, lo) / len(rows)))

    # 组合：z-score 后加权
    print("\n=== 组合判据 ===")
    def z(r, k):
        vals = [r[s][k] for s in seeds]
        m = statistics.mean(vals)
        sd = statistics.pstdev(vals)
        return {s: (r[s][k] - m) / sd if sd > 1e-9 else 0.0 for s in seeds}

    combos = {
        "CE only": [("CE", 1)],
        "PQ only": [("PQ", 1)],
        "CE+PQ": [("CE", 1), ("PQ", 1)],
        "CE+CU": [("CE", 1), ("CU", 1)],
        "CE+PQ-CU": [("CE", 1), ("PQ", 1), ("CU", -1)],
    }
    for name, w in combos.items():
        hit = 0
        for r in rows:
            zs = {s: sum(wt * z(r, k)[s] for k, wt in w) for s in seeds}
            win = max(seeds, key=lambda s: zs[s])
            if win == r["pick"]:
                hit += 1
        print("  %-12s %.3f" % (name, hit / len(rows)))

    # 分维度原始分对照（看是否有系统偏移）
    print("\n=== 被选中 vs 未被选中 的平均分 ===")
    for k in DIMS:
        sel = [r[r["pick"]][k] for r in rows]
        oth = [r[[s for s in seeds if s != r["pick"]][0]][k] for r in rows]
        print("  %-3s 选中 %.3f  未选中 %.3f  差 %+.3f" % (k, statistics.mean(sel), statistics.mean(oth), statistics.mean(sel) - statistics.mean(oth)))

    json.dump(dict(n=len(rows), seeds=seeds, dims=res,
                   rows=[{kk: vv for kk, vv in r.items()} for r in rows]),
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写出 %s" % a.out)


if __name__ == "__main__":
    main()
