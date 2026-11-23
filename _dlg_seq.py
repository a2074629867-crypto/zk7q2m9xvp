# -*- coding: utf-8 -*-
"""_dlg_seq.py —— 条间音色一致性（用户 2026-11-14 15:48 指出：音色突变最常见在
「换句之后、标点停顿之后」，是**条与条之间**，不是句内）

做法：
  1. 每个角色单独一条时间线（按 id 编号 = 文本顺序），只比**同角色**相邻两次出场
  2. 两路证据：
     A. r34 embedding 余弦（身份）
     B. 句级声道指纹（drift 窗的 cen/slp/hnr 中位 → 对数距离）
  3. 分「同情绪档 / 跨情绪档」统计 —— 情绪变化本身会拉低 cos，不能混算
  4. 找离群：cos 低于同层 p5，或声道距离高于同层 p95

用法：G:/Python310/python.exe _dlg_seq.py
"""
import json, os, math, statistics as st, collections
import numpy as np

P = "G:/_setup"
os.chdir(P)

plan = [json.loads(l) for l in open("_dlg_plan_v2.jsonl", encoding="utf-8")]
by_id = {r["id"]: r for r in plan}

z = np.load("_utt_emb/r34.npz", allow_pickle=True)
emb = {str(i): e for i, e in zip(z["ids"], z["embs"])}
emb = {k: v / (np.linalg.norm(v) + 1e-9) for k, v in emb.items()}

# 句级声道指纹：drift 窗里 voiced 足够、f0 可测的窗取中位
cache = {os.path.basename(x["file"])[:-4]: x for x in json.load(open("_drift_cache.json", encoding="utf-8"))}


def timbre_fp(sid):
    x = cache.get(sid)
    if not x:
        return None
    ws = [w for w in (x.get("windows") or []) if (w.get("voiced") or 0) >= 0.30 and w.get("f0")]
    if len(ws) < 2:
        return None
    out = {}
    for k in ("cen", "slp", "hnr", "f0"):
        v = [w[k] for w in ws if w.get(k) is not None]
        if not v:
            return None
        out[k] = st.median(v)
    return out


# 按角色分组、按 id 排序
bywho = collections.defaultdict(list)
for r in plan:
    bywho[r["who"]].append(r)
for w in bywho:
    bywho[w].sort(key=lambda r: r["id"])

pairs = []
for who, seq in bywho.items():
    for a, b in zip(seq, seq[1:]):
        if a["id"] not in emb or b["id"] not in emb:
            continue
        cos = float(np.dot(emb[a["id"]], emb[b["id"]]))
        fa, fb = timbre_fp(a["id"]), timbre_fp(b["id"])
        dist = None
        if fa and fb:
            # 声道形状对数距离：谱质心比值 + 谱倾斜差 + HNR 差
            d1 = abs(math.log(fa["cen"] / fb["cen"]))
            d2 = abs(fa["slp"] - fb["slp"]) / 10.0
            d3 = abs(fa["hnr"] - fb["hnr"]) / 10.0
            dist = round(math.sqrt(d1 * d1 + d2 * d2 + d3 * d3), 3)
        pairs.append(dict(a=a["id"], b=b["id"], who=who,
                          emo_a=a["emo"], emo_b=b["emo"],
                          same_emo=(a["emo"] == b["emo"]),
                          voice_a=a.get("voice"), voice_b=b.get("voice"),
                          same_voice=(a.get("voice") == b.get("voice")),
                          cos=round(cos, 3), dist=dist))

print("同角色相邻出场对 %d（角色内时间线）" % len(pairs))
print("  同情绪档 %d ｜ 跨情绪档 %d" % (sum(p["same_emo"] for p in pairs),
                                     sum(not p["same_emo"] for p in pairs)))
print("  同 voice 档 %d ｜ 换档 %d" % (sum(p["same_voice"] for p in pairs),
                                     sum(not p["same_voice"] for p in pairs)))


def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))]


print()
print("%-10s %4s | %-22s | %s" % ("层", "n", "cos p5 / 中位 / p95", "声道距离 中位 / p95"))
for label, sub in (("同档同voice", [p for p in pairs if p["same_emo"] and p["same_voice"]]),
                   ("同档换voice", [p for p in pairs if p["same_emo"] and not p["same_voice"]]),
                   ("跨档", [p for p in pairs if not p["same_emo"]])):
    if not sub:
        continue
    cs = [p["cos"] for p in sub]
    ds = [p["dist"] for p in sub if p["dist"] is not None]
    print("%-10s %4d | %.3f / %.3f / %.3f | %s" % (
        label, len(sub), q(cs, .05), q(cs, .5), q(cs, .95),
        ("%.2f / %.2f" % (q(ds, .5), q(ds, .95))) if ds else "-"))

print()
print("=== 最可疑 20 对（同角色，按 cos 升序）===")
print("%-9s %-9s %-8s %-4s %-4s %-5s %-5s %s" % ("前", "后", "角色", "emo前", "emo后", "cos", "声道", "voice"))
for p in sorted(pairs, key=lambda x: x["cos"])[:20]:
    print("%-9s %-9s %-8s %-4s %-4s %.3f %-5s %s" % (
        p["a"], p["b"], p["who"], p["emo_a"], p["emo_b"], p["cos"],
        p["dist"] if p["dist"] is not None else "-",
        ("同" if p["same_voice"] else "%s→%s" % (p["voice_a"], p["voice_b"]))))

json.dump(pairs, open("_dlg_seq_pairs.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n写出 _dlg_seq_pairs.json")
