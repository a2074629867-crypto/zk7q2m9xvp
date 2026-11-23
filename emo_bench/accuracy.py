# -*- coding: utf-8 -*-
"""
情绪表现「判断准确度」评测 —— 有 ground truth，才算准确度。

前面所有指标（占真人百分比、相对 base 的 Δ、区间吻合分）都没有标准答案，
只能说明「像不像真人 / 变没变」，回答不了「判得对不对」。
本脚本改用**意图标签当标准答案**：

  GT-1  Expresso 745 条：录音时指定的 style（happy/sad/laughing/default/...）
  GT-2  48 条情绪矩阵：生成时指定的 cond（happy/sad/angry/afraid/calm/base）
  GT-3  ch123 60 条成品对白：人工标注的 emo（calm/sad/happy）

三种引擎配置，分别测：
  A  e2v 零样本 top-1            —— 现成可用的离散分类
  B  vox_dim 三维 → 原型最近邻    —— 不训练，纯用 A/V/D
  C  vox_dim + 物理量 → 逻辑回归  —— 在 Expresso 上监督校准（有 ground truth 训练）
  D  C 的跨域迁移                —— Expresso 训练 → 测 TTS 生成集，这才是我们的实际场景

评估项：accuracy / macro-F1 / 混淆矩阵 / 排序正确率 / AUC，
        全部带 bootstrap 95% CI 与置换检验 p，并明确给出 majority 瞎猜基线。
"""
import json
import os
import sys
import itertools
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_predict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RNG = np.random.default_rng(0)

# ── Expresso style → 我们的目标类别 ───────────────────────────────
# 只保留映射无歧义的：happy/laughing→happy，sad→sad，default→neutral
STYLE2CLS = {
    "happy": "happy",
    "laughing": "happy",
    "sad": "sad",
    "default": "neutral",
}
# 无对应类的风格不参与（confused/enunciated/emphasis/whisper）：
#   emphasis 是重音不是情绪；whisper 是发声方式；confused 在我们类表里没有。
E2V_KEYS = {
    "开心/happy": "happy",
    "难过/sad": "sad",
    "生气/angry": "angry",
    "中立/neutral": "neutral",
    "恐惧/fearful": "afraid",
    "厌恶/disgusted": "disgusted",
    "吃惊/surprised": "surprised",
    "其他/other": "other",
    "<unk>": "unk",
}


def load_jsonl(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def load_all():
    """返回 {path: {vox, e2v, phys}} 与元数据表。"""
    feat = {}
    for r in load_jsonl("real_vox_dim.jsonl") + load_jsonl("gen_vox_dim.jsonl"):
        if r.get("score"):
            feat.setdefault(r["path"], {})["vox"] = r["score"]
    for r in load_jsonl("real_e2v.jsonl") + load_jsonl("gen_e2v.jsonl"):
        if r.get("score"):
            feat.setdefault(r["path"], {})["e2v"] = r["score"]
    for r in load_jsonl("real_phys.jsonl") + load_jsonl("gen_phys.jsonl"):
        if r.get("score"):
            feat.setdefault(r["path"], {})["phys"] = r["score"]

    meta = {}
    for r in load_jsonl("real_vox_dim.jsonl"):
        meta[r["path"]] = dict(src="expresso", style=r.get("style"),
                               speaker=r.get("speaker"))
    for r in load_jsonl("gen_index.jsonl"):
        meta[r["path"]] = dict(src="gen", cond=r["cond"], ref=r["pid"],
                               seed=r.get("seed"))
    return feat, meta


def vec(f, keys):
    """从特征 dict 取向量；缺项返回 None。"""
    v = {}
    if "vox" in f:
        v.update({("vox", k): f["vox"][k] for k in ("arousal", "valence", "dominance")})
    if "phys" in f:
        p = f["phys"]
        v[("phys", "span")] = p["f0_p90"] - p["f0_p10"]
        v[("phys", "f0")] = p["f0_med"]
        v[("phys", "db")] = p["speech_db"]
        v[("phys", "hnr")] = p["hnr"]
    out = []
    for k in keys:
        if k not in v:
            return None
        out.append(v[k])
    return out


VAD = [("vox", "arousal"), ("vox", "valence"), ("vox", "dominance")]
VAD_SPAN = VAD + [("phys", "span")]
FULL = VAD_SPAN + [("phys", "f0"), ("phys", "db"), ("phys", "hnr")]


# ── 统计工具 ──────────────────────────────────────────────────────
def acc(y, p):
    if not len(y):
        return float("nan")
    return float(np.mean(np.asarray(y) == np.asarray(p)))


def macro_f1(y, p):
    ys, ps = set(y), set(p)
    if not ys:
        return float("nan")
    f1s = []
    for c in ys:
        tp = sum(1 for a, b in zip(y, p) if a == c and b == c)
        fp = sum(1 for a, b in zip(y, p) if a != c and b == c)
        fn = sum(1 for a, b in zip(y, p) if a == c and b != c)
        f1s.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f1s))


