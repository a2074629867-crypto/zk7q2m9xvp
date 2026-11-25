# -*- coding: utf-8 -*-
"""_wtlib2.py —— 词时间戳改用「字母级强制对齐」，不再用 whisper 猜。

用户 2026-11-25 09:2x：「我们用英文 ASR 也不是 whisper，我们不是用 Parakeet 吗？
还有另一种更好的，直接字母级的那种……是有三个 ASR 的，精准度从小到大。」

库里确实有三档，本条链路却一直停在最低那档：

  | 档 | 实现 | 粒度 | 本条链路用不用 |
  |---|---|---|---|
  | 1 | faster-whisper（`transplant_prosody2.word_times`） | 词，±40~280 ms | **一直用它** ← 错在这里 |
  | 2 | Parakeet TDT 0.6b v3 int8（`_asr_lib.transcribe`） | 词 | 只用于覆盖率/吞字校验 |
  | 3 | **wav2vec2-960h + torchaudio.forced_align（`_align_gate`）** | **字符，20 ms** | 只用于吞字检测 |

实测（`_wt_err.py`，10 句 213 词）whisper 词尾相对强制对齐：
  p5 −120ms / p50 +20ms / p95 +568ms，|误差| 中位 40ms，最大 2180ms；
  **24% 的词 whisper 词尾早于真实词尾 >40ms ⇒ 切点落进词里。**
c1_0174 的 `himself`：whisper 2.44，强制对齐 2.52（/l/ 2.42-2.46、/f/ 2.48-2.52）
⇒ 插入静音把 "himself" 劈成 "himse … lf"，贪心解码直接吐出 `HIMSELF OLF`。

## 本模块做什么

1. 用 `_align_gate.align`（字符级）拿到每个字符的 [start,end]（20ms 帧）；
2. 按空白合并成词，**词尾 = 最后一个字符的 end**（whisper 的错就错在这里）；
3. 与 whisper 的词序列做 LCS 配对：**文本、标点仍取 whisper**（`plan_from_text`
   靠它认标点），**时间取强制对齐**；对不上的词保留 whisper 时间并标记。
4. 结果缓存进 `_wt_fa_cache.json`（键同 `_wt_cache.json`：basename|size|mtime）。

用法：
  G:/Python310/python.exe -u _wtlib2.py <wav> [<wav> ...]    # 打印对照
"""
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CACHE = os.path.join(HERE, "_wt_fa_cache.json")
_MEM = None
_PROC = None
_MODEL = None
_META = None


def _cache():
    global _MEM
    if _MEM is None:
        _MEM = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    return _MEM


def _meta():
    """sid → {text}。对齐需要 gold 文本。"""
    global _META
    if _META is None:
        _META = {}
        p = os.path.join(HERE, "_narr_plan_for_pause.jsonl")
        if os.path.exists(p):
            for l in open(p, encoding="utf-8"):
                r = json.loads(l)
                _META[r["id"]] = r
    return _META


def text_of(sid):
    r = _meta().get(sid)
    return (r or {}).get("text", "")


def _model():
    global _PROC, _MODEL
    if _MODEL is None:
        import _align_gate as AG
        _PROC, _MODEL = AG.load_model()
    return _PROC, _MODEL


def _fa_words(wav, text):
    """字符级强制对齐 → 词表 [{'w','start','end'}]（词尾取最后一字符的 end）。"""
    import _align_gate as AG
    proc, model = _model()
    r = AG.align(proc, model, wav, text)
    if r is None:
        return None
    words, cur = [], []
    for t in r["tokens"]:
        if t["tok"] == "|":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        words.append(cur)
    out = []
    for w in words:
        out.append(dict(w="".join(x["tok"] for x in w),
                        start=w[0]["start"] * AG.FRAME_MS / 1000.0,
                        end=w[-1]["end"] * AG.FRAME_MS / 1000.0))
    return out


def _norm(s):
    return re.sub(r"[^a-z']", "", s.lower())


def word_times_fa(wav):
    """返回 [(start, end, text)]：时间来自字符级强制对齐，文本/标点来自 whisper。"""
    from _wtlib import word_times_cached as whisper_times
    sid = os.path.basename(wav).rsplit(".", 1)[0]
    wl = whisper_times(wav)                     # [(s,e,text)]
    if not text_of(sid):
        return wl
    fa = _fa_words(wav, text_of(sid))
    if not fa:
        return wl
    a = [_norm(x[2]) for x in wl]
    b = [_norm(x["w"]) for x in fa]

    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    fixed = {}
    for blk in sm.get_matching_blocks():
        for i in range(blk.size):
            fixed[blk.a + i] = fa[blk.b + i]
    out = []
    for i, (s, e, txt) in enumerate(wl):
        f = fixed.get(i)
        if f and f["end"] > f["start"]:
            out.append((round(f["start"], 3), round(f["end"], 3), txt))
        else:
            out.append((s, e, txt))
    return out


def word_times_cached(wav):
    c = _cache()
    st = os.stat(wav)
    key = "%s|%d|%d" % (os.path.basename(wav), st.st_size, int(st.st_mtime))
    if key in c:
        return [tuple(x) for x in c[key]]
    rw = word_times_fa(wav)
    c[key] = [list(x) for x in rw]
    json.dump(c, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return rw


def main():
    from _wtlib import word_times_cached as whisper_times
    for wav in sys.argv[1:]:
        wl = whisper_times(wav)
        fa = word_times_cached(wav)
        print("=" * 20, os.path.basename(wav), "whisper %d 词 / FA %d 词" % (len(wl), len(fa)))
        for x, y in zip(wl, fa):
            d = (y[1] - x[1]) * 1000
            flag = "  <<< 早 %.0fms" % d if d < -40 else ""
            print("  %-14s whisper %.2f-%.2f   FA %.2f-%.2f%s" % (x[2], x[0], x[1], y[0], y[1], flag))


if __name__ == "__main__":
    main()
