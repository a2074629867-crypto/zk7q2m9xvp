# -*- coding: utf-8 -*-
"""情绪判定闸门 —— 接回对白链路用。

两种工作模式：

  ① 有基线（推荐，生产链用这个）
     同一条台词、同一个 ref，先生成一版**无标签**的基线，
     再生成带标签版，比较两者的 A/V/D 差值 ⇒ 直接回答「标签起了多大作用」。
     阈值用「真人同情绪差的效应量」标定，不拍脑袋。

  ② 无基线（只有一条成品）
     用真人校准出来的绝对区间打软分，只能给「大概属于哪一类 + 有多可信」，
     不能断言标签有效——因为缺对照，任何绝对阈值都会被素材/语言/域偏移带走。

用法：
  python emo_gate.py --wav a.wav --baseline b.wav --label sad
  python emo_gate.py --wav a.wav --json
  python emo_gate.py --batch list.txt --baseline-dir out/gen
"""
import argparse, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

# ── 真人校准出来的参照（Expresso 745 条，见 analyze_real.py 输出）──
# 维度头在真人上的**合并组内 SD**（8 个 style 各自 SD 按自由度加权），
# 用来把 Δ 换算成效应量。
# ★ 2026-11-06 修正：原值是 A0.075 / V0.083 / D0.061，其中 valence 写成了
#   「更小的口径」，实际 pooled within = 0.130 —— 导致 valence 方向的效应量
#   被系统性高估 1.57 倍（之前报「V 掉 3σ」的条目实际约 1.9σ）。
#   区分两个 SD 很重要：全体 SD（A0.136/V0.171/D0.108）含**组间**差，
#   当分母会把「情绪本身差异」算进噪声，效应量被低估；这里必须用组内。
REAL_SD = {"arousal": 0.0729, "valence": 0.1301, "dominance": 0.0659}
# 真人各 style 的中位（16k、峰值归一后的口径）
REAL_MED = {
    "default":   dict(A=0.50, V=0.54, D=0.56),
    "happy":     dict(A=0.59, V=0.56, D=0.62),
    "laughing":  dict(A=0.68, V=0.73, D=0.64),
    "sad":       dict(A=0.32, V=0.40, D=0.39),
    "whisper":   dict(A=0.33, V=0.30, D=0.41),
    "confused":  dict(A=0.40, V=0.47, D=0.45),
}
# 标签期望方向（arousal, valence）
EXPECT = {
    "happy": (+1, +1), "sad": (-1, -1), "angry": (+1, -1),
    "afraid": (+1, -1), "disgusted": (+1, -1), "surprised": (+1, +0.2),
    "calm": (-1, +0.3), "melancholic": (-1, -1), "neutral": (0, 0),
}
# 判定门槛（效应量，单位=真人在中性语料上的组内 SD）
EFF_WEAK = 0.5      # 低于此视为「没起作用」
EFF_OK = 1.0        # 达到真人同情绪差的一半以上，实用上够

_E2V = None
_DIM = None


def _dim():
    global _DIM
    if _DIM is None:
        import ser as S
        _DIM = S.VoxDim()
    return _DIM


def _e2v():
    global _E2V
    if _E2V is None:
        import ser as S
        p = "G:/_setup/models/ms/iic/emotion2vec_plus_large"
        _E2V = S.E2V(p if os.path.isdir(p) else None)
    return _E2V


def dim_score(path):
    return _dim().score(path)


def e2v_score(path):
    try:
        return _e2v().score(path)
    except Exception:
        return None


def effect(delta, axis="arousal"):
    return delta / REAL_SD[axis]


def judge_one(wav, baseline=None, label=None, want_e2v=True):
    a = dim_score(wav)
    if a is None:
        return {"ok": False, "err": "audio too short or unreadable"}
    out = {"ok": True, "wav": wav, "dim": a}
    if want_e2v:
        out["e2v"] = e2v_score(wav)

    if baseline:
        b = dim_score(baseline)
        d = {k: round(a[k] - b[k], 4) for k in ("arousal", "valence", "dominance")}
        e = {k: round(effect(d[k], k), 3) for k in d}
        out["delta"] = d
        out["effect"] = e
        verdict = "unknown"
        if label and label in EXPECT:
            ea, ev = EXPECT[label]
            ok_a = (e["arousal"] * ea) >= EFF_WEAK if ea else None
            ok_v = (e["valence"] * ev) >= EFF_WEAK if ev else None
            verdict = "effective" if (ok_a and (ok_v is not False)) else (
                "weak" if (ok_a is False or ok_v is False) else "unknown")
            out["expect"] = dict(arousal=ea, valence=ev)
        out["verdict"] = verdict
    else:
        # 无基线：最近邻真人中位
        best, bd = None, 9
        for k, v in REAL_MED.items():
            dist = ((a["arousal"] - v["A"]) ** 2 + (a["valence"] - v["V"]) ** 2) ** 0.5
            if dist < bd:
                best, bd = k, dist
        out["nearest_real_style"] = best
        out["nearest_dist"] = round(bd, 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-e2v", action="store_true")
    args = ap.parse_args()

    r = judge_one(args.wav, args.baseline, args.label, not args.no_e2v)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    if not r["ok"]:
        print("失败：", r.get("err"))
        return
    d = r["dim"]
    print("A=%.3f  V=%.3f  D=%.3f" % (d["arousal"], d["valence"], d["dominance"]))
    if "delta" in r:
        e = r["effect"]
        print("相对基线：ΔA=%+.3f (%.2fσ)  ΔV=%+.3f (%.2fσ)  ΔD=%+.3f (%.2fσ)"
              % (r["delta"]["arousal"], e["arousal"], r["delta"]["valence"], e["valence"],
                 r["delta"]["dominance"], e["dominance"]))
        print("判定：", r.get("verdict"))
    elif "nearest_real_style" in r:
        print("最接近真人风格：%s（距离 %.2f）" % (r["nearest_real_style"], r["nearest_dist"]))
    if r.get("e2v"):
        top = sorted(((k, v) for k, v in r["e2v"].items() if not k.startswith("_")),
                     key=lambda x: -x[1])[:3]
        print("e2v：", "  ".join("%s %.2f" % (k, v) for k, v in top))


if __name__ == "__main__":
    main()
