# -*- coding: utf-8 -*-
"""_pool_rank.py —— 候选池统一评级（用户口径：语调要有生气、咬字要清楚）

★ 2026-11-25 05:3x 用户纠正了评级口径：
  「我说的 Free 更好，它是有点声调的，就是最后来说它不是很平的那种 Free，
    它更像是普通人说话，就是说有生气的说话，有表演性质的更好一点。」

所以我上一版「rough 越低越好」是错的 —— rough 低到极点是**平**（单调、像机器）。
正确的三件事：

1. **词内音域 rng**（半音）：一个词内部 F0 的最高−最低。太小学究是平。
   实测 c2_0368 的 `free`：s45 只有 1.7st（94% 帧在 ±1st 内 = 平，用户没选），
   s44 是 8.5st + 句末下滑 −7.3st（用户选的「有表演性质」）。
2. **句末/内容词的滑移 glide**（半音）：自然语气在短语末会落下来。
3. **误重音 spike**：功能词（i/the/it/all/them/its…）突然比左右高 ≥4st。
   c2_0368 的 s43 第二处 think +11.9st 就是喊，s42 两处 think +5.3/+5.7 也刺耳。

咬字（本脚本只测目标词的词尾塞音）：
  `_burst.burst()` 给 hf_jump / closure_db。`can't` 的 /t/ 是「闭合 + 高频释放」，
  读成 `cam` 时尾音会变成一段低频鼻音、没有释放。

输出：按「先过技术闸 → 再按表达力排序」的表格，人工可读。
"""
import argparse
import glob
import json
import os
import sys

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np          # noqa: E402
import soundfile as sf      # noqa: E402

sys.path.insert(0, "G:/_setup")
import _align_gate as AG    # noqa: E402
import _burst as BU         # noqa: E402
import _intonation as IN    # noqa: E402
import _pause_gap as PG     # noqa: E402

FUNC = set("""i it its it's the a an and or but so all them that this these those
of to in on at for with you your my me he she we they was were is been are
do don't didn't can't can could would should will just not no yes well oh""".split())


def word_shape(path, a, b):
    """词内音高形状：rng（半音跨度）、glide（首尾差）、flat（±1st 帧占比）。"""
    import parselmouth
    f = parselmouth.Sound(path).to_pitch(0.01, 75, 600).selected_array["frequency"]
    i0, i1 = int(a / 0.01), max(int(b / 0.01), int(a / 0.01) + 1)
    v = f[i0:i1]
    v = v[v > 0]
    if len(v) < 3:
        return None
    med = float(np.median(v))
    st = 12.0 * np.log2(v / med)
    k = max(1, len(st) // 4)
    return dict(n=int(len(v)),
                rng=round(float(st.max() - st.min()), 1),
                glide=round(float(np.mean(st[-k:]) - np.mean(st[:k])), 1),
                flat=round(float((np.abs(st) < 1.0).mean()), 2))


def rank(rid, pools, word, proc, model, base_dir="G:/_setup/_audio_ch123/out"):
    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}
    text = PG.clean(rows[rid]["text"])
    # ★ 词数不能按 split() 算：`I – I can ...` 里的破折号会被当第 2 个「词」，
    #   于是 9 个真词被算成 10，全部候选都被标「词数不符」。只数字母词。
    import re as _re
    exp_n = len(_re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text))
    base = os.path.join(base_dir, rid + ".wav")
    b_dur = None
    if os.path.exists(base):
        y, sr = sf.read(base, dtype="float64")
        b_dur = len(y) / sr if y.ndim == 1 else len(y) / sr

    cands = [("now", base)]
    for d in pools:
        for p in sorted(glob.glob(os.path.join(d, rid, "s*.wav")),
                        key=lambda x: int(os.path.basename(x)[1:-4])):
            cands.append((os.path.basename(p)[:-4], p))

    out = []
    for tag, p in cands:
        if not os.path.exists(p):
            continue
        r = IN.analyse(p, text, proc, model)
        if not r:
            out.append(dict(tag=tag, ok=False, why="对齐失败"))
            continue
        y, sr = sf.read(p, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        dur = len(y) / sr
        # 词内表达力（排除无法测的词）
        shapes = [word_shape(p, a, b) for _, a, b in r["spans"]]
        shapes = [s for s in shapes if s]
        mean_rng = round(float(np.mean([s["rng"] for s in shapes])), 2) if shapes else 0.0
        flat_frac = round(float(np.mean([s["flat"] for s in shapes])), 2) if shapes else 1.0
        # 功能词误重音
        bad_spike = [s for s in r["spike"] if s[0].split()[0].lower() in FUNC]
        # 目标词咬字
        tgt = [x for x in r["spans"] if x[0].startswith(word)]
        bst = BU.burst(p, tgt[0][1], tgt[0][2]) if tgt else None
        out.append(dict(tag=tag, ok=(len(r["spans"]) == exp_n),
                        spans=r["spans"],
                        nword=len(r["spans"]), dur=round(dur, 2),
                        dr=round(dur / b_dur, 2) if b_dur else None,
                        rough=r["rough"], range_st=r["range_st"],
                        mean_rng=mean_rng, flat_frac=flat_frac,
                        spikes=len(r["spike"]), bad_spike=len(bad_spike),
                        burst=bst))
    return text, exp_n, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="c3_0853")
    ap.add_argument("--word", default="cant")
    ap.add_argument("--pools", default="G:/_setup/_seedpick2,G:/_setup/_seedpick")
    ap.add_argument("--json", default="G:/_setup/_pool_rank.json")
    a = ap.parse_args()

    proc, model = AG.load_model()
    text, exp_n, rows = rank(a.id, [x for x in a.pools.split(",") if x], a.word, proc, model)
    print("== %s  %s" % (a.id, text))
    print("%-6s %-4s %5s %6s %6s %6s %6s %5s %5s %5s %5s %s" % (
        "take", "词数", "dur", "x基线", "rough", "音域", "词内rng", "平帧%", "突起", "误重", "尾rng", "咬字(hfJump/closure)"))
    for r in rows:
        if not r.get("ok") and "why" in r:
            print("%-6s %s" % (r["tag"], r["why"]))
            continue
        b = r["burst"]
        print("%-6s %4d %5.2f %6.2f %6.2f %6.1f %6.2f %5.0f%% %5d %5d %5d  %s" % (
            r["tag"], r["nword"], r["dur"], r["dr"] or 0, r["rough"], r["range_st"],
            r["mean_rng"], 100 * r["flat_frac"], r["spikes"], r["bad_spike"],
            b["dur"] if b else 0,
            ("hfJump %5.2f  closure %4.1f  hfTail %.3f" % (b["hf_jump"], b["closure_db"], b["hf_tail"])) if b else "-"))
        if not r["ok"]:
            print("       ↑ 词数不符（应 %d）" % exp_n)
    json.dump(dict(id=a.id, text=text, rows=rows), open(a.json, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("->", a.json)


if __name__ == "__main__":
    sys.exit(main())
