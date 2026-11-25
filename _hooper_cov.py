# -*- coding: utf-8 -*-
"""按角色批量跑 ASR 覆盖率，找出「吞字」集中区。

用户 2026-11-24：Hooper 语音「吞字吞音很严重」。用 small.en 贪心转写比词，
覆盖率 drop 与 wpm 做相关 —— 如果「越快覆盖越低」，那就坐实了「读太快导致吞字」。
"""
import argparse
import difflib
import json
import os
import re
import statistics as st
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, "G:/_setup")
from _rate import rate  # noqa: E402


_PUNCT_MAP = {"\u2019": "'", "\u2018": "'", "\u02bc": "'",
              "\u201c": "", "\u201d": "", "\u2013": " ", "\u2014": " "}

# 同音/异写归一：不做这层，ASR 明明听对也会被判「吞字」
_ALIAS = {"ok": "okay", "o": "@DROP", "k": "@DROP", "okay": "okay",
          "yes": "yes", "yeah": "yes", "okey": "okay"}


def words(t):
    """★ 2026-11-24 修：原版只认 ASCII 撇号，而剧本用的是 U+2019（’）。
    于是 You’ll 被切成 [you, ll]，ASR 输出 You'll 是一个 token
    → 2 词对 3 词，cov 直接掉到 0.33（c2_0463 两侧文本相同却只得 0.33）。
    Thomas 110 条缩写密集，这是 cov 中位 0.862 的主因，**不是吞字**。
    """
    for k, v in _PUNCT_MAP.items():
        t = t.replace(k, v)
    # O.K. / OK / Okay 统一成 okay，否则 o/k 两个 token 对 okay 一个 token 必掉分
    t = re.sub(r"\bO\.?K\.?\b", "okay", t, flags=re.I)
    raw = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", t)
    out = []
    for w in raw:
        w = w.lower()
        w = _ALIAS.get(w, w)
        if w != "@DROP":
            out.append(w)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="Thomas,Joseph")
    ap.add_argument("--out", default="G:/_setup/_hooper_cov.json")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    m = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=4)

    rows = json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))
    out = {}
    for who in [x.strip() for x in a.who.split(",") if x.strip()]:
        sub = [r for r in rows if r["who"] == who]
        if a.limit:
            sub = sub[: a.limit]
        items = []
        for r in sub:
            p = "G:/_setup/_audio_ch123/out/%s.wav" % r["id"]
            if not os.path.exists(p):
                continue
            ref = words(r["text"])
            segs, _ = m.transcribe(p, language="en", word_timestamps=False,
                                   vad_filter=False, beam_size=5)
            hyp_t = " ".join(s.text for s in segs)
            hyp = words(hyp_t)
            sm = difflib.SequenceMatcher(a=ref, b=hyp)
            ok, miss = 0, []
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op == "equal":
                    ok += i2 - i1
                else:
                    miss += ref[i1:i2]
            cov = ok / max(1, len(ref))
            try:
                q = rate(p, r["text"])
                wpm = q.get("wpm")
            except Exception:
                wpm = None
            items.append({"id": r["id"], "emo": r["emo"], "cov": round(cov, 3),
                          "wpm": wpm, "words": len(ref), "miss": miss[:8],
                          "hyp": hyp_t.strip()[:120]})
            print("%-9s %-6s cov=%.2f wpm=%s 缺=%s" %
                  (r["id"], r["emo"], cov, ("%4.0f" % wpm) if wpm else "  -", miss[:5]), flush=True)
        cs = [x["cov"] for x in items]
        out[who] = {
            "n": len(items),
            "cov_med": round(st.median(cs), 3) if cs else None,
            "cov_p10": round(sorted(cs)[max(0, len(cs) // 10)], 3) if cs else None,
            "lt_090": sum(1 for c in cs if c < 0.90),
            "lt_080": sum(1 for c in cs if c < 0.80),
            "items": items,
        }
        pairs = [(x["wpm"], x["cov"]) for x in items if x["wpm"]]
        if len(pairs) > 5:
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            mx, my = st.mean(xs), st.mean(ys)
            num = sum((x - mx) * (y - my) for x, y in pairs)
            den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
            out[who]["corr_wpm_cov"] = round(num / den, 3) if den else None
            fast = [y for x, y in pairs if x > 260]
            slow = [y for x, y in pairs if x <= 260]
            out[who]["cov_fast"] = round(st.median(fast), 3) if fast else None
            out[who]["cov_slow"] = round(st.median(slow), 3) if slow else None

    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n==== 汇总 ====")
    for who, v in out.items():
        print("%-8s n=%3d cov中位 %.3f p10 %.3f  <0.90: %d  <0.80: %d  "
              "corr(wpm,cov)=%s  cov(快>260)=%s vs cov(慢)=%s"
              % (who, v["n"], v["cov_med"], v["cov_p10"], v["lt_090"], v["lt_080"],
                 v.get("corr_wpm_cov"), v.get("cov_fast"), v.get("cov_slow")))
    print("-> %s" % a.out)


if __name__ == "__main__":
    main()