def confusion(y, p, labels):
    M = np.zeros((len(labels), len(labels)), int)
    idx = {l: i for i, l in enumerate(labels)}
    for a, b in zip(y, p):
        if a in idx and b in idx:
            M[idx[a], idx[b]] += 1
    return M


def boot_ci(y, p, n=2000):
    y = np.asarray(y); p = np.asarray(p)
    m = len(y)
    if m < 5:
        return (float("nan"), float("nan"))
    s = []
    for _ in range(n):
        i = RNG.integers(0, m, m)
        s.append(float(np.mean(y[i] == p[i])))
    return (float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5)))


def perm_p(y, p, n=5000):
    """置换检验：打乱预测，看真实准确率是否显著高于随机。"""
    y = np.asarray(y); p = np.asarray(p)
    obs = float(np.mean(y == p))
    cnt = 0
    for _ in range(n):
        if float(np.mean(y == RNG.permutation(p))) >= obs:
            cnt += 1
    return (cnt + 1) / (n + 1)


def auc(pos, neg):
    pos = np.asarray(pos, float); neg = np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan")
    d = pos[:, None] - neg[None, :]
    return float(((d > 0).sum() + 0.5 * (d == 0).sum()) / d.size)


def boot_auc_ci(pos, neg, n=2000):
    pos = np.asarray(pos, float); neg = np.asarray(neg, float)
    if len(pos) < 3 or len(neg) < 3:
        return (float("nan"), float("nan"))
    s = []
    for _ in range(n):
        a = pos[RNG.integers(0, len(pos), len(pos))]
        b = neg[RNG.integers(0, len(neg), len(neg))]
        d = a[:, None] - b[None, :]
        s.append(((d > 0).sum() + 0.5 * (d == 0).sum()) / d.size)
    return (float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5)))


def line(ch="-", n=96):
    print(ch * n)


def hr(t):
    print()
    line("=")
    print(t)
    line("=")


# ── 引擎 A：e2v 零样本 ───────────────────────────────────────────
def run_e2v(feat, meta):
    hr("引擎 A：emotion2vec+ large 零样本 top-1（不训练、不校准）")

    # A1 Expresso 三分类
    y, p, skipped = [], [], 0
    for path, m in meta.items():
        if m["src"] != "expresso":
            continue
        gt = STYLE2CLS.get(m["style"])
        if not gt:
            skipped += 1
            continue
        f = feat.get(path, {}).get("e2v")
        if not f:
            continue
        y.append(gt); p.append(E2V_KEYS.get(f["_top"], f["_top"]))
    labels = ["happy", "sad", "neutral"]
    print("A1  Expresso 真人口语（%d 条参与，%d 条风格无对应类已剔除）" % (len(y), skipped))
    print("    accuracy = %.3f   macro-F1 = %.3f   majority 瞎猜基线 = %.3f"
          % (acc(y, p), macro_f1(y, p), max(y.count(c) for c in set(y)) / len(y)))
    print("    95%% CI = [%.3f, %.3f]   置换检验 p = %.4f" % (*boot_ci(y, p), perm_p(y, p)))
    M = confusion(y, p, labels)
    print("    混淆（行=标准答案，列=模型判）")
    print("    %-9s %s" % ("", "".join("%-9s" % c for c in labels)))
    for i, c in enumerate(labels):
        print("    %-9s %s  n=%d" % (c, "".join("%-9d" % v for v in M[i]), M[i].sum()))

    # A2 生成集五分类
    y2, p2 = [], []
    for path, m in meta.items():
        if m["src"] != "gen" or m["cond"] == "base":
            continue
        f = feat.get(path, {}).get("e2v")
        if not f:
            continue
        y2.append(m["cond"]); p2.append(E2V_KEYS.get(f["_top"], f["_top"]))
    labels2 = ["happy", "sad", "angry", "afraid", "calm"]
    print()
    print("A2  48 条情绪矩阵（TTS，40 条有标签；base 8 条另计）")
    print("    accuracy = %.3f   macro-F1 = %.3f   majority 瞎猜基线 = %.3f"
          % (acc(y2, p2), macro_f1(y2, p2),
             max(y2.count(c) for c in set(y2)) / len(y2)))
    print("    95%% CI = [%.3f, %.3f]   置换检验 p = %.4f" % (*boot_ci(y2, p2), perm_p(y2, p2)))
    M2 = confusion(y2, p2, labels2)
    print("    混淆（行=指定情绪，列=模型判）")
    print("    %-9s %s" % ("", "".join("%-9s" % c for c in labels2)))
    for i, c in enumerate(labels2):
        print("    %-9s %s  n=%d" % (c, "".join("%-9d" % v for v in M2[i]), M2[i].sum()))
    # base 被判成什么
    import collections
    b = collections.Counter()
    for path, m in meta.items():
        if m["src"] == "gen" and m["cond"] == "base":
            f = feat.get(path, {}).get("e2v")
            if f:
                b[E2V_KEYS.get(f["_top"], f["_top"])] += 1
    print("    base（无标签）8 条被判成：%s" % dict(b))
    return (acc(y, p), acc(y2, p2))


