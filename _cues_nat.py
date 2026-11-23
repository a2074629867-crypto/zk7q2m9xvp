# -*- coding: utf-8 -*-
"""_cues_nat.py —— 对 castle_cues 全量测 NISQA，找「高质量替代素材」。

背景（2026-11-12）：闸6 实测参考素材质量是天花板 —— voice_lib 84 条参考的 NISQA-MOS
中位仅 2.34（交付旁白的参照是 3.81），其中 25 条 <2.0。Charles_angry(1.11)/
nervous(1.52)/defiant(1.30)、Thomas_loud(1.78~2.19)、Thomas_begging(0.84~1.39)
这些档生成出来的音频自然度必然塌，且库里**没有同角色同情绪的替代档**。

这一步回答：原始片源 castle_cues（393 条切片）里，还有没有没被选进 voice_lib 的干净片段。
输出 _cues_nat.json：每条 wav 的四项分 + 语音时长。
"""
import glob, json, os, sys, time

sys.path.insert(0, "G:/_setup")
import _nat_guard as NG

OUT = "G:/_setup/_cues_nat.json"


def main():
    ws = sorted(glob.glob("G:/_setup/castle_cues/*.wav"))
    try:
        old = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        old = {}
    t0 = time.time()
    for i, p in enumerate(ws, 1):
        k = os.path.basename(p)[:-4]
        if k in old and old[k].get("mos") is not None:
            continue
        try:
            r = NG.raw(p)
        except Exception as e:
            old[k] = dict(mos=None, err=str(e)[:80])
            continue
        old[k] = dict(mos=r.get("nq_mos"), noi=r.get("nq_noi"), dis=r.get("nq_dis"),
                      col=r.get("nq_col"), sp=r.get("sp"))
        if i % 50 == 0:
            el = time.time() - t0
            print("  %d/%d %.0fs  剩 %.0f 分" % (i, len(ws), el, (len(ws) - i) * el / i / 60),
                  flush=True)
            json.dump(old, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(old, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    v = [x["mos"] for x in old.values() if x.get("mos")]
    import numpy as np
    print("完成 %d 条  MOS p10 %.2f p50 %.2f p90 %.2f  ≥2.8 的 %d 条"
          % (len(old), *np.percentile(v, [10, 50, 90]), sum(1 for x in v if x >= 2.8)))


if __name__ == "__main__":
    main()
