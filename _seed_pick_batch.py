# -*- coding: utf-8 -*-
"""_seed_pick_batch.py —— 省略号/破折号「延长」，原生 seed 择优（批量）。

背景（全部实测，见 DECISIONS.md 2026-11-25 01:0x）：
  · `<rate>` 标签在本机 tts 入口无效：GGUF `--inspect` 只声明 tts/clon、
    `supports_timestamps=false`，`added_tokens.json` 里没有任何 rate/pitch/pause
    控制 token ⇒ 标签被当普通文本读。
  · 官方 `dots.tts.edit` SDK 要 ROCm/CUDA torch；Windows 无 ROCm 轮子，
    RX580(gfx803) 不在 ROCm 支持表 ⇒ 本地跑不了原生 edit。
  · 后处理轻拉受 1.4x 听觉上限约束，用户否掉（「听不出来没什么用」）。
  · 唯一干净的「原生」路线：同文本换 seed，让模型自己把该词说长。c2_0368 实测
    think 现役 140ms → seed44 400ms / seed45 360ms，音频零改动。

★ 定位方式（关键，踩过坑）：
  不按词名匹配。`_align_gate.norm_text()` 会把撇号删掉（`IT'S` → `IT S`），
  `it's` 在对齐结果里是 it + s 两个 token 组；按词名匹配必然错位。
  改为「标记前文本的 norm 词数 = N ⇒ 取对齐结果第 N 个词（1-based）」。

判据：
  word_ok  对齐词数 == 全文 norm 词数（不吃字），允许整体差 0，否则标 MISMATCH
  target   目标词时长（ms），干净文本对齐，不含静音
  ratio    target / 现役基线，选 1.6~3.5 之间最长的（<1.6 听不出，>3.5 拖过头）
"""
import argparse
import json
import os
import re
import subprocess
import sys

# ★ 必须最先设，且早于 transformers 导入。
#   `_align_gate.MODEL` 是 HF repo id（facebook/wav2vec2-base-960h），不是本地路径；
#   不设离线时 from_pretrained 会联网校验 etag，代理环境下卡十几分钟（实测 10 分钟无输出）。
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import numpy as np
import parselmouth
import soundfile as sf

sys.path.insert(0, "G:/_setup")
import _align_gate as AG      # noqa: E402
import _paths as P            # noqa: E402

OUT = "G:/_setup/_seedpick"
# 单词语音绝对上限。用户认可的 c2_0368 think 是 360ms；
# c1_0035 的 well 拖到 1920ms 已是一个词吃半句（听着是 weeeeeell）。
MAX_ABS_MS = 600
MARK = re.compile(r"(\.\.\.|\u2026|\u2014|\u2013|--|\s-\s)")
QUOTES = "\u2018\u2019\u201c\u201d\"'"


def clean(t):
    """去包裹引号 + 内部 ’ 统一成 '。剧本用 ‘…’ 当引号，与撇号同为 U+2019。

    ★ 2026-11-25 踩坑：原来写 `while t[:1] in QUOTES`，剥净后 t 为空串，
      而 `"" in "abc"` 在 Python 里恒 True（空串是任何串的子串）⇒ **死循环**，
      100% CPU 空转、4 分钟无产出。必须加 `t and` 守卫。
    """
    t = t.strip()
    while t and t[0] in QUOTES:
        t = t[1:]
    while t and t[-1] in QUOTES:
        t = t[:-1]
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", "").replace("\u201d", "")
    return re.sub(r"\s+", " ", t).strip()


def norm_words(t):
    """与 _align_gate.norm_text 同一口径：只留 A-Z，按空格切词。"""
    return AG.norm_text(t).split()


def target_index(text, mark_pos, word=""):
    """标记前有几个 norm 词 ⇒ 目标词的**起始**序号（1-based）。

    ★ 缩写要回退：`norm_text` 删撇号，`It's` 在对齐结果里是 `IT`+`S` 两组。
      按「标记前词数」直接取会拿到 `S`（清擦音、无基频，量出来 530ms 是噪声）。
      c2_0372 实测踩到。这里按目标词自身的 norm 词数回退到它第一部分。
    """
    n = len(norm_words(text[:mark_pos]))
    k = len(norm_words(word)) if word else 1
    return max(1, n - (k - 1)), k