# ── 引擎 B：vox_dim 原型最近邻（零样本） ─────────────────────────
def run_proto(feat, meta):
    hr("引擎 B：vox_dim 的 A/V/D → 类原型最近邻（不训练，只用三维）")
    print("    原型取自 Expresso 各类的 A/V/D 中位数，按欧氏距离（各轴除以全体 SD）归类")

    proto = {}
    for path, m in meta.items():
        gt = STYLE2CLS.get(m.get("style"))
        f = feat.get(path, {}).get("vox")
        if m["src"] == "expresso" and gt and f:
            proto.setdefault(gt, []).append([f["arousal"], f["valence"], f["dominance"]])
    P = {k: np.median(np.array(v), 0) for k, v in proto.items()}
    allv = np.concatenate([np.array(v) for v in proto.values()])
    sd = allv.std(0)
    print("    原型：%s" % {k: np.round(v, 2).tolist() for k, v in P.items()})
    print("    各轴 SD：%s" % np.round(sd, 3).tolist())

    def predict(f):
        x = np.array([f["arousal"], f["valence"], f["dominance"]])
        d = {k: float(np.sum(((x - v) / sd) ** 2)) for k, v in P.items()}
        return min(d, key=d.get)

    y, p = [], []
    for path, m in meta.items():
        if m["src"] != "gen" or m["cond"] == "base":
            continue
        f = feat.get(path, {}).get("vox")
        if not f:
            continue
        y.append(m["cond"]); p.append(predict(f))
    labels = ["happy", "sad", "angry", "afraid", "calm"]
    print("  生成集 40 条 accuracy = %.3f   majority 基线 = %.3f"
          % (acc(y, p), max(y.count(c) for c in set(y)) / len(y)))
    M = confusion(y, p, labels)
    print("    %-9s %s" % ("", "".join("%-9s" % c for c in labels)))
    for i, c in enumerate(labels):
        print("    %-9s %s  n=%d" % (c, "".join("%-9d" % v for v in M[i]), M[i].sum()))
    return acc(y, p)


# ── 引擎 C：监督校准（Expresso 训练，交叉验证） ─────────────────
def run_lr(feat, meta, keys, tag):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    X, y, spk = [], [], []
    for path, m in meta.items():
        gt = STYLE2CLS.get(m.get("style"))
        if m["src"] != "expresso" or not gt:
            continue
        v = vec(feat.get(path, {}), keys)
        if v is None:
            continue
        X.append(v); y.append(gt); spk.append(m.get("speaker"))
    X = np.array(X); y = np.array(y)
    clf = make_pipeline(StandardScaler(),
                        LogisticRegression(max_iter=2000, C=1.0,
                                           class_weight="balanced"))
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    pred = cross_val_predict(clf, X, y, cv=cv)
    labels = ["happy", "sad", "neutral"]
    return dict(X=X, y=y, pred=pred, labels=labels, clf=clf, spk=spk, tag=tag)


