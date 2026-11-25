# -*- coding: utf-8 -*-
"""_elong_batch.py —— 省略号 / 破折号处的「自然拖音」批量处理。

依据（本项目 10 月已解决、留过产物的做法，不是新发明）：
  · `ch123_l078_natural2.py`（2026-10-19）：只拉**元音**，用 rubberband 不用 OLA。
      OLA 拉 2.65 倍 → F0 抖动 4.0%→49.4%（电音）；rubberband tempo 0.30 → 抖动 4.0→4.5%，无损。
  · 用户规则：省略号 = 自然拖音，**只拉元音、辅音原速、末尾渐弱**。
  · 已明确作废的路线：dots.tts 词级 `<rate>` 标签在本机无效（11-21 与 11-24 两次实测，
    加标签只变短不变长）。所以只能走音频域。

两类分别处理：
  A 句中（标记后还有词）→ 拖长元音 + 把随后的长死寂收到 --gap
  B 句末（标记后即结束）→ 拖长元音 + 末尾渐弱（渐弱长度按新元音长度比例给）

用法：
  python _elong_batch.py --out G:/_setup/_elong
  python _elong_batch.py --ids c2_0368,c1_0043
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _align_gate as AG          # noqa: E402
from _elong_vowel import stretch, fade, voiced_run   # noqa: E402

SR = 48000
MARK = re.compile(r"(\.\.\.|\u2026|\u2014|\u2013|--|\s-\s)")
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")


def norm(t):
    return (t.replace("\u2019", "'").replace("\u2018", "'")
             .replace("\u201c", "").replace("\u201d", ""))


def targets(text):
    """返回 [(前词, 起始秒附近的词序, 是否句末)]。"""
    t = norm(text)
    out = []
    for m in MARK.finditer(t):
        head = t[:m.start()].rstrip(" ,'\"")
        ws = WORD.findall(head)
        if not ws:
            continue
        at_end = not WORD.search(t[m.end():])
        out.append((ws[-1], len(ws) - 1, at_end))
    return out


def words_of(proc, model, path, text):
    r = AG.align(proc, model, path, text)
    if not r:
        return []
    words, cur = [], []
    for tk in r["tokens"]:
        if tk["tok"] == "|":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(tk)
    if cur:
        words.append(cur)
    return [("".join(x["tok"] for x in w), w[0]["start"] * 0.02, w[-1]["end"] * 0.02)
            for w in words]


def norm_rms(y, sr):
    w = int(0.025 * sr)
    n = len(y) // w
    if n < 5:
        return y
    fr = np.sqrt((y[:n * w].reshape(n, w) ** 2).mean(1)) + 1e-12
    db = 20 * np.log10(fr)
    voiced = db[db > np.percentile(db, 97) - 20]
    if not len(voiced):
        return y
    y = y * (10 ** ((-24.0 - float(np.mean(voiced))) / 20.0))
    pk = float(np.abs(y).max())
    if pk > 0.97:
        y = y * (0.97 / pk)
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default="G:/_setup/_elong")
    ap.add_argument("--tempo", type=float, default=0.55, help="越小拉越长（0.55≈1.5x）")
    ap.add_argument("--gap", type=float, default=0.60, help="句中标记后停顿上限（秒）")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json",
                                               encoding="utf-8"))}
    ids = ([x.strip() for x in a.ids.split(",") if x.strip()] if a.ids
           else [r["id"] for r in rows.values() if MARK.search(norm(r["text"]))])
    print("待处理 %d 条" % len(ids))

    proc, model = AG.load_model()
    log = {}
    for rid in ids:
        src = "G:/_setup/_audio_ch123/out/%s.wav" % rid
        if not os.path.exists(src):
            print("%-9s 缺音频" % rid)
            continue
        text = rows[rid]["text"]
        tg = targets(text)
        if not tg:
            print("%-9s 无可用标记" % rid)
            continue
        y, sr = sf.read(src, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        ws = words_of(proc, model, src, text)
        if not ws:
            print("%-9s 对齐失败" % rid)
            continue

        # 只处理第一个标记（多标记条先证一条，避免连锁错）
        wname, order, at_end = tg[0]
        low = wname.lower()
        cand = [i for i, w in enumerate(ws) if w[0].lower() == low]
        if not cand:
            cand = [i for i, w in enumerate(ws) if w[0].lower().startswith(low[:3])]
        if not cand:
            print("%-9s 对齐词表里找不到 %s | %s" % (rid, wname,
                                                    [w[0] for w in ws][:8]))
            continue
        idx = cand[0]
        wn, t0, t1 = ws[idx]
        nxt = ws[idx + 1][1] if idx + 1 < len(ws) else None

        vr = voiced_run(y, sr, t0, t1)
        if not vr:
            print("%-9s 词内无 >=50ms voiced" % rid)
            continue
        v0, v1 = vr
        i0, i1 = int(v0 * sr), int(v1 * sr)
        head, vowel, tail = y[:i0], y[i0:i1], y[i1:]
        vz = stretch(vowel, sr, a.tempo, tag=rid)
        # 句末：渐弱拉长；句中：短渐弱保连贯
        vz = fade(vz, sr, 6, 60 if at_end else 16, out_gain=0.55 if at_end else 0.78)
        out = np.concatenate([head, vz, tail])

        rec = dict(id=rid, who=rows[rid]["who"], word=wn, at_end=at_end,
                   vowel_ms=round((v1 - v0) * 1000, 1),
                   new_ms=round(len(vz) / sr * 1000, 1))
        if not at_end and nxt:
            shift = (len(vz) - len(vowel)) / sr
            vent = t1 + shift
            nstart = nxt + shift
            cur_gap = nstart - vent
            rec["gap_before"] = round(cur_gap, 2)
            if cur_gap > a.gap + 0.05:
                keep_f = int(0.30 * sr)
                keep_b = int(a.gap * sr) - keep_f
                a0 = int(vent * sr)
                a1 = int(nstart * sr)
                if a1 - keep_b > a0 + keep_f:
                    out = np.concatenate([out[:a0 + keep_f], out[a1 - keep_b:]])
                    rec["gap_after"] = round(a.gap, 2)
        out = norm_rms(out, sr)
        rec["dur"] = round(len(out) / sr, 2)
        rec["peak"] = round(float(np.abs(out).max()), 3)
        log[rid] = rec
        if not a.dry:
            sf.write(os.path.join(a.out, "%s_elong.wav" % rid), out, sr, subtype="PCM_24")
        print("%-9s %-5s %-8s 元音 %5.0f→%5.0fms  %s  总 %5.2fs"
              % (rid, rows[rid]["who"][:5], wn, rec["vowel_ms"], rec["new_ms"],
                 ("停顿 %.2f→%.2f" % (rec.get("gap_before"), rec.get("gap_after", 0)))
                 if rec.get("gap_before") else ("句末渐弱" if at_end else ""),
                 rec["dur"]))

    if not a.dry:
        p = os.path.join(a.out, "_elong_log.json")
        old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        old.update(log)
        json.dump(old, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("-> %s (%d 条)" % (p, len(old)))


if __name__ == "__main__":
    main()
