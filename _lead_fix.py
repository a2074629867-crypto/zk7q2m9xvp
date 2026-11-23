# -*- coding: utf-8 -*-
"""裁掉「开头多念了参考片段原文」（LEAD_REF）。

为什么必须现在做
----------------
`_align_deliver.json` 里存了 wav2vec2 的**逐字符时间戳**，把 gold 与解码词做
序列对齐后可以直接看出：正文之前多出来几个词、它们落在哪一帧。

实测本轮交付里 5 条（`c2_0445`、`c1_0046`、`c1_0149`、`c2_0430`、`c2_0404`）
开头多念了参考片段的原文（Joseph 的参考是 "My father was a reserved man"），
而 Parakeet / whisper 会把这种「多念」当成上下文正常读过去，报覆盖率 1.00，
所以七闸和双 ASR 全都查不出。11-12 那份 `_wl_flags_all.jsonl` 记过 60 条同类，
一直没人处理。

做法：对齐 → 找正文第一个稳定匹配块 → 把它之前的词整段切掉 → 20ms 淡入。
只裁开头，不动中间；裁完重新做 w2v 复检，插入词数必须归零。
"""
import argparse
import difflib
import glob
import io
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _pick52 as PK


def word_spans(row):
    """把 align 行里的 token 序列拼成词 + 起止帧。

    用 `greedy_spans`（贪心解码路径的字符时间戳），不是 `tokens` ——
    后者是 forced_align 对 gold 文本的结果，只含 gold 里有的字符，
    天然看不到「多念的词」。
    """
    words, cur = [], []
    for t in row.get("greedy_spans") or row.get("tokens") or []:
        if t["tok"] == "|":
            if cur:
                words.append({"w": "".join(x["tok"] for x in cur),
                              "s": cur[0]["start"], "e": cur[-1]["end"]})
                cur = []
        else:
            cur.append(t)
    if cur:
        words.append({"w": "".join(x["tok"] for x in cur),
                      "s": cur[0]["start"], "e": cur[-1]["end"]})
    return words


def match_ratio(gold, hyp, k, window=None):
    """从 hyp 的第 k 个词开始，按顺序能对上多少 gold 词（模糊匹配，且顺序单调）。"""
    j = k
    hit = 0
    for g in gold:
        found = False
        while j < len(hyp):
            if PK.words_match(g, hyp[j]):
                hit += 1
                j += 1
                found = True
                break
            j += 1
            if window and j - k > window:
                break
        if not found and window and j - k > window:
            break
    return hit / max(1, len(gold))


def lead_len(gold, hyp_words):
    """返回「正文开始前多出来的词数」。

    判据不是「第一个匹配块在哪」—— 那会被 wav2vec2 的拼写偏差骗到
    （THAT'S 解码成 HAT，TERE'S 解码成 RE'S，匹配块从第 3 个词才开始，
    于是把正文头部当成 lead，实测 46 条里绝大部分是这种假警）。
    改成：从 hyp 第 k 个词起按顺序能覆盖多少 gold，取覆盖 ≥0.85 且最小的 k。
    """
    h = []
    for w in hyp_words:
        t = PK.norm_words(w["w"])
        h.append(t[0] if t else "")
    if not gold or not h:
        return 0
    # window=2：gold 相邻两个词之间最多容忍跳掉 2 个解码词。
    # 不限 window 的话，扫描会一路往后跳，任何音频都能「覆盖 100%」，
    # 反而检不出 lead（实测 c2_0445 多念 14 词却被判 0）。
    if match_ratio(gold, h, 0, 2) >= 0.85:
        return 0
    best = 0
    for k in range(1, min(16, len(h))):
        if match_ratio(gold, h, k, 2) >= 0.80:
            best = k
            break
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="G:/_setup/_audio_ch123/out_deliver")
    ap.add_argument("--align", default="G:/_setup/_align_deliver.json")
    ap.add_argument("--bak", default="G:/_setup/_bak_lead_1121")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--frame", type=float, default=0.02)
    ap.add_argument("--fade", type=float, default=0.020)
    a = ap.parse_args()

    import _calm_gate as CG
    plan = CG.load_plan()
    rows = json.load(io.open(a.align, encoding="utf-8"))

    todo = []
    for r in rows:
        rid = r["id"]
        gold = PK.norm_words((plan.get(rid) or {}).get("text") or "")
        ws = word_spans(r)
        if len(gold) < 3:
            # 极短句（Yes./No.）没法用顺序覆盖判，用长度比：解码词数远超原文
            # 只可能是把参考文本念进来了（实测 c1_0046 "Yes." 解出 13 个词）
            if len(ws) >= len(gold) * 3 + 2:
                k = len(ws) - len(gold)
            else:
                continue
        else:
            k = lead_len(gold, ws)
        if k >= 2:
            todo.append((rid, k, ws[k]["s"] * a.frame if k < len(ws) else 0.0,
                         " ".join(w["w"] for w in ws[:k])))

    print("检出 LEAD_REF %d 条" % len(todo))
    for rid, k, t, txt in todo:
        print("  %-9s 多 %d 词，切点 %.2fs  多出：%s" % (rid, k, max(0.0, t - 0.05), txt[:70]))
    if not a.apply:
        print("\n（--apply 才真正裁）")
        return

    os.makedirs(a.bak, exist_ok=True)
    done = 0
    for rid, k, t, txt in todo:
        p = os.path.join(a.dir, rid + ".wav")
        if not os.path.exists(p):
            continue
        bak = os.path.join(a.bak, rid + ".wav")
        if not os.path.exists(bak):
            shutil.copyfile(p, bak)
        y, sr = sf.read(p, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(1)
        cut = int(max(0.0, t - 0.05) * sr)
        if cut <= 0 or cut >= len(y) - int(0.3 * sr):
            continue
        z = y[cut:].copy()
        f = max(1, int(a.fade * sr))
        z[:f] *= np.linspace(0, 1, f)
        if abs(z).max() > 0.98:
            z = z * (0.98 / abs(z).max())
        sf.write(p, z, sr, subtype="PCM_16")
        done += 1
    print("已裁 %d 条，备份在 %s" % (done, a.bak))


if __name__ == "__main__":
    main()