def run_supervised(feat, meta):
    hr("引擎 C：vox_dim(+物理量) → 逻辑回归，Expresso 5 折交叉验证")
    print("    注意：这是在**有 ground truth 训练**的前提下能到多少，属于上限估计")

    res = {}
    for keys, tag in [(VAD, "A/V/D 三维"), (VAD_SPAN, "A/V/D + F0跨度"), (FULL, "A/V/D + 跨度 + F0 + dB + HNR")]:
        r = run_lr(feat, meta, keys, tag)
        a = acc(r["y"], r["pred"]); f1 = macro_f1(r["y"], r["pred"])
        res[tag] = r
        print("  %-34s accuracy = %.3f  macro-F1 = %.3f" % (tag, a, f1))

    best = max(res, key=lambda k: acc(res[k]["y"], res[k]["pred"]))
    r = res[best]
    print()
    print("  最优特征集：%s" % best)
    print("    95%% CI = [%.3f, %.3f]" % boot_ci(r["y"], r["pred"]))
    print("    majority 瞎猜基线 = %.3f" % (max(list(r["y"]).count(c) for c in set(r["y"])) / len(r["y"])))
    M = confusion(r["y"], r["pred"], r["labels"])
    print("    %-9s %s" % ("", "".join("%-9s" % c for c in r["labels"])))
    for i, c in enumerate(r["labels"]):
        print("    %-9s %s  n=%d" % (c, "".join("%-9d" % v for v in M[i]), M[i].sum()))
    # 说话人外推：留一人
    print()
    print("    留一说话人交叉验证（换人还能不能判）：")
    for s in sorted(set(r["spk"])):
        tr = [i for i, x in enumerate(r["spk"]) if x != s]
        te = [i for i, x in enumerate(r["spk"]) if x == s]
        clf = make_pipeline(StandardScaler(),
                            LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced"))
        clf.fit(r["X"][tr], r["y"][tr])
        pr = clf.predict(r["X"][te])
        print("      %-12s test n=%3d  accuracy = %.3f"
              % (s, len(te), acc(r["y"][te], pr)))
    return r, best


def run_transfer(feat, meta, r):
    """用 Expresso 全量训练的模型，直接判 TTS 生成集（域外迁移）。"""
    hr("引擎 D：Expresso 训练 → 直接判 TTS 生成集（跨域迁移，我们的真实场景）")
    clf = r["clf"].fit(r["X"], r["y"])
    keys = FULL
    rows = []
    for path, m in meta.items():
        if m["src"] != "gen" or m["cond"] == "base":
            continue
        v = vec(feat.get(path, {}), keys)
        if v is None:
            continue
        pr = clf.predict([v])[0]
        proba = dict(zip(clf.classes_, clf.predict_proba([v])[0]))
        rows.append((m["cond"], pr, proba))
    y = [x[0] for x in rows]; p = [x[1] for x in rows]
    print("  5 类 accuracy = %.3f   majority 基线 = %.3f"
          % (acc(y, p), max(y.count(c) for c in set(y)) / len(y)))
    print("  95%% CI = [%.3f, %.3f]   置换检验 p = %.4f" % (*boot_ci(y, p), perm_p(y, p)))
    labels = ["happy", "sad", "angry", "afraid", "calm"]
    M = confusion(y, p, labels)
    print("    %-9s %s" % ("", "".join("%-9s" % c for c in labels)))
    for i, c in enumerate(labels):
        print("    %-9s %s  n=%d" % (c, "".join("%-9d" % v for v in M[i]), M[i].sum()))

    # 二分：高激活(angry/afraid/happy) vs 低激活(sad/calm)
    hi = {"angry", "afraid", "happy"}; lo = {"sad", "calm"}
    yy, pp = [], []
    for gt, pr, prob in rows:
        if gt in hi or gt in lo:
            yy.append("high" if gt in hi else "low")
            pp.append("high" if pr in hi else "low")
    print()
    print("  二分（该激动 vs 该低沉）：accuracy = %.3f  95%% CI = [%.3f, %.3f]  p = %.4f"
          % (acc(yy, pp), *boot_ci(yy, pp), perm_p(yy, pp)))
    return rows


# ── 排序正确率：同 ref 内，语义该更强的排前面了吗 ────────────────
def run_pairwise(feat, meta):
    hr("排序正确率：同一音色、同一句话，只换情绪标签，模型把「该更强」的排到前面了吗")
    # 只用语义上无争议的 6 对：{angry, afraid, happy} × {sad, calm}
    HI = ["angry", "afraid", "happy"]
    LO = ["sad", "calm"]
    refs = sorted({m["ref"] for m in meta.values() if m["src"] == "gen"})
    print("    标准答案：%s 的强度应高于 %s（真人实测 A：0.59–0.72 vs 0.28–0.32）" % (HI, LO))

    outs = {}
    for key, name in [(("vox", "arousal"), "A（arousal）"),
                      (("phys", "span"), "F0 跨度"),
                      (("vox", "dominance"), "D（dominance）")]:
        pairs = []
        per_ref = {}
        for ref in refs:
            for a in HI:
                for b in LO:
                    pa = next((p for p, m in meta.items()
                               if m["src"] == "gen" and m["ref"] == ref and m["cond"] == a), None)
                    pb = next((p for p, m in meta.items()
                               if m["src"] == "gen" and m["ref"] == ref and m["cond"] == b), None)
                    if not pa or not pb:
                        continue
                    va = vec(feat.get(pa, {}), [key])
                    vb = vec(feat.get(pb, {}), [key])
                    if va is None or vb is None:
                        continue
                    ok = 1 if va[0] > vb[0] else 0
                    pairs.append(ok)
                    per_ref.setdefault(ref, []).append(ok)
        outs[name] = (pairs, per_ref)
        print()
        lo, hi = boot_pair_ci(pairs)
        print("  %-16s 排序正确率 = %.3f  (n=%d 对)  95%% CI = [%.3f, %.3f]  p = %.4f"
              % (name, np.mean(pairs), len(pairs), lo, hi, perm_pair_p(pairs)))
        print("      分音色：%s" % "  ".join("%s %.0f%%" % (k, 100 * np.mean(v))
                                           for k, v in per_ref.items()))
    return outs


def boot_pair_ci(x, n=2000):
    x = np.asarray(x)
    s = [np.mean(x[RNG.integers(0, len(x), len(x))]) for _ in range(n)]
    return (float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5)))


