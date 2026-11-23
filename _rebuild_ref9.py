# -*- coding: utf-8 -*-
"""重建 `_ref9/` 全部参考：同情绪全用，不够再借同角色其它情绪（排除 c185）。

为什么要重写
------------
上一版 `_build_ref9.py` 有两个缺陷，实测都踩到了：

1. **按「原始时长」累加到 9s 就停**，可 `trim_edges()` 会把每段首尾死静音切掉
   0.05~0.3s，拼完实测比标称短。Charles_wary 本有 5.01+3.79+2.76=11.56s 可用，
   却只用前两段拼出 8.06s。
2. **借素材时不排除 `c185`**。c185 的 voiced-tilt 是 0.197（长参考的 4 倍），
   把它借进 Charles_nervous 后，生成结果 tilt 从 0.019 涨到 0.176、F0 257→324 ——
   正是用户否掉的「太亮、像喊」。所以 borrow 必须排除 c185。

规则
----
· 先用**同情绪**的全部素材（长句优先），按切边后的真实时长累加到 ≥9s 就停。
· 不够再借**同角色**其它情绪（低唤醒借低唤醒、高唤醒借高唤醒），逐条加入直到 ≥9s。
· 任何情况下都不使用 `BAN` 里的文件（c185 —— 用户否过的亮参考）。
· 参考文本一律用 SRT 原文（`castle_srt_cues.json`），查不到才退回原文本。
"""
import io
import json
import os
import re

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
LIB = os.path.join(ROOT, "_emo_refs_all.json")
SRT = os.path.join(ROOT, "castle_srt_cues.json")
OUT = os.path.join(ROOT, "_ref9")
SR = 48000
GAP = 0.20
TARGET = 9.0
BAN = ("c185_",)          # 用户否过的亮参考，任何组都不许用

LOW = ("neutral", "soft", "wronged", "wary", "normal", "nervous", "calm")
HIGH = ("excited", "angry", "defiant", "loud", "scold", "begging")


def load_any(p, sr=SR):
    y, s = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    if s != sr:
        g = np.gcd(int(s), int(sr))
        from scipy.signal import resample_poly
        y = resample_poly(y, sr // g, s // g).astype("float32")
    return y


def trim_edges(y, thr=0.012, pad=0.03):
    a = np.abs(y)
    idx = np.where(a > thr * (a.max() or 1))[0]
    if not len(idx):
        return y
    i0 = max(0, idx[0] - int(pad * SR))
    i1 = min(len(y), idx[-1] + int(pad * SR))
    return y[i0:i1]


def cue_i(path):
    b = os.path.basename(path)
    m = re.match(r"^c(\d+)_[\d.]+_[\d.]+\.wav$", b)
    return int(m.group(1)) if m else None


def clean(t):
    t = (t or "").replace("\u2019", "'").replace("\u2018", "'")
    t = re.sub(r"\s+", " ", t.replace("\u201c", "").replace("\u201d", "")).strip()
    return t


def main():
    banned = [b for b in BAN]
    lib = json.load(io.open(LIB, encoding="utf-8"))
    byi = {x["i"]: clean(x["text"]) for x in json.load(io.open(SRT, encoding="utf-8"))}

    # 素材池：预先切边、测真实时长（切边一次，后面反复用）
    pool = {}
    for role, emos in lib.items():
        pool[role] = {}
        for emo, items in emos.items():
            rows = []
            for it in items:
                p = it.get("path") if isinstance(it, dict) else it
                if not p or not os.path.exists(p):
                    continue
                if any(b in os.path.basename(p) for b in banned):
                    continue
                y = trim_edges(load_any(p))
                d = len(y) / SR
                if d < 0.3:
                    continue
                t = clean((it.get("text") if isinstance(it, dict) else "") or "")
                i = cue_i(p)
                if i is not None and i in byi:
                    t = byi[i]
                rows.append({"path": p, "y": y, "dur": round(d, 2), "text": t})
            pool[role][emo] = rows

    index = {}
    for role in sorted(pool):
        for emo in sorted(pool[role]):
            own = sorted(pool[role][emo], key=lambda x: -x["dur"])
            if not own:
                continue
            key = "%s_%s" % (role, emo)
            parts, used, total = [], set(), 0.0
            for it in own:
                if total >= TARGET:
                    break
                parts.append(it)
                used.add(it["path"])
                total += it["dur"] + GAP
            borrowed = []
            if total < TARGET:
                order = list(LOW if emo in LOW else HIGH)
                order += [e for e in LOW + HIGH if e not in order]
                for e in order:
                    if e == emo or total >= TARGET:
                        continue
                    for it in sorted(pool[role].get(e, []), key=lambda x: -x["dur"]):
                        if total >= TARGET:
                            break
                        if it["path"] in used:
                            continue
                        parts.append(it)
                        used.add(it["path"])
                        total += it["dur"] + GAP
                        borrowed.append(e)
            y = np.concatenate(
                [np.concatenate([p["y"], np.zeros(int(GAP * SR), dtype="float32")])
                 for p in parts])[:-int(GAP * SR)]
            dst = os.path.join(OUT, key + ".wav")
            sf.write(dst, y, SR, subtype="PCM_16")
            dur = round(len(y) / SR, 2)
            index[key] = {
                "file": dst, "dur": dur,
                "parts": [{"path": p["path"], "dur": p["dur"], "text": p["text"],
                           **({"borrowed": True} if p["path"] not in
                              {q["path"] for q in own} else {})} for p in parts],
                "text": " ".join(p["text"] for p in parts if p["text"]).strip(),
                "short": dur < TARGET - 0.15,
                "borrowed_from": sorted(set(borrowed)),
            }
            print("%-24s %5.2fs  %d 段%s" % (
                key, dur, len(parts),
                "  借 " + ",".join(sorted(set(borrowed))) if borrowed else ""))

    json.dump(index, io.open(os.path.join(OUT, "_index_srt.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sh = [(k, v["dur"]) for k, v in index.items() if v["short"]]
    import statistics
    print("\n%d 组，中位 %.2fs；不足 %.1fs 的 %d 组：%s" % (
        len(index), statistics.median([v["dur"] for v in index.values()]),
        TARGET, len(sh), sh))


if __name__ == "__main__":
    main()
