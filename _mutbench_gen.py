# -*- coding: utf-8 -*-
"""_mutbench_gen.py —— 造「句内音色突变」评测基准（有 ground truth）。

为什么必须造基准：现有 `_segcheck_dlg.py` 只跑出了「11 条候选」，
但没有 ground truth 就没法回答「换一个检测器是更准还是更不准」。
本脚本把「突变」变成可控变量，才能算 TPR / FPR / 定位误差。

四组样本（全部 48k 单声道，取自 `_audio_ch123/out`，已 −24dBFS 归一）：
  POS_hard  两个不同角色硬拼接，**拼接处不留静音** —— 语流中换人的真场景
  POS_soft  同上但拼接处插 0.30s 静音 —— 停顿处换人，现有工具唯一能切出来的情形
  NEG_emo   同一角色两个不同句子（尽量不同情绪档）硬拼接 —— 同一人，不许判突变
  NEG_real  真实整条（≥6s，排除已知有突变的 c2_0217）

ground truth：`cut` = 突变时刻（秒）；NEG 组 `cut` = None。

用法：
  G:/Python310/python.exe _mutbench_gen.py
"""
import json, os, random, collections
import numpy as np
import soundfile as sf

SRC = "G:/_setup/_audio_ch123/out"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
OUT = "G:/_setup/_mutbench"
TARGET = (6.5, 9.5)     # 目标总时长
RNG = random.Random(20261112)


def load(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    assert sr == 48000, (p, sr)
    return y


def main():
    os.makedirs(os.path.join(OUT, "wav"), exist_ok=True)
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            o = json.loads(l)
            plan[o["id"]] = o

    pool = collections.defaultdict(list)
    durs = {}
    for i, o in plan.items():
        f = os.path.join(SRC, i + ".wav")
        if not os.path.exists(f):
            continue
        d = sf.info(f).duration
        durs[i] = d
        if d >= 3.5:
            pool[o["who"]].append(i)
    for w in pool:
        pool[w].sort()

    idx = []
    n = 0

    def emit(kind, ids, y, cut, extra):
        nonlocal n
        n += 1
        sid = "%s_%03d" % (kind, n)
        p = os.path.join(OUT, "wav", sid + ".wav")
        sf.write(p, np.clip(y, -1, 1), 48000, subtype="PCM_16")
        idx.append({"sid": sid, "kind": kind, "src": ids, "cut": cut,
                    "dur": round(len(y) / 48000, 3), **extra})

    # ---- POS_hard / POS_soft：换人 ----
    pairs = [("Thomas", "Charles"), ("Charles", "Joseph"),
             ("Joseph", "Thomas"), ("Helena", "Thomas")]
    for kind in ("POS_hard", "POS_soft"):
        for a_who, b_who in pairs:
            for _ in range(15):
                a = RNG.choice(pool[a_who])
                b = RNG.choice(pool[b_who])
                if a == b:
                    continue
                ya, yb = load(os.path.join(SRC, a + ".wav")), load(os.path.join(SRC, b + ".wav"))
                # 前半长度：保证总长落在 TARGET，且突变点不在首尾 25%
                tA = RNG.uniform(max(2.6, TARGET[0] * 0.35), min(len(ya) / 48000, TARGET[1] * 0.6))
                tB = RNG.uniform(2.6, min(len(yb) / 48000, TARGET[1] - tA))
                tA, tB = round(tA, 3), round(tB, 3)
                head = ya[:int(tA * 48000)]
                tail = yb[:int(tB * 48000)]
                gap = np.zeros(int(0.30 * 48000), dtype=np.float32) if kind == "POS_soft" else np.zeros(0, dtype=np.float32)
                y = np.concatenate([head, gap, tail])
                emit(kind, [a, b], y, round(tA + len(gap) / 48000, 3),
                     {"who_a": a_who, "who_b": b_who, "emo_a": plan[a]["emo"], "emo_b": plan[b]["emo"]})

    # ---- NEG_emo：同一人，不同句 ----
    for who in ("Thomas", "Charles", "Joseph"):
        ids = pool[who]
        tries = 0
        made = 0
        while made < 13 and tries < 200:
            tries += 1
            a, b = RNG.sample(ids, 2)
            if plan[a]["emo"] == plan[b]["emo"] and RNG.random() < 0.7:
                continue
            ya, yb = load(os.path.join(SRC, a + ".wav")), load(os.path.join(SRC, b + ".wav"))
            tA = RNG.uniform(2.6, min(len(ya) / 48000, TARGET[1] * 0.6))
            tB = RNG.uniform(2.6, min(len(yb) / 48000, TARGET[1] - tA))
            tA, tB = round(tA, 3), round(tB, 3)
            y = np.concatenate([ya[:int(tA * 48000)], yb[:int(tB * 48000)]])
            emit("NEG_emo", [a, b], y, None,
                 {"who_a": who, "who_b": who, "emo_a": plan[a]["emo"], "emo_b": plan[b]["emo"]})
            made += 1

    # ---- NEG_real：真实整条（不含拼接） ----
    long_ids = [i for i, d in durs.items() if d >= 6.0 and i != "c2_0217"]
    for i in RNG.sample(sorted(long_ids), min(30, len(long_ids))):
        y = load(os.path.join(SRC, i + ".wav"))
        lim = int(min(len(y), TARGET[1] * 48000))
        y = y[:lim]
        emit("NEG_real", [i], y, None,
             {"who_a": plan[i]["who"], "who_b": None, "emo_a": plan[i]["emo"], "emo_b": None})

    json.dump(idx, open(os.path.join(OUT, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("写入 %d 条 -> %s" % (len(idx), OUT))
    print(collections.Counter(x["kind"] for x in idx))
    for k in ("POS_hard", "POS_soft", "NEG_emo", "NEG_real"):
        s = [x for x in idx if x["kind"] == k]
        print("  %-9s n=%3d  dur %.1f~%.1fs  %s" % (
            k, len(s), min(x["dur"] for x in s), max(x["dur"] for x in s),
            ("cut %.1f~%.1fs" % (min(x["cut"] for x in s), max(x["cut"] for x in s))) if s[0]["cut"] else ""))


if __name__ == "__main__":
    main()
