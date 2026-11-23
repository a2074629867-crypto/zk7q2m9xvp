"""从 1-NN 高置信结果重建干净的情绪 ref 库。

逻辑：
  1-NN 给出每条 cue 最像哪一档（角色+情绪），只保留 z>1.8 且 margin>0.3 的高置信结果
  再按 (角色, 情绪) 分组，每组取 top-N 条最长的（避开过短音频 embedding 不稳）
  人工语义校验：Charles 有妈妈、Thomas 有爸爸；"pardon à Charles" 必是 Thomas
"""
import json, os, sys, re
import numpy as np

CUE = "G:/_setup/out_sv/cues_znorm2.json"
IDX = "G:/_setup/castle_cues_index.json"
OUT = "G:/_setup/_emo_refs.json"

EMO_OF = {
    "1_charles_normal": "neutral", "2_charles_soft": "soft",
    "3_charles_excited": "excited", "4_charles_angry": "angry",
    "5_hooper_loud": "loud", "6_hooper_calm": "calm",
    "6b_hooper_scold": "scold", "7_hooper_begging": "begging",
}

# 语义反证规则：命中则强制改判/剔除
BAD_FOR = {
    "Charles": [r"à charles", r"pour charles", r"\bmon père\b", r"\bpapa\b"],
    "Thomas":  [r"\bma mère\b", r"\bmaman\b"],
}

MIN_DUR = 1.8
MIN_DUR_BY_EMO = {"soft": 1.15, "neutral": 1.5}
TOPN = 4


def main():
    rows = json.load(open(CUE, encoding="utf-8"))
    idx = {c["i"]: c for c in json.load(open(IDX, encoding="utf-8"))}

    cand = []
    for r in rows:
        if not (r["z1"] >= 1.8 and r["margin"] >= 0.3):
            continue
        ci = int(r["name"].split("_")[0][1:])
        c = idx.get(ci)
        if not c:
            continue
        dur = c["t1"] - c["t0"]
        _emo_pre = EMO_OF.get(r["top1"], "")
        if dur < MIN_DUR_BY_EMO.get(_emo_pre, MIN_DUR):
            continue
        # 排除双人对白与音效标注（混人/非语音）
        if c.get("multi") or "(" in c["text"] or ")" in c["text"]:
            continue
        role = r["role"]
        emo = EMO_OF.get(r["top1"])
        if not emo:
            continue
        txt = c["text"].lower()
        # 语义反证：如果内容违反角色设定，剔除
        if any(re.search(p, txt) for p in BAD_FOR[role]):
            continue
        cand.append({"path": c["path"], "role": role, "emo": emo,
                     "z": r["z1"], "margin": r["margin"], "dur": round(dur, 2),
                     "t0": c["t0"], "text": c["text"][:70]})

    # 同情绪内按 z 排序取 topN，同时优先时长 >= 2.5s
    lib = {}
    print("%-8s %-9s %-7s %-6s %-6s %s" % ("角色", "情绪", "z", "margin", "时长", "台词"))
    for role in ("Charles", "Thomas"):
        for emo in ("excited", "angry", "soft", "neutral", "loud", "calm", "scold", "begging"):
            g = [x for x in cand if x["role"] == role and x["emo"] == emo]
            if not g:
                continue
            g.sort(key=lambda x: (-(x["z"] + 0.5 * (x["dur"] >= 2.5)), -x["z"]))
            pick = g[:TOPN]
            lib.setdefault(role, {})[emo] = [
                {"path": p["path"], "name": "c%03d" % int(0), "z": p["z"], "text": p["text"]}
                for p in pick]
            for p in pick:
                print("%-8s %-9s %-7.2f %-6.2f %-6.2f %s" %
                      (role, emo, p["z"], p["margin"], p["dur"], p["text"][:44]))
            print()

    json.dump(lib, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(len(v) for e in lib.values() for v in e.values())
    print("写 -> %s  %d 档 %d 条" % (OUT, sum(len(e) for e in lib.values()), n))


if __name__ == "__main__":
    main()
