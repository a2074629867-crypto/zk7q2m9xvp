# -*- coding: utf-8 -*-
"""_asr_ab_r6.py —— 旧/新字节对 ASR 覆盖率（A/B），判「高 wpm 是截断还是 ASR 误识」。

为什么要 A/B：单看新条的 cov 无法区分「音频被截断」与「ASR 对情绪语音误识」。
同一句话、同一个 ASR，旧条（当交付、旧参考档）cov 就是基线；
  新条 cov 明显低于旧条 ⇒ 真的丢字；
  两边差不多 ⇒ ASR 的锅，不归音频。
词表口径：只取 [A-Za-z]，去除单独撇号（先前把 ‘ 当成词，cov 被白白拉低）。
"""
import json
import re
import sys
import difflib

sys.path.insert(0, "G:/_setup")
import _asr_lib

CAND = "G:/_setup/_dlg_plan_r6_cand.jsonl"
OLD = "G:/_setup/_audio_ch123/out/%s.wav"
OUT = "G:/_setup/_asr_ab_r6.json"


def words_of(t):
    t = (t or "").replace("\u2018", " ").replace("\u2019", "'")
    return [x.lower() for x in re.findall(r"[A-Za-z][A-Za-z']*", t)]


def cov_of(ref, hyp):
    sm = difflib.SequenceMatcher(a=ref, b=hyp)
    ok, miss = 0, []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            ok += i2 - i1
        else:
            miss += ref[i1:i2]
    return (ok / len(ref) if ref else 1.0), miss


rows = [json.loads(l) for l in open(CAND, encoding="utf-8")]
pairs = [(r["id"], OLD % r["id"], r["path"], r["text"]) for r in rows]
paths = [p for _, a, b, _ in pairs for p in (a, b)]
res = _asr_lib.transcribe(paths)

out = []
print("%-9s %4s %6s | %5s %5s | %5s %5s | %s" %
      ("id", "词", "dur新", "cov旧", "cov新", "wpm旧", "wpm新", "判定"))
for i, po, pn, text in pairs:
    ref = words_of(text)
    vo, vn = res.get(po) or {}, res.get(pn) or {}
    ho = words_of(vo.get("text"))
    hn = words_of(vn.get("text"))
    co, mo = cov_of(ref, ho)
    cn, mn = cov_of(ref, hn)
    do = vo.get("dur") or 0
    dn = vn.get("dur") or 0
    if cn + 0.05 < co:
        verdict = "新条丢字 %s" % mn
    elif co + 0.05 < cn:
        verdict = "新条更好"
    else:
        verdict = "相当"
    out.append(dict(id=i, n=len(ref), dur_old=round(do, 2), dur_new=round(dn, 2),
                    cov_old=round(co, 3), cov_new=round(cn, 3),
                    miss_old=mo, miss_new=mn, verdict=verdict,
                    hyp_old=vo.get("text"), hyp_new=vn.get("text")))
    print("%-9s %4d %6.2f | %5.2f %5.2f | %5.0f %5.0f | %s" %
          (i, len(ref), dn, co, cn,
           len(ref) / do * 60 if do else 0, len(ref) / dn * 60 if dn else 0, verdict))

json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
bad = [x["id"] for x in out if x["cov_new"] + 0.05 < x["cov_old"]]
print("\n新条明显丢字 %d 条：%s" % (len(bad), bad))
