# -*- coding: utf-8 -*-
"""用当前闸门阈值重判已有候选（不重新生成、不重跑 ASR/wpt）。

为什么需要它：闸门阈值是跑批中途才按标定结果改的，正在运行的进程用的是旧值。
wav 和 prom 都还在盘上，只要重算测量 + 闸门就能得到新结论，不必再烧一遍生成。

用法：
    python _rejudge.py                 # 只看，不写 state
    python _rejudge.py --apply         # 写回 state（attempts 与 cand）
"""
import os
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mt_adv_fix as M
import _adv_prom
import _align_lib as AL
import _guard


def pick(cws, adv):
    if not cws:
        return None
    hit = [c for c in cws if c["key"] == adv.lower()]
    return hit[-1] if hit else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--units", default=None)
    a = ap.parse_args()
    only = {x.strip() for x in a.units.split(",")} if a.units else None

    path = M.STATE
    st = json.load(open(path, encoding="utf-8"))
    us = st["units"]

    BL = AL.load_baseline()
    changed, rows = 0, []
    for u, x in sorted(us.items()):
        if only and u not in only:
            continue
        adv = x["adv"].lower()
        text = x["text"]
        for at in x.get("attempts") or []:
            w, c = at.get("wav"), at.get("ctl_wav")
            if not (w and c and os.path.exists(w) and os.path.exists(c)):
                continue
            tp = M.att_prom(u, at.get("seed"))
            if not tp:
                continue
            cp = os.path.join(M.ROOT, "_mt_adv_prom_ctl_%s" % at.get("seed"), u + ".prom")
            if not os.path.exists(cp):
                continue
            cw = _adv_prom.measure_one(w, tp, text)
            cc = _adv_prom.measure_one(c, cp, text)
            rec = pick(cw, adv)
            ctl = pick(cc, adv)
            # ★ 补时长轴要用的三个量（口径统一到 _align_lib）：
            #   dur_x = sps ÷ 其余内容词 sps 中位（旧口径，仅展示）
            #   rel   = sps ÷ **全部**内容词 sps 中位（含自身，与真人锚点一致）
            #   rel_z = 音节校正后的 rel（时长轴的判据）
            import statistics as _st
            for _r, _all in ((rec, cw), (ctl, cc)):
                if not _r or not _all:
                    continue
                _allsp = [_w["sps"] for _w in _all if _w["sps"]]
                _o = [_w["sps"] for _w in _all if _w is not _r and _w["sps"]]
                if _o:
                    _r["dur_x"] = round(_r["sps"] / max(_st.median(_o), 1e-6), 3)
                if _allsp:
                    _rel = _r["sps"] / max(_st.median(_allsp), 1e-6)
                    _r["rel"] = round(_rel, 3)
                    _r["rel_z"] = AL.rel_z_value(_rel, _r.get("nsyl") or 1, BL)
            if not rec:
                at["judge"] = "WATCH"
                at["by"] = "重判:副词缺失"
                continue
            g = _guard.all_guards(w, tp, text, ctl=c, ctl_prom=cp,
                                  delivered=M.orig_wav(u), exclude_uid=u,
                                  cand_cws=cw, ctl_cws=cc, adv=adv)
            j, by = M.judge_cand(rec, ctl, g)
            old = at.get("judge")
            at.update(judge=j, by=by,
                      loc=None if rec is None else rec.get("loc"),
                      voiced=None if rec is None else rec.get("voiced"),
                      share=None if rec is None else rec.get("share"),
                      rel=None if rec is None else rec.get("rel"),
                      rel_z=None if rec is None else rec.get("rel_z"),
                      loc_ctl=None if ctl is None else ctl.get("loc"),
                      voiced_ctl=None if ctl is None else ctl.get("voiced"),
                      share_ctl=None if ctl is None else ctl.get("share"),
                      guards=dict(verdict=g.get("verdict"), failed=g.get("failed"),
                                  warned=g.get("warned"),
                                  audio=(g.get("audio") or {}).get("why"),
                                  words=(g.get("words") or {}).get("why"),
                                  speaker=(g.get("speaker") or {}).get("margin"),
                                  prosody=(g.get("prosody") or {}).get("why")))
            if old != j:
                changed += 1
            rows.append((u, at.get("seed"), at.get("cond"), old, j, by,
                         at.get("loc_ctl"), at.get("loc"), g.get("verdict"),
                         (g.get("words") or {}).get("why")))

    print("%-7s %-6s %-4s %-8s %-8s %-6s %-22s %s"
          % ("uid", "seed", "cond", "旧", "新", "loc", "依据", "闸门"))
    for u, s, c, o, n, by, lc, l, gv, wd in rows:
        print("%-7s %-6s %-4s %-8s %-8s %-6s %-22s %s"
              % (u, s, c, o, n, "%s→%s" % (lc, l), by[:22], gv))

    if not a.apply:
        print("\n[dry-run] 加 --apply 才写回 %s（%d 条判定变化）" % (os.path.basename(path), changed))
        return
    json.dump(st, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写回 %s（%d 条判定变化）" % (os.path.basename(path), changed))


if __name__ == "__main__":
    main()