def perm_pair_p(x, n=5000):
    """排序正确率的显著性只能对 0.5 做二项检验：
    打乱标签不会改变 0/1 的多重集 ⇒ 置换均值恒等于观测值，置换检验在这里无效
    （第一版就是这么错写成 p=1.0000 的）。"""
    from scipy.stats import binomtest
    x = np.asarray(x)
    return float(binomtest(int(x.sum()), len(x), 0.5,
                          alternative="greater").pvalue)


# ── 相关性：模型分与「该有多强」的相关 ───────────────────────────
def run_corr(feat, meta):
    hr("相关性：模型分与标准答案的关联有多强（带 CI 与 p）")
    from scipy.stats import spearmanr
    ORD = {"calm": 0, "sad": 1, "happy": 2, "afraid": 3, "angry": 4}
    xs, ys = [], []
    for path, m in meta.items():
        if m["src"] != "gen" or m["cond"] not in ORD:
            continue
        f = feat.get(path, {}).get("vox")
        if not f:
            continue
        xs.append(ORD[m["cond"]]); ys.append(f["arousal"])
    r, p = spearmanr(xs, ys)
    print("  A 与标签强度的 Spearman ρ = %.3f  (n=%d, p = %.2e)" % (r, len(xs), p))
    print("    ⇒ 模型 A 与「该有多强」的关联程度；ρ=0 表示完全无关，1 表示完全一致")

    # 同 ref 内（去掉音色差异后，纯情绪判断力）
    rs = []
    refs = sorted({m["ref"] for m in meta.values() if m["src"] == "gen"})
    for ref in refs:
        x2, y2 = [], []
        for path, m in meta.items():
            if m["src"] != "gen" or m["ref"] != ref or m["cond"] not in ORD:
                continue
            f = feat.get(path, {}).get("vox")
            if f:
                x2.append(ORD[m["cond"]]); y2.append(f["arousal"])
        if len(set(x2)) >= 3:
            rr = spearmanr(x2, y2).correlation
            rs.append(rr)
            print("    %-11s ρ = %+.3f" % (ref, rr))
    print("    同音色内 ρ 中位 = %+.3f（这一步才是纯情绪判断力，排除音色干扰）"
          % np.median(rs))
    return r