def mtok(text, bonus=150):
    """按词数估 max_tokens，与 _regen9.mtok 同一公式。

    ★ 2026-11-25 踩坑：原来写死 760，对 `It...` 这种 1 词短句等于上限的 5.7 倍，
      模型一路生成到 token 上限，单次 4 分钟（而正常 40 秒）。1 词需 ~15 token，
      132+150 就够。
    """
    n = len(text.split())
    return max(200, min(900, int(n * 12 + 120) + bonus))


def gen(text, ref, out, seed, mtok_override=0):
    cmd = [P.ACPP, "--task", "tts", "--family", "dots_tts", "--model", P.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % (mtok_override or mtok(text)),
           "--session-option", "dots_tts.mem_saver=true"]
    r = subprocess.run(cmd, cwd=P.ACPP_DIR, capture_output=True, text=True, timeout=1800)
    return r.returncode


def align_words(path, text, proc, model):
    r = AG.align(proc, model, path, text)
    if not r:
        return None
    ws, cur = [], []
    for tk in r["tokens"]:
        if tk["tok"] == "|":
            if cur:
                ws.append(cur)
            cur = []
        else:
            cur.append(tk)
    if cur:
        ws.append(cur)
    return [("".join(x["tok"] for x in w).lower(),
             (w[-1]["end"] - w[0]["start"]) * 0.02 * 1000,
             w[0]["start"] * 0.02) for w in ws]


def f0_med(path):
    f = parselmouth.Sound(path).to_pitch(0.01, 75, 600).selected_array["frequency"]
    f = f[f > 0]
    return int(np.median(f)) if len(f) else 0


def voiced_len(y, sr, t0, max_win=2.5, min_gap=0.04, rel_db=25.0):
    """从 t0 起量「连续发声时长」（ms）。

    ★ 为什么不用对齐的 (end−start)：
      句末词（`But...` / `It...`）的对齐 end 会把后面的大段静音一起算进去，
      实测把 160ms 的 but 量成 2240ms（15 倍）。对齐 end 只对句中词可信。
      这里用能量法：从 start 起逐 10ms 帧，遇到连续 40ms 低于「窗口峰值 −25dB」即判停。
    """
    hop = int(0.01 * sr)
    n = len(y) // hop
    if n < 5:
        return 0.0
    e = np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-12
    db = 20 * np.log10(e)
    i0 = max(0, min(n - 1, int(t0 / 0.01)))
    i1 = min(n, i0 + int(max_win / 0.01))
    if i1 - i0 < 5:
        return 0.0
    thr = float(db[i0:i1].max()) - rel_db
    quiet = 0
    for i in range(i0, i1):
        if db[i] < thr:
            quiet += 1
            if quiet >= int(min_gap / 0.01):
                return (i - quiet + 1 - i0) * 10.0
        else:
            quiet = 0
    return (i1 - i0) * 10.0


def n_voiced_segs(path, min_ms=40):
    """发声段个数。复读/多念时远大于词数（实测 2 词生成 7 段）。"""
    f = parselmouth.Sound(path).to_pitch(0.01, 75, 600).selected_array["frequency"]
    v = f > 0
    segs, cur = 0, None
    for i, x in enumerate(v):
        if x and cur is None:
            cur = i
        if (not x or i == len(v) - 1) and cur is not None:
            if (i - cur) * 10 >= min_ms:
                segs += 1
            cur = None
    return segs


def resolve_ref(voice, override=""):
    if override:
        return override
    p = "G:/_setup/_refs_v3/%s.wav" % voice
    if os.path.exists(p):
        return p
    alt = "G:/_setup/_refs_v3/%s.wav" % re.sub(r"_\d+$", "", voice)   # Charles_soft_1 → Charles_soft
    return alt if os.path.exists(alt) else p


