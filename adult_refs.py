# -*- coding: utf-8 -*-
"""冷启动补角色音色：从一部片里自动切出"没有模板"的角色。

为什么需要它
------------
1-NN 判角色必须有模板，没模板的角色会被硬塞进已有桶里。实测《城堡之王》
257 条 cue 全被判成 Thomas 193 / Charles 64，成年男（Joseph）和成年女
（Helena）一条都没单独出来。所以补角色音色不能从"判角色"入手，要先
**按声音聚类**，再人工点一下"这簇是谁"。

流程
----
  ① 声纹 embedding 余弦聚类 → 分几簇（不需要任何模板）
  ② 每簇报中位 F0 → 男/女/童，先排除明显不合的
  ③ 簇内按技术指标筛干净句（时长 / 静音 / 长停顿 / 语速）
  ④ 打印文本给人读（"Papa"/"maman" 这种称呼最可靠）
  ⑤ 给定 {簇: 角色名} 与留用清单 → 建库 + 留一法自检

用法
----
  # 第一步：看有几簇（打印候选表）
  python adult_refs.py --dir _emo_auto/cues --report

  # 第二步：按人工点名建库
  python adult_refs.py --dir _emo_auto/cues --build --names 0=Joseph 2=Helena \
      --pick J_normal:c046 J_ramble:c048 ... --out _adult_refs.json
"""
import argparse
import collections
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, "G:/_setup")


def load_embs(dirpath, ids=None):
    from chain_check import EmoVoice
    m = EmoVoice().m
    files = sorted(glob.glob(os.path.join(dirpath, "*.wav")))
    if ids:
        files = [f for f in files if os.path.basename(f)[:4] in ids]
    out = []
    for f in files:
        out.append((os.path.basename(f)[:4], f, m.embed(f)))
    return out


def cluster(rows, k):
    from sklearn.cluster import AgglomerativeClustering
    E = np.array([r[2] for r in rows], dtype=np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    lab = AgglomerativeClustering(n_clusters=k, metric="cosine",
                                  linkage="average").fit_predict(E)
    return E, lab


def vocal_band(f0):
    if f0 <= 0:
        return "?"
    if f0 < 145:
        return "成年男"
    if f0 < 175:
        return "界(男/女)"
    if f0 < 225:
        return "成年女"
    if f0 < 240:
        return "界(女/童)"
    return "儿童"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--cluster", default="out/voice_cluster.json")
    ap.add_argument("--cand", default="_emo_auto/candidates.json")
    ap.add_argument("--out", default="_adult_refs.json")
    ap.add_argument("--refdir", default="refs_adult")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--names", nargs="*", default=[], help="0=Joseph 2=Helena")
    ap.add_argument("--pick", nargs="*", default=[], help="档名:c编号")
    ap.add_argument("--loio", action="store_true", help="跑留一法自检")
    a = ap.parse_args()

    vc = json.load(open(a.cluster, encoding="utf-8"))
    cl = {r["id"]: r["cl"] for r in vc["rows"]}
    f0 = {r["id"]: r["f0"] for r in vc["rows"]}
    cand = {r["id"]: r for r in json.load(open(a.cand, encoding="utf-8"))}

    if a.report:
        for c in sorted(set(cl.values())):
            ids = [i for i in cl if cl[i] == c]
            f = np.median([f0[i] for i in ids if f0[i] > 0])
            rows = [cand[i] for i in ids if i in cand]
            good = [r for r in rows if 1.8 <= r["dur"] <= 12.0
                    and r["sil"] <= 0.45 and r["long_sil"] <= 1.5]
            print("\n簇 %-2d %3d 条  F0 %3.0f（%s）  干净 %d 条"
                  % (c, len(ids), f, vocal_band(f), len(good)))
            for r in sorted(good, key=lambda x: x["id"])[:12]:
                print("   %-5s %4.1fs | %s" % (r["id"], r["dur"], r["text"][:70]))
        return

    if not a.build:
        sys.exit("给 --report 或 --build")

    names = dict(x.split("=", 1) for x in a.names)
    picked = dict(x.split(":", 1) for x in a.pick)
    os.makedirs(a.refdir, exist_ok=True)

    lib = collections.defaultdict(dict)
    for ref_name, cid in picked.items():
        role_id, slot = ref_name.split("_", 1)
        role = names.get(role_id, role_id)
        src = glob.glob(os.path.join(a.dir, "%s_*.wav" % cid))[0]
        import shutil
        dst = os.path.join(a.refdir, "%s_%s_%s.wav" % (role, slot, cid))
        shutil.copy2(src, dst)
        lib[role].setdefault(slot, []).append({
            "path": dst.replace("\\", "/"),
            "text": cand.get(cid, {}).get("text", ""),
            "from": cid,
        })

    json.dump(lib, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("建库 -> %s" % a.out)
    for role, slots in lib.items():
        print("  %-8s %d 档  %s" % (role, len(slots), " ".join(slots)))

    if a.loio:
        from chain_check import EmoVoice
        m = EmoVoice().m
        E, keys = {}, []
        for role, slots in lib.items():
            for slot, items in slots.items():
                p = items[0]["path"]
                E[(role, slot)] = m.embed(p)
                keys.append((role, slot))
        print("\n留一法（拿掉这条，用同角色其他条当模板）:")
        ok = n = 0
        for (role, slot), e in E.items():
            same = [(r, s) for (r, s) in keys if r == role and s != slot]
            other = [(r, s) for (r, s) in keys if r != role]
            en = e / np.linalg.norm(e)
            bs = max(float(en @ (E[t] / np.linalg.norm(E[t]))) for t in same)
            bo = max(float(en @ (E[t] / np.linalg.norm(E[t]))) for t in other)
            good = bs > bo
            ok += good
            n += 1
            print("  %-8s %-9s 组内 %.3f | 跨角色 %.3f %s"
                  % (role, slot, bs, bo, "OK" if good else "✗"))
        print("留一法 %d/%d" % (ok, n))


if __name__ == "__main__":
    main()