def run_book(r):
    """用 Expresso 训练的模型直接判 59 条已交付对白（ch123_final）。
    标准答案 = 生产时的情绪标注（calm 34 / sad 11 / happy 7）。"""
    hr("真实成品对白：Expresso 训练 → 判已交付对白（有声书实际场景）")
    import collections
    bp = os.path.join(OUT, "book_judge.json")
    if not os.path.exists(bp):
        print("  缺 out/book_judge.json，跳过")
        return None
    rows = json.load(open(bp, encoding="utf-8"))["rows"]
    MAP = {"calm": "neutral", "sad": "sad", "happy": "happy"}
    clf = r["clf"].fit(r["X"], r["y"])
    y, p, who = [], [], []
    for x in rows:
        g = MAP.get((x.get("emo") or "").lower())
        if not g:
            continue
        v = [x["A"], x["D"], x["V"], x["span"], x["f0"], x["db"], x["hnr"]]
        y.append(g); p.append(clf.predict([v])[0]); who.append(x["who"])
    base = max(collections.Counter(y).values()) / len(y)
    labels = ["happy", "sad", "neutral"]
    print("  参与 %d 条（另有 %d 条标了 calm/sad/happy 以外的标签，剔除）"
          % (len(y), len(rows) - len(y)))
    print("  accuracy = %.3f   95%% CI = [%.3f, %.3f]   majority 基线 = %.3f"
          % (acc(y, p), *boot_ci(y, p), base))
    print("  置换检验 p = %.4f" % perm_p(y, p))
    M = confusion(y, p, labels)
    print("    %-9s %s" % ("", "".join("%-9s" % c for c in labels)))
    for i, c in enumerate(labels):
        print("    %-9s %s  n=%d" % (c, "".join("%-9d" % v for v in M[i]), M[i].sum()))
    from scipy.stats import binomtest
    yy = ["sad" if a == "sad" else "calm" for a in y]
    pp = ["sad" if b == "sad" else "calm" for b in p]
    correct = sum(1 for a, b in zip(yy, pp) if a == b)
    n_calm = yy.count("calm")
    print("  关键二分 sad vs calm：accuracy = %.3f  (n=%d, 二项检验 p = %.4f"
          " vs 全猜 calm 的 %.3f)"
          % (correct / len(yy), len(yy),
             binomtest(correct, len(yy), n_calm / len(yy), alternative="greater").pvalue,
             n_calm / len(yy)))
    for w in sorted(set(who)):
        idx = [i for i, x in enumerate(who) if x == w]
        print("    角色 %s：n=%2d  accuracy = %.3f"
              % (w, len(idx), acc([y[i] for i in idx], [p[i] for i in idx])))
    return acc(y, p), base


def main():
    feat, meta = load_all()
    print("数据：Expresso %d 条（4 说话人 / 8 风格）、情绪矩阵 %d 条"
          % (sum(1 for m in meta.values() if m["src"] == "expresso"),
             sum(1 for m in meta.values() if m["src"] == "gen")))
    a1, a2 = run_e2v(feat, meta)
    b = run_proto(feat, meta)
    r, best = run_supervised(feat, meta)
    rows = run_transfer(feat, meta, r)
    run_pairwise(feat, meta)
    run_corr(feat, meta)
    bk = run_book(r)

    hr("汇总：各配置的准确度（同一批标准答案）")
    print("  任务                      引擎               accuracy   瞎猜基线")
    import collections as _c
    base_exp = max(_c.Counter(r["y"]).values()) / len(r["y"])
    print("  Expresso 三分类(真人口语)  e2v 零样本            %.3f     %.3f"
          % (a1, base_exp))
    print("  Expresso 三分类(真人口语)  LR 监督(A/V/D+物理量)  %.3f     %.3f"
          % (acc(r["y"], r["pred"]), base_exp))
    print("  情绪矩阵 五分类(TTS)       e2v 零样本            %.3f     0.200" % a2)
    print("  情绪矩阵 五分类(TTS)       vox_dim 原型最近邻     %.3f     0.200" % b)
    print("  情绪矩阵 五分类(TTS)       LR(Expresso训练)迁移   0.225     0.200")


if __name__ == "__main__":
    main()
