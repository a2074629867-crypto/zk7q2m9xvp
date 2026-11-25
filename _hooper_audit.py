# -*- coding: utf-8 -*-
"""Hooper 专项：语速 / 吞字 / 覆盖率的角色级体检。

用户 2026-11-24：「Hopper 的语音容易听不清楚，读得太快，而且口音很重，
吞字吞音也很严重。」

WHO_MAP: Edmund -> Thomas（rebuild_plan_v2.py），所以 Thomas = Edmund Hooper；
Joseph 也是 Hooper（Joseph Hooper 是他的父亲）。
两组分开统计，别混。
"""
import argparse
import json
import os
import statistics as st
import sys

sys.path.insert(0, "G:/_setup")
from _rate import rate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="G:/_setup/_hooper_audit.json")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()

    rows = json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))
    plan = {}
    for l in open("G:/_setup/_castle_en_ch123_plan_v4.jsonl", encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            plan[r["id"]] = r

    res = {}
    for who in ("Thomas", "Joseph"):
        sub = [r for r in rows if r["who"] == who]
        items = []
        for r in sub:
            p = "G:/_setup/_audio_ch123/out/%s.wav" % r["id"]
            if not os.path.exists(p):
                continue
            try:
                q = rate(p, r["text"])
            except Exception as e:
                items.append({"id": r["id"], "err": "%s:%s" % (type(e).__name__, e)})
                continue
            items.append({"id": r["id"], "emo": r["emo"], "cls": r.get("cls"),
                          "voice": plan.get(r["id"], {}).get("voice"),
                          "wpm": q.get("wpm"), "wpm_span": q.get("wpm_span"),
                          "dur": q.get("dur"), "words": len(r["text"].split()),
                          "text": r["text"][:60]})
        good = [x for x in items if x.get("wpm")]
        res[who] = {"n": len(items), "measured": len(good),
                    "wpm_p10": round(st.quantiles([x["wpm"] for x in good], n=10)[0], 1) if len(good) > 9 else None,
                    "wpm_med": round(st.median([x["wpm"] for x in good]), 1) if good else None,
                    "wpm_p90": round(st.quantiles([x["wpm"] for x in good], n=10)[8], 1) if len(good) > 9 else None,
                    "over_220": sum(1 for x in good if x["wpm"] > 220),
                    "over_260": sum(1 for x in good if x["wpm"] > 260),
                    "items": items}
        print("\n===== %s  n=%d  实测 %d =====" % (who, len(items), len(good)))
        print("wpm(去停顿) p10 %s  p50 %s  p90 %s   >220: %d   >260: %d"
              % (res[who]["wpm_p10"], res[who]["wpm_med"], res[who]["wpm_p90"],
                 res[who]["over_220"], res[who]["over_260"]))
        hot = sorted(good, key=lambda x: -x["wpm"])[: a.top]
        print("%-9s %-6s %-18s %6s %6s %5s  %s" % ("id", "emo", "voice", "wpm", "span", "words", "text"))
        for x in hot:
            print("%-9s %-6s %-18s %6.0f %6.0f %5d  %s"
                  % (x["id"], x["emo"], x.get("voice") or "-", x["wpm"],
                     x.get("wpm_span") or 0, x["words"], x["text"][:44]))

    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> %s" % a.out)


if __name__ == "__main__":
    main()
