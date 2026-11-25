# -*- coding: utf-8 -*-
"""韵律判据 v2：词与词之间的 F0 四个量（对应 PROSODY_ACTION.md §5）

只用 F0。不含时长、不含停顿、不含语速（§1 的 R1 / R2）。
所有量都是相对量：相对句内中位、相对相邻峰 ⇒ 免疫音域与风格（L4）。

输入：`_accent_fix_*.jsonl`（双估计器版，必须含 cons / cons90 / ok）
输出：`_prosody_rel.json`

四个量
  S 峰间斜率   S_i = (hi[P_i+1] − hi[P_i]) / (t[P_i+1] − t[P_i])   st/s
  r 下阶步长   r_i = hi[P_i+1] − hi[P_i]                            st
  F 末位额外降 F   = r_last − median(其余 r)                         st
  J 局部突变   J   = max_i abs(hi[P_i+1] − hi[P_i])                 st

命中（布尔清单，不打分）
  J_HIT   J > J_MAX(10st)  ⇒ 人声做不到（US7286986），耳朵会误读成重音
  FLAT    句内 r 的 IQR < 1st 或 n_peaks < 2 ⇒ 只标「无法判定」，不判错

用法
  G:/Python310/python.exe -u _prosody_rel.py \
      --a _accent_fix_old.jsonl --b _accent_fix_new.jsonl --out _prosody_rel.json
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _speedlib  # noqa: E402  复用同一套帧/阈值口径

ROOT = r"G:/_setup"

CONTENT = {"NOUN", "VERB", "ADJ", "ADV", "NUM", "PROPN"}
J_MAX = 10.0        # 相邻词 F0 落差上限（st）；来自 US7286986 的"人声做不到"
PEAK_PCT = 50.0     # 峰候选门槛：prom(cons) ≥ 句内 p50（原 p70 每句只出 2 个峰，掩膜后无法判）
PAUSE_MIN = 0.45    # 跨过 ≥0.45s 停顿的词对不算「相邻」，掩膜用（R2：只排除不评分）


def pause_spans(y, sr, min_len=PAUSE_MIN):
    """返回 [(a, b)] 秒，低能量段（阈值口径与 _speedlib 一致）。"""
    db, h = _speedlib._frames_db(y, sr)
    hop = h / float(sr)
    thr = max(-60.0, float(np.percentile(db, 90)) - _speedlib.DROP_DB)
    low = db < thr
    out, i, n = [], 0, len(low)
    while i < n:
        if low[i]:
            j = i
            while j < n and low[j]:
                j += 1
            if (j - i) * hop >= min_len:
                out.append((i * hop, j * hop))
            i = j
        else:
            i += 1
    return out


def find_peaks(ws):
    """ws: 已过滤出 cons90 有值的内容词，按时间排序。返回峰下标列表。"""
    if not ws:
        return []
    vals = np.array([w["cons90"] for w in ws], dtype=float)
    thr = float(np.percentile(vals, PEAK_PCT))
    idx = []
    for i, w in enumerate(ws):
        if w["cons"] is None or w["cons"] < thr:
            continue
        left = vals[i - 1] if i > 0 else -1e9
        right = vals[i + 1] if i + 1 < len(vals) else -1e9
        if vals[i] >= left and vals[i] >= right:
            idx.append(i)
    if not idx:
        idx = [int(np.argmax(vals))]
    # 末峰强制保留（final lowering 需要它）
    last = len(ws) - 1
    if last not in idx and ws[last]["cons"] is not None:
        idx.append(last)
    return sorted(set(idx))


def analyse(rec, wav):
    # 峰：只取内容词（判「该不该重」需要语法角色）
    ws = [w for w in rec["words"]
          if w.get("cons90") is not None and w.get("pos") in CONTENT]
    ws.sort(key=lambda w: w["t0"])
    # J：取全部有 cons90 的词（含功能词）—— 突变落在 the/of/much 上正是要抓的那种错
    allw = [w for w in rec["words"] if w.get("cons90") is not None]
    allw.sort(key=lambda w: w["t0"])

    def note(msg, **kw):
        d = dict(id=rec["id"], n_peaks=len(ws), note=msg,
                 peaks=[dict(w=p["w"], hi=p["cons90"], t=round(p["t0"], 2)) for p in ws])
        d.update(kw)
        return d

    if len(allw) < 3:
        return note("词不足")

    # 停顿掩膜（只排除，不参与评分）
    try:
        y, sr = sf.read(wav, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        spans = pause_spans(y, sr)
    except Exception:  # noqa: BLE001
        spans = []

    def crossed(t0, t1):
        return any(a < t1 and b > t0 for a, b in spans)

    # ---- J：相邻词（全词性）----
    jw = []
    for a, b in zip(allw, allw[1:]):
        m = crossed(a["t1"], b["t0"])
        jw.append(dict(wa=a["w"], wb=b["w"], pos_a=a.get("pos"), pos_b=b.get("pos"),
                       d=round(b["cons90"] - a["cons90"], 2), masked=m))
    jl = [p for p in jw if not p["masked"]]
    J = round(max((abs(p["d"]) for p in jl), default=None), 2) if jl else None

    if not jl:
        return note("词对全部跨停顿边界", J=None, n_pairs=0, pairs=[], jpairs=jw)

    pk = [ws[i] for i in find_peaks(ws)] if len(ws) >= 2 else []
    if len(pk) < 2:
        return note("峰不足（只有 J 可用）", J=J, n_pairs=len(jl), jpairs=jw,
                    pairs=[dict(wa=p["wa"], wb=p["wb"], d=p["d"]) for p in jl])

    pairs = []
    for i in range(len(pk) - 1):
        a, b = pk[i], pk[i + 1]
        ta = 0.5 * (a["t0"] + a["t1"])
        tb = 0.5 * (b["t0"] + b["t1"])
        d = b["cons90"] - a["cons90"]
        pairs.append(dict(i=i, wa=a["w"], wb=b["w"], hi_a=a["cons90"], hi_b=b["cons90"],
                          dt=round(tb - ta, 3), d=round(d, 2),
                          slope=round(d / max(1e-3, tb - ta), 2),
                          masked=crossed(a["t1"], b["t0"])))

    live = [p for p in pairs if not p["masked"]]
    ds = [p["d"] for p in live]
    r_iqr = float(np.percentile(ds, 75) - np.percentile(ds, 25)) if len(ds) > 1 else 0.0
    F = None
    if len(ds) >= 3:
        F = round(ds[-1] - float(np.median(ds[:-1])), 2)
    elif len(ds) == 2:
        F = round(ds[-1] - ds[0], 2)

    hits = []
    if J is not None and J > J_MAX:
        worst = max(jl, key=lambda p: abs(p["d"]))
        hits.append(dict(rule="J", val=J, at="%s→%s" % (worst["wa"], worst["wb"]),
                         pos=[worst["pos_a"], worst["pos_b"]]))
    flat = (len(ds) < 2) or (r_iqr < 1.0)

    return dict(id=rec["id"], n_peaks=len(pk), n_pairs=len(jl), jpairs=jw,
                J=J, F=F, r_iqr=round(r_iqr, 2),
                s_med=(round(float(np.median([p["slope"] for p in live])), 2) if live else None),
                hits=hits, flat=bool(flat),
                peaks=[dict(w=p["w"], hi=p["cons90"], t=round(p["t0"], 2), pos=p["pos"])
                       for p in pk],
                pairs=live)


def load(p):
    out = {}
    for ln in open(p, encoding="utf-8"):
        if ln.strip():
            r = json.loads(ln)
            out[r["id"]] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="_accent_fix_old.jsonl")
    ap.add_argument("--b", default="_accent_fix_new.jsonl")
    ap.add_argument("--da", default="_audio_ch123/out")
    ap.add_argument("--db", default="_regen_final")
    ap.add_argument("--out", default="_prosody_rel.json")
    a = ap.parse_args()

    A, B = load(a.a), load(a.b)
    common = sorted(set(A) & set(B))
    print("两版共有 %d 句（A %d / B %d）" % (len(common), len(A), len(B)), flush=True)

    res = {"J_MAX": J_MAX, "old": {}, "new": {}}
    for tag, D, dd in (("old", A, a.da), ("new", B, a.db)):
        for sid in common:
            wav = os.path.join(ROOT, dd, sid + ".wav")
            res[tag][sid] = analyse(D[sid], wav)
        jh = [r for r in res[tag].values() if r.get("hits")]
        fl = [r for r in res[tag].values() if r.get("flat")]
        nj = [r["J"] for r in res[tag].values() if r.get("J") is not None]
        print("%s: 可判 %d 句 | J>%.0f 命中 %d | 无法判定(平/单峰) %d | J 中位 %.1f p90 %.1f"
              % (tag, len(nj), J_MAX, len(jh), len(fl),
                 float(np.median(nj)) if nj else 0,
                 float(np.percentile(nj, 90)) if nj else 0), flush=True)

    both = [s for s in common
            if res["old"][s].get("hits") and res["new"][s].get("hits")]
    only_o = [s for s in common
              if res["old"][s].get("hits") and not res["new"][s].get("hits")]
    only_n = [s for s in common
              if res["new"][s].get("hits") and not res["old"][s].get("hits")]
    res["summary"] = dict(common=len(common), both=len(both),
                          only_old=len(only_o), only_new=len(only_n),
                          both_ids=both, only_old_ids=only_o, only_new_ids=only_n)
    print("J 命中：两版都中 %d | 只旧版 %d | 只新版 %d" % (len(both), len(only_o), len(only_n)))

    # ---- 配对比较：只在「两版都没被掩膜」的同一批词对上取 max ----
    # 必须这么做：J 是 max，样本越多 max 越大。旧版语速慢 ⇒ 0.45s 绝对阈值把更多词间空隙
    # 误判成停顿 ⇒ 活下来的词对少 ⇒ J 天然偏小。不配对就是拿两个不同样本量比最大值。
    paired = {}
    for sid in common:
        A_, B_ = res["old"][sid], res["new"][sid]
        ka = {(p["wa"], p["wb"]): p["d"] for p in A_.get("jpairs") or [] if not p["masked"]}
        kb = {(p["wa"], p["wb"]): p["d"] for p in B_.get("jpairs") or [] if not p["masked"]}
        keys = [k for k in ka if k in kb]
        if not keys:
            continue
        ja = max(abs(ka[k]) for k in keys)
        jb = max(abs(kb[k]) for k in keys)
        paired[sid] = dict(n=len(keys), J_old=round(ja, 2), J_new=round(jb, 2),
                           delta=round(jb - ja, 2),
                           better=("new" if jb < ja - 0.5 else
                                   ("old" if ja < jb - 0.5 else "tie")))
    res["paired"] = paired
    if paired:
        from collections import Counter
        c = Counter(v["better"] for v in paired.values())
        hop = [s for s, v in paired.items() if v["J_old"] > J_MAX]
        hnp = [s for s, v in paired.items() if v["J_new"] > J_MAX]
        print("配对可比 %d 句（每句只用两版共有且都未被掩膜的词对）" % len(paired))
        print("  J 更小：new %d / old %d / 平 %d"
              % (c["new"], c["old"], c["tie"]))
        print("  J>%.0f 命中：old %d 句 / new %d 句（同一批词对口径）"
              % (J_MAX, len(hop), len(hnp)))
        dd = [v["delta"] for v in paired.values()]
        print("  ΔJ（new−old）中位 %+.2f，p10 %+.2f，p90 %+.2f"
              % (float(np.median(dd)), float(np.percentile(dd, 10)),
                 float(np.percentile(dd, 90))))

    for sid in ("c2_0191",):
        if sid in paired:
            v = paired[sid]
            print("  c2_0191 配对：词对 %d | J old %.2f → new %.2f（%s）"
                  % (v["n"], v["J_old"], v["J_new"], v["better"]))

    outp = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    json.dump(res, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已写 %s" % outp)


if __name__ == "__main__":
    main()
