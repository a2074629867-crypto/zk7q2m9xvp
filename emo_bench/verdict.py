# -*- coding: utf-8 -*-
"""单句情绪到位度判定器。

用法：
  python verdict.py --wav x.wav --emotion 紧张
  python verdict.py --dir out/gen --emotion 激动反抗 --top 5   # 找出最不到位的 5 句
  python verdict.py --dir out/gen --emotion 色温               # 只看冷暖，不判档

五类情绪，每类一个判据（都来自真人正例分布标定，out/ref_stats.json）：
  兴奋      VAD: A×V         AUC 0.898
  激动反抗  VAD: D 支配度     AUC 0.886
  警惕      e2v disgusted    AUC 0.834
  紧张      VAD: A×(1−D)     AUC 0.812
  委屈      VAD: 1−A 低唤醒   AUC 0.779

两条连续轴（不判档，只看值）：
  色温      V    —— 高=暖，低=冷闷
  起伏      F0 跨度 —— 大=有活力，小=平

注意：没有「平静」这一类。实测「平静」和「普通说话（base）」是同一件事
（A 0.308 vs 0.502、F0 跨度 51 vs 92，差异来自 ref 不同而非标签），
它实际拆成「起伏」和「色温」两条轴。

判定档位按在真人正例分布中的分位：>=P25 到位 / P10..P25 勉强 / <P10 没演出来
（不要用负例阈值判档：不同判据方向不一致，两条阈值线的大小关系会翻转）

实测边界：
  - V 靠后期改不动（EQ/降速都试过，Δ<0.02）
  - 降速只能降 A 约 0.06
  - <emo> 标签是净负收益（40 次对照平均掉 18 分位），优先选天赋 ref
  - seed 重试对 V 无效（7 seed sd 仅 0.031，够不到提高 0.13 的需求）
"""
import argparse, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")

PRIMARY = {
    "激动反抗": ("vox", "d"),          # 支配度，AUC 0.886
    "兴奋": ("vox", "a_x_v"),          # A×V，AUC 0.898
    "紧张": ("vox", "a_x_nd"),         # A×(1−D)，AUC 0.812
    "委屈": ("vox", "neg_a"),          # 1−A 低唤醒，AUC 0.779
    "警惕": ("e2v", "厌恶/disgusted"),  # AUC 0.834
}

# 连续轴：只报值，不判档（真人基准见 AXIS_REF）
AXES = {
    "色温": ("vox", "v"),
    "起伏": ("phys", "f0_span"),
}
AXIS_REF = {"色温": (0.28, 0.64), "起伏": (60, 150)}  # (低参考, 高参考)，依次为冷/热、平/活


def vox_feat(sc, key):
    A = float(sc.get("arousal", 0)); V = float(sc.get("valence", 0)); D = float(sc.get("dominance", 0))
    return {"a": A, "v": V, "d": D, "neg_a": 1 - A, "neg_v": 1 - V, "neg_d": 1 - D,
            "a_x_v": A * V, "a_x_nd": A * (1 - D), "a_x_v_x_d": A * (1 - V) * D,
            "neg_a_neg_v_neg_d": (1 - A) * (1 - V) * (1 - D)}.get(key, 0.0)

def pct(v, dist):
    """v 落在真人正例分布的哪个分位（支持低于 P10 时为负）"""
    arr = np.array([dist["p10"], dist["p25"], dist["p50"], dist["p75"], dist["p90"]])
    qs = [.10, .25, .50, .75, .90]
    for i in range(1, len(arr)):
        if v <= arr[i]:
            f = (v - arr[i - 1]) / max(1e-9, arr[i] - arr[i - 1])
            return qs[i - 1] + f * (qs[i] - qs[i - 1])
    return .90 + min(.10, (v - arr[-1]) / max(1e-9, arr[-1]) * .3)


TIERS = [("到位", "threshold_fpr25", "p25@真人正例"),
         ("勉强", "threshold", "p10@真人正例")]


def load_stats():
    p = os.path.join(HERE, "out", "ref_stats.json")
    if not os.path.exists(p):
        sys.exit("缺 out/ref_stats.json，先跑 calib.py")
    return json.load(open(p, encoding="utf-8"))


def f0_med(path):
    import parselmouth
    snd = parselmouth.Sound(path).resample(16000)
    p = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=500)
    f = p.selected_array["frequency"]
    f = f[f > 0]
    return float(np.median(f)) if len(f) else 0.0


def e2v_score(paths, cache):
    import ser as S
    if "m" not in cache:
        cache["m"] = S.E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large")
    out = {}
    for p in paths:
        try:
            out[p] = cache["m"].score(p) or {}
        except Exception:
            out[p] = {}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--dir")
    ap.add_argument("--emotion", required=True, choices=list(PRIMARY))
    ap.add_argument("--top", type=int, default=0, help="只列最不到位的 N 句")
    a = ap.parse_args()

    files = [a.wav] if a.wav else sorted(
        os.path.join(a.dir, f) for f in os.listdir(a.dir) if f.lower().endswith(".wav"))
    if not files:
        sys.exit("没有输入文件")

    stats = load_stats()
    g = a.emotion
    src, key = PRIMARY[g]
    st = stats[g]["signals"].get("%s:%s" % (src, key))
    if not st:
        sys.exit("ref_stats 里没有 %s 的判据" % g)

    cache = {}
    if src == "e2v":
        sc = e2v_score(files, cache)
        vals = [(p, float(sc[p].get(key, 0.0))) for p in files]
    elif src == "vox":
        import ser as S
        m = S.VoxDim()
        vals = []
        for p in files:
            try:
                vals.append((p, vox_feat(m.score(p) or {}, key)))
            except Exception:
                vals.append((p, 0.0))
    else:
        vals = []
        for p in files:
            try:
                vals.append((p, f0_med(p) if key == "f0_med" else 0.0))
            except Exception:
                vals.append((p, 0.0))

    def tier(v):
        """按在真人正例分布中的分位判档（与报告口径一致）：
        >=P25 到位 / P10..P25 勉强 / <P10 没演出来"""
        q = pct(v, st["pos"])
        if q >= 0.25:
            return "到位", q
        if q >= 0.10:
            return "勉强", q
        return "没演出来", q

    rows = [(p, v) + tier(v) for p, v in vals]
    if a.top:
        rows.sort(key=lambda x: x[2])
        rows = rows[:a.top]

    print("情绪 %s  判据 %s:%s  AUC %.3f" % (g, src, key, st["auc"]))
    print("  真人正例分位：P10=%.4g  P25=%.4g  P50=%.4g\n" % (st["pos"]["p10"], st["pos"]["p25"], st["pos"]["p50"]))
    for p, v, t, q in rows:
        print("  %-28s %9.4g  %6.0f%%  %s" % (os.path.basename(p)[:28], v, 100 * q, t))

    if not a.top:
        cnt = {}
        for _, _, t in rows:
            cnt[t] = cnt.get(t, 0) + 1
        print("\n汇总:", cnt)


if __name__ == "__main__":
    main()
