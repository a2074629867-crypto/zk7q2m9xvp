# -*- coding: utf-8 -*-
"""把仍不足 9s 的参考组用**同角色**其它情绪的素材补齐。

为什么可以借
------------
音色是角色属性，不是情绪属性。dots.tts 只从参考里学音色/音质，
情绪由文本与韵律推。同角色的另一段录音，音色是对的，情绪略偏；
而**参考太短**（实测 4.9~5.7s）会让音色本身学不准，代价更大。

借用顺序（只借同角色）
--------------------
· soft/wronged/wary/normal 这类低唤醒 → 先借同角色 neutral/wronged/wary
· excited/angry/defiant/loud 这类高唤醒 → 先借同角色 angry/defiant/loud/excited
· 不够再按该角色其余情绪的长短继续借

只重写仍 `short=True` 的组，已达标的不动。输出仍写 `_ref9/`，索引 `_index_srt.json`。
"""
import io
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
from _build_ref9 import GAP, SR, trim_edges, load_any  # noqa: E402

ROOT = "G:/_setup"
LIB = os.path.join(ROOT, "_emo_refs_all.json")
IDX = os.path.join(ROOT, "_ref9", "_index_srt.json")
SRTFIX = os.path.join(ROOT, "_fix_ref9_text.py")

LOW = ("neutral", "soft", "wronged", "wary", "normal", "nervous", "calm")
HIGH = ("excited", "angry", "defiant", "loud", "scold", "begging")


def srt_text(path, byi):
    import re
    b = os.path.basename(path)
    m = re.match(r"^c(\d+)_[\d.]+_[\d.]+\.wav$", b)
    if m:
        i = int(m.group(1))
        if i in byi:
            return byi[i]
    return None


def main():
    target = float(sys.argv[1]) if len(sys.argv) > 1 else 9.0
    idx = json.load(io.open(IDX, encoding="utf-8"))
    lib = json.load(io.open(LIB, encoding="utf-8"))
    srt = json.load(io.open(os.path.join(ROOT, "castle_srt_cues.json"), encoding="utf-8"))
    byi = {x["i"]: x["text"] for x in srt}

    # 全素材池：role -> emo -> [{path,dur,text}]
    pool = {}
    for role, emos in lib.items():
        pool[role] = {}
        for emo, items in emos.items():
            rows = []
            for it in items:
                p = it.get("path") if isinstance(it, dict) else it
                if not p or not os.path.exists(p):
                    continue
                try:
                    d = sf.info(p).duration
                except Exception:
                    continue
                t = (it.get("text") if isinstance(it, dict) else "") or ""
                st = srt_text(p, byi)
                if st:
                    t = st
                rows.append({"path": p, "dur": d, "text": t})
            pool[role][emo] = rows

    for key, v in idx.items():
        if v["dur"] >= target - 0.15:
            continue
        role, _, emo = key.partition("_")
        order = list(LOW if emo in LOW else HIGH)
        order += [e for e in LOW + HIGH if e not in order]
        used = {p["path"] for p in v["parts"]}
        parts = list(v["parts"])
        # 用索引里实测的 dur 当基准：parts 的 dur 是原始片段长度，
        # trim_edges 之后每条会短 0.05~0.3s，拿原始值累加会把 8.06s 当成 9.0s
        # 从而「以为够了」直接跳过（Charles_wary 就这么被漏掉的）。
        total = v["dur"]
        added = []
        for e in order:
            if e == emo:
                continue
            if total >= target:
                break
            cands = [x for x in pool.get(role, {}).get(e, []) if x["path"] not in used]
            cands.sort(key=lambda x: -x["dur"])
            for c in cands:
                if total >= target:
                    break
                parts.append({"path": c["path"], "dur": round(c["dur"], 2),
                              "text": c["text"], "borrowed": e})
                used.add(c["path"])
                total += c["dur"] + GAP
                added.append((e, c["dur"]))
        if not added:
            print("%-22s %.2fs 无可借素材，保持原样" % (key, v["dur"]))
            continue

        chunks = []
        for p in parts:
            chunks.append(trim_edges(load_any(p["path"])))
            chunks.append(np.zeros(int(GAP * SR), dtype="float32"))
        y = np.concatenate(chunks[:-1])
        dst = os.path.join(ROOT, "_ref9", key + ".wav")
        sf.write(dst, y, SR, subtype="PCM_16")
        v["file"] = dst
        v["dur"] = round(len(y) / SR, 2)
        v["parts"] = parts
        v["text"] = " ".join(p["text"] for p in parts if p["text"]).strip()
        v["short"] = v["dur"] < target
        v["borrowed_from"] = sorted({a[0] for a in added})
        print("%-22s %.2fs → %.2fs  借 %s" % (
            key, total - sum(a[1] + GAP for a in added), v["dur"],
            ", ".join("%s(%.1fs)" % a for a in added)))

    json.dump(idx, io.open(IDX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    left = [(k, v["dur"]) for k, v in idx.items() if v.get("short")]
    print("\n仍不足 %.1fs: %d 组  %s" % (target, len(left), left))


if __name__ == "__main__":
    main()
