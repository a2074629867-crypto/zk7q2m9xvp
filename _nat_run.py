# -*- coding: utf-8 -*-
"""_nat_run.py —— 对 239 条对白全量跑自然度下限闸（NISQA + SQUIM），结果落 _nat_dlg.json。

判据完全是 _nat_guard 里标定好的（合成退化 AUC 0.90 的那套），不重新发明：
  FAIL  score < -2.3σ   WARN < -1.4σ   OK 其余
  语音 <0.9s 判不出（UNKNOWN，不参与判决）
"""
import json, os, sys, time
sys.path.insert(0, "G:/_setup")
import _nat_guard as NG

AUD = "G:/_setup/_audio_ch123/out"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
OUT = "G:/_setup/_nat_dlg.json"


def main():
    rows = []
    for l in open(PLAN, encoding="utf-8"):
        l = l.strip()
        if l:
            rows.append(json.loads(l))
    res, t0 = {}, time.time()
    for i, o in enumerate(rows, 1):
        p = os.path.join(AUD, o["id"] + ".wav")
        if not os.path.exists(p):
            continue
        try:
            r = NG.verdict(p)
        except Exception as e:
            r = dict(verdict="UNKNOWN", why="测量失败：%s" % e, score=None)
        r.pop("raw", None) if isinstance(r.get("raw"), dict) and len(str(r.get("raw"))) > 400 else None
        res[o["id"]] = dict(r, who=o["who"], emo=o["emo"])
        if i % 20 == 0:
            el = time.time() - t0
            print("  %d/%d  %.0fs (%.1fs/条) 剩余约 %.0f 分"
                  % (i, len(rows), el, el / i, (len(rows) - i) * el / i / 60), flush=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    import collections
    print("完成 %d 条 -> %s" % (len(res), OUT))
    print("判决:", dict(collections.Counter(v["verdict"] for v in res.values())))


if __name__ == "__main__":
    main()
