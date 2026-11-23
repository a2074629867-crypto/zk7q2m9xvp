"""1-NN 声纹归属：拿每档 ref 单独当模板（不平均），取最相似的一档。

这就是"用之前的 REF 当检测源 + 对应情绪的情绪 REF"的落地形式：
  - 模板库 = 每档 ref 一条（角色 × 情绪）
  - 待测音频 → 与全部模板算余弦 → top1 即"最像哪一档情绪音色"
  - top1 角色 == 目标角色 且 top1 分数够高 → 音色归属通过

用法：
  python sv_1nn.py --list out/final_labels.jsonl --out out/final_sv1nn.json
  python sv_1nn.py --dir G:/_setup/castle_cues --out out/cues_sv1nn.json
"""
import os, sys, json, argparse
import numpy as np

sys.path.insert(0, "G:/_setup")
from sv_onnx import SV, load16

REF = "G:/_setup/castle_fr_ref"
ROLE_OF = {
    "1_charles_normal": "Charles", "2_charles_soft": "Charles",
    "3_charles_excited": "Charles", "4_charles_angry": "Charles",
    "5_hooper_loud": "Thomas", "6_hooper_calm": "Thomas",
    "6b_hooper_scold": "Thomas", "7_hooper_begging": "Thomas",
}
EMO_OF = {
    "1_charles_normal": "neutral", "2_charles_soft": "soft",
    "3_charles_excited": "excited", "4_charles_angry": "angry",
    "5_hooper_loud": "loud", "6_hooper_calm": "calm",
    "6b_hooper_scold": "scold", "7_hooper_begging": "begging",
}


def build(model="r34"):
    m = SV(model)
    T = {}
    for k in ROLE_OF:                     # 只取标准 8 档，忽略 _v2/_tight/HP_* 等变体
        p = os.path.join(REF, k + ".wav")
        if os.path.exists(p):
            T[k] = m.embed(p)
    return m, T


def classify(m, T, wav):
    e = m.embed(wav)
    sc = sorted(((k, float(np.dot(e, v))) for k, v in T.items()), key=lambda x: -x[1])
    k1, s1 = sc[0]
    k2, s2 = sc[1]
    role = ROLE_OF[k1]
    # 角色级 margin：目标角色最高分 - 另一角色最高分
    bestC = max(s for k, s in sc if ROLE_OF[k] == "Charles")
    bestT = max(s for k, s in sc if ROLE_OF[k] == "Thomas")
    return {
        "top1": k1, "sim1": round(s1, 4),
        "top2": k2, "sim2": round(s2, 4),
        "role": role, "emo": EMO_OF[k1],
        "margin_emo": round(s1 - s2, 4),
        "role_margin": round(bestC - bestT, 4),
        "confident": bool(s1 >= 0.30 and (s1 - s2) >= 0.05),
        "all": {k: round(s, 4) for k, s in sc},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", help="labels jsonl: {path, emotion, ...}")
    ap.add_argument("--dir", help="目录下所有 wav")
    ap.add_argument("--model", default="r34")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    m, T = build(a.model)
    print("模板 %d 档: %s" % (len(T), list(T)), flush=True)

    items = []
    if a.list:
        for line in open(a.list, encoding="utf-8"):
            d = json.loads(line)
            items.append((d["path"], d))
    elif a.dir:
        for f in sorted(os.listdir(a.dir)):
            if f.endswith(".wav"):
                items.append((os.path.join(a.dir, f), {"path": os.path.join(a.dir, f), "emotion": f[:-4]}))
    print("待测 %d 条" % len(items), flush=True)

    out = []
    for i, (p, meta) in enumerate(items):
        try:
            r = classify(m, T, p)
        except Exception as ex:
            print("FAIL", p, ex)
            continue
        r.update({k: v for k, v in meta.items() if k != "path"})
        r["path"] = p
        r["name"] = os.path.basename(p)
        out.append(r)
        if (i + 1) % 50 == 0:
            print("  %d/%d" % (i + 1, len(items)), flush=True)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    import collections
    c = collections.Counter(r["top1"] for r in out)
    rc = collections.Counter(r["role"] for r in out)
    conf = sum(1 for r in out if r["confident"])
    print("\n写 ->", a.out)
    print("角色分布:", dict(rc))
    print("置信条数: %d/%d (%.0f%%)" % (conf, len(out), 100 * conf / max(1, len(out))))
    print("top1 档分布:")
    for k, v in c.most_common():
        print("  %-20s %d" % (k, v))


if __name__ == "__main__":
    main()