def one(item, seeds, proc, model, ref_override=""):
    rid = item["id"]
    rows = json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))
    src = next(r["text"] for r in rows if r["id"] == rid)
    text = clean(src)
    m = MARK.search(text)
    if not m:
        return dict(id=rid, err="no_mark")
    tgt_i, tgt_k = target_index(text, m.start(), item["word"])
    exp_n = len(norm_words(text))
    at_end = clean(text[m.end():]) == ""
    ref = resolve_ref(item.get("voice", ""), ref_override)
    if not os.path.exists(ref):
        return dict(id=rid, err="no_ref:%s" % ref)

    d = os.path.join(OUT, rid)
    os.makedirs(d, exist_ok=True)
    print("\n=== %s  v=%s  %s=%s(#%d)  词数%d  %s" % (
        rid, item.get("voice"), norm_words(text)[tgt_i - 1] if tgt_i else "?",
        item["word"], tgt_i, exp_n, "句末" if at_end else "句中"))

    base = "G:/_setup/_audio_ch123/out/%s.wav" % rid
    b_t = b_dur = None
    b_segs = 0
    if os.path.exists(base):
        w0 = align_words(base, text, proc, model)
        y0, sr0 = sf.read(base, dtype="float64")
        if y0.ndim > 1:
            y0 = y0.mean(1)
        b_dur = len(y0) / sr0
        b_segs = n_voiced_segs(base)
        if w0 and len(w0) >= tgt_i:
            b_t = voiced_len(y0, sr0, w0[tgt_i - 1][2])
            print("  基线 %s=%s  总%.2fs  发声段%d  (词数 %d/%d)" % (
                w0[tgt_i - 1][0], "%.0fms" % b_t, b_dur, b_segs, len(w0), exp_n))

    res = []
    for sd in seeds:
        p = os.path.join(d, "s%s.wav" % sd)
        if not (os.path.exists(p) and os.path.getsize(p) > 10000):
            rc = gen(text, ref, p, int(sd))
            if rc != 0 or not os.path.exists(p):
                print("  seed %-3s 生成失败 rc=%s" % (sd, rc))
                continue
        w = align_words(p, text, proc, model)
        if not w:
            print("  seed %-3s 对齐失败" % sd)
            continue
        y, sr = sf.read(p, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        dur = len(y) / sr
        tv = voiced_len(y, sr, w[tgt_i - 1][2]) if len(w) >= tgt_i else 0
        segs = n_voiced_segs(p)
        # 判据：词数一致（不吃字）+ 时长比合理（不复读/不拖沓）+ 发声段不爆
        #   ★ 实测极短文本会复读：`No. But...` 基线 1.07s/2 段，seed42 生成 5.60s/7 段。
        dr = round(dur / b_dur, 2) if b_dur else None
        bad = []
        if len(w) != exp_n:
            bad.append("词%d/%d" % (len(w), exp_n))
        if dr is not None and not (0.70 <= dr <= 1.90):
            bad.append("时长%.1fx" % dr)
        if segs > max(3, exp_n * 2):
            bad.append("段%d" % segs)
        res.append(dict(seed=int(sd), dur=round(dur, 2), dr=dr, target=round(tv, 0),
                        nword=len(w), nseg=segs, f0=f0_med(p), ok=(not bad),
                        why=",".join(bad)))
        r = res[-1]
        print("  seed %-3s 总%5.2fs(%sx)  %s=%s  段%d  F0 %d  %s" % (
            sd, r["dur"], ("%.1f" % dr) if dr else "-",
            norm_words(text)[tgt_i - 1] if tgt_i else "?",
            "%.0fms" % r["target"], segs, r["f0"],
            "OK" if r["ok"] else "✗ " + r["why"]))

    entry = dict(id=rid, voice=item.get("voice"), word=item["word"], tgt_i=tgt_i,
                 at_end=at_end, text=text, nword=exp_n,
                 base=round(b_t, 0) if b_t else None,
                 base_dur=round(b_dur, 2) if b_dur else None, base_segs=b_segs,
                 seeds=res)
    cand = [r for r in res if r["ok"] and r["target"] and b_t]
    if cand:
        for r in cand:
            r["ratio"] = round(r["target"] / b_t, 2)
        best = sorted(cand, key=lambda r: -r["target"])
        # 1.6x 以下听不出延长；3.5x 以上拖过头。
        # ★ 再加一条：基线本身已经够长（如 c2_0299 的 well 550ms，破折号前自带拖音）时，
        #   所有候选都更短 ⇒ 不动它。硬换等于把已经合适的拖音改短。
        gain = [r for r in best if r["ratio"] >= 1.5 and r["target"] <= MAX_ABS_MS]
        entry["ranked"] = [dict(seed=r["seed"], target=r["target"], ratio=r["ratio"],
                                dur=r["dur"], f0=r["f0"]) for r in best[:4]]
        if not gain:
            over = [r for r in best if r["target"] > MAX_ABS_MS]
            if over and len(over) == len(best):
                entry["pick"] = None
                entry["reason"] = "over_drag(%.0fms)" % over[0]["target"]
                print("  → 不自动选：%d 个候选全部超 %dms（最长 %.0fms），需人工试听"
                      % (len(over), MAX_ABS_MS, over[0]["target"]))
            else:
                entry["pick"] = None
                entry["reason"] = "no_gain(best %.2fx/%.0fms)" % (best[0]["ratio"], best[0]["target"])
                print("  → 不换：基线 %s %.0fms；%d 个候选最长 %.0fms（%.2fx），"
                      "没有既 ≤%dms 又比基线长 1.5x 的" % (
                          item["word"], b_t, len(best), best[0]["target"],
                          best[0]["ratio"], MAX_ABS_MS))
        else:
            pick = max(gain, key=lambda r: r["target"])
            entry["pick"] = pick["seed"]
            entry["pick_ratio"] = pick["ratio"]
            print("  → 选 seed %s  %s=%s (%.1fx)  总%.2fs  F0 %d" % (
                pick["seed"], item["word"], "%.0fms" % pick["target"],
                pick["ratio"], pick["dur"], pick["f0"]))
    else:
        entry["pick"] = None
        print("  → 无合格候选（%d 个 seed 全部被词数/时长/段数判据拦下）" % len(res))
    json.dump(entry, open(os.path.join(d, "_pick.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return entry


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="逗号分隔，空=全部 _elong_targets.json")
    ap.add_argument("--seeds", default="42,43,44,45,46,47,48,49")
    ap.add_argument("--ref", default="")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    items = json.load(open("G:/_setup/_elong_targets.json", encoding="utf-8"))
    if a.ids:
        want = [x.strip() for x in a.ids.split(",") if x.strip()]
        items = [x for x in items if x["id"] in want]
    seeds = [x.strip() for x in a.seeds.split(",") if x.strip()]
    print("条目 %d 条 × %d seed" % (len(items), len(seeds)))

    proc, model = AG.load_model()
    summary = []
    for it in items:
        try:
            summary.append(one(it, seeds, proc, model, a.ref))
        except Exception as e:
            print("  !! %s 异常 %s: %s" % (it["id"], type(e).__name__, e))
            summary.append(dict(id=it["id"], err=str(e)))

    path = "G:/_setup/_seedpick_summary.json"
    old = {}
    if os.path.exists(path):
        old = {x["id"]: x for x in json.load(open(path, encoding="utf-8"))}
    old.update({x["id"]: x for x in summary})
    json.dump(list(old.values()), open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\n===== 汇总 =====")
    for x in summary:
        if x.get("err"):
            print("%-9s ERR %s" % (x["id"], x["err"]))
        else:
            b = x.get("base")
            k = next((r for r in x["seeds"] if r["seed"] == x.get("pick")), None)
            print("%-9s base=%s pick=%s %s ratio=%s" % (
                x["id"], ("%.0f" % b) if b else "-", x.get("pick"),
                ("%.0fms" % k["target"]) if k else "-",
                k.get("ratio") if k else "-"))
    print("-> _seedpick_summary.json")
