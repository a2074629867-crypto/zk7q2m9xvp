# -*- coding: utf-8 -*-
"""gate_scs.py —— 第 5 闸：角色/档级音色一致性（SceneTTS-Bench §3.3 的 SCS 口径，本地改造版）。

为什么不直接用 ch123_scs.py 的 z-score：
  实测 239 条上 Joseph 核心簇 σ=0.017 ⇒ 正常句子被打到 20~29σ，但 top-1 角色归属
  仍然是 Joseph。也就是说 z 爆表是「该角色内部过于一致」造成的分母病，不是换人。
  角色内分布严重非正态（Joseph 紧成一点、Charles 散成一片），z 判据在这里不成立。

改成两级判据（都是相对量，不用绝对阈值）：
  级 1 逐条「档内一致性」：同 voice 档、≥3 句时，该条与同档其他句的 cos 中位。
       同一参考档生成的句子应当彼此更像。标定（r34，239 条）：
         ≥2.0s：p5 0.420 / p10 0.552 / p50 0.688  ⇒ 取 0.42 为下限（FPR≈5%）
         <2.0s 一律不判（短句声纹不可靠，实测 0.5s 句的档内中位可低到 0.16）
  级 2 档级「归属」：档中心对「本角色中心」vs「其他角色中心」谁更近。
       别的角色更近 ⇒ 该档参考素材本身不是这个角色（素材问题，重生成修不好）。
       只用于批量报告，不参与单条判决（档内只有 2-3 句时不可靠）。
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "G:/_setup")

PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
EMB = "G:/_setup/_utt_emb/%s.npz"
AUD = "G:/_setup/_audio_ch123/out"

MIN_DUR = 2.0        # 低于此不判（短句声纹不可靠）
TIER_MIN = 3         # 档内至少 3 句才互比
THR_IN = 0.42        # 档内中位 cos 下限（≥2s 的 p5）

_C = {}


def _nrm(v):
    return v / (np.linalg.norm(v) + 1e-9)


def _dur(k):
    try:
        import soundfile as sf
        return sf.info(os.path.join(AUD, k + ".wav")).duration
    except Exception:
        return 0.0


def build(model="r34"):
    """建索引：每条的档内中位 cos + 档级归属。"""
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l); plan[o["id"]] = o
    z = np.load(EMB % model)
    ids, whos, E = list(z["ids"]), list(z["whos"]), z["embs"]
    dur = {k: _dur(k) for k in ids}

    tiers, roles = {}, {}
    for i, k in enumerate(ids):
        tiers.setdefault(plan[k]["voice"], []).append(i)
        roles.setdefault(plan[k]["who"], []).append(i)

    # 档级：档中心 / 角色中心
    tier_c = {v: _nrm(E[ix].mean(0)) for v, ix in tiers.items() if len(ix) >= 2}
    role_c = {w: _nrm(E[ix].mean(0)) for w, ix in roles.items() if len(ix) >= 6}
    tier_own = {}
    for v, c in tier_c.items():
        own = v.split("_")[0]
        sc = {w: float(c @ rc) for w, rc in role_c.items()}
        best = max(sc, key=sc.get)
        tier_own[v] = dict(own=own, own_cos=round(sc.get(own, float("nan")), 3),
                           best=best, best_cos=round(sc[best], 3),
                           flip=(best != own), n=len(tiers[v]))

    per = {}
    for v, ix in tiers.items():
        # ★ 档内互比只用「够长」的句子（2026-11-15 16:4x 修）
        #   原来 23 句一锅算中位，其中 16 句是 0.36~0.76s 的 "No." / "Yes." / "It..."。
        #   短句的 embedding 本身不可靠（实测这批短句的档内 med 全在 0.152），
        #   它们自己因为 < MIN_DUR 被判 NA 不报，却**把别人的档内中位拉下去**：
        #   Charles_soft_1 全档 23 句 med 0.379~0.457（全部 < 0.42 判离群），
        #   只拿 6 条 >=2.0s 的互比 med 0.670~0.769（全部远高于阈值）。
        #   ⇒ 分母里混了不同可靠度的样本，和「z 阈值跨域」是同一类错误。
        ix = [i for i in ix if dur.get(ids[i], 0.0) >= MIN_DUR]
        if len(ix) < TIER_MIN:
            for i in tiers[v]:
                per[ids[i]] = None
            continue
        S = E[ix]
        C = S @ S.T
        med_all = float(np.median([np.median(np.delete(C[a], a)) for a in range(len(ix))]))
        for a, i in enumerate(ix):
            oth = np.delete(C[a], a)
            per[ids[i]] = dict(tier=v, med=float(np.median(oth)), mn=float(np.min(oth)),
                               tier_med=med_all, tier_n=len(ix))
    _C.clear()
    _C.update(dict(per=per, tier=tier_own, dur=dur, model=model, plan=plan))
    return _C


def idx():
    return _C if _C else build()


def check(wav):
    """-> (verdict, note)；verdict ∈ PASS / MANUAL / NA"""
    c = idx()
    k = os.path.splitext(os.path.basename(wav))[0]
    r = c["per"].get(k)
    d = c["dur"].get(k, 0.0)
    # ★ 先判短句：短句现在不进档内互比（per 里没有它），若先判 per 会报成
    #   「档内不足 3 句」，措辞误导（实际原因是它自己太短）。两者同为 NA，不影响判决。
    if d < MIN_DUR:
        return "NA", {"code": "scs_short",
                      "why": "%.2fs < %.1fs，短句声纹不可靠（实测 0.5s 句档内中位可低到 0.16）"
                             % (d, MIN_DUR)}
    if r is None:
        return "NA", {"code": "scs_unmeasurable",
                      "why": "%s 档内 >=%.1fs 的句子不足 %d 句，无法互比" % (
                          c["plan"].get(k, {}).get("voice", "?"), MIN_DUR, TIER_MIN)}
    t = c["tier"].get(r["tier"], {})
    bad_tier = r["tier_med"] < THR_IN
    if r["med"] < THR_IN:
        why = "档内一致性低：与同档其他 %d 句 cos 中位 %.2f < %.2f" % (
            r["tier_n"] - 1, r["med"], THR_IN)
        if bad_tier:
            why += "；该档整体中位仅 %.2f（整档生成不稳，非单条问题）" % r["tier_med"]
        if t.get("flip"):
            why += "；★该档中心更像 %s（%.2f vs 本角色 %.2f）" % (
                t["best"], t["best_cos"], t["own_cos"])
        return "MANUAL", {"code": "scs_outlier", "why": why,
                          "med": round(r["med"], 3), "tier_med": round(r["tier_med"], 3),
                          "tier": r["tier"], "flip": bool(t.get("flip"))}
    return "PASS", {"code": "scs_ok",
                    "why": "档内一致 %.2f（档中位 %.2f）" % (r["med"], r["tier_med"]),
                    "med": round(r["med"], 3), "tier_med": round(r["tier_med"], 3),
                    "tier": r["tier"]}


def report():
    c = idx()
    print("== 档级归属（档中心对哪个角色中心最近）")
    print("%-24s %-8s %-7s %-8s %-7s %s" % ("档", "句数", "本角色", "本角色cos", "最近", "判决"))
    for v, t in sorted(c["tier"].items(), key=lambda x: x[1]["own_cos"]):
        print("%-24s %-8d %-7s %-8.3f %-7s %s"
              % (v, t["n"], t["own"], t["own_cos"], t["best"],
                 "★归属翻转 -> %s %.3f" % (t["best"], t["best_cos"]) if t["flip"] else "ok"))
    fail = [k for k, r in c["per"].items() if r and r["med"] < THR_IN
            and c["dur"].get(k, 0) >= MIN_DUR]
    print()
    print("== 逐条档内离群（≥%.1fs 且 med<%.2f）：%d 条" % (MIN_DUR, THR_IN, len(fail)))
    for k in sorted(fail, key=lambda x: c["per"][x]["med"]):
        r = c["per"][k]
        print("  %-8s %-22s %-8s %5.2fs med %.3f (档中位 %.3f, n=%d)"
              % (k, r["tier"], c["plan"][k]["who"], c["dur"][k], r["med"],
                 r["tier_med"], r["tier_n"]))


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        for w in sys.argv[1:]:
            print(os.path.basename(w), check(w))
