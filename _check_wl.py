# -*- coding: utf-8 -*-
"""先验数据可信度：词表与音频对不对得上（词数 / 时长 = wpm）。"""
import json, os
import soundfile as sf

ROOT = r"G:\_setup"
for tag, wlfile, d in (("old", "_wl_words.json", "_audio_ch123/out"),
                       ("new", "_wl_regen1123.json", "_regen_1123")):
    wl = json.load(open(os.path.join(ROOT, wlfile), encoding="utf-8"))
    wl = {os.path.basename(k).rsplit(".", 1)[0]: v for k, v in wl.items()}
    bad, n, ratios = [], 0, []
    for sid, v in wl.items():
        p = os.path.join(ROOT, d, sid + ".wav")
        if not os.path.exists(p):
            continue
        durs = [w for w in v.get("words") or []]
        if not durs:
            continue
        try:
            info = sf.info(p)
        except Exception:
            continue
        n += 1
        words = len([w for w in durs if any(c.isalpha() for c in w["w"])])
        rate = words / info.duration * 60.0
        ratios.append(rate)
        if rate > 260:
            bad.append((sid, words, round(info.duration, 2), round(rate)))
    ratios.sort()
    print("== %s  n=%d  wpm含停顿 p50=%.0f p90=%.0f max=%.0f  超260的 %d 条"
          % (tag, n, ratios[len(ratios)//2], ratios[int(len(ratios)*0.9)], ratios[-1], len(bad)))
    for b in bad[:6]:
        print("    ", b)
