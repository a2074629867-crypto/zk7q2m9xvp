# -*- coding: utf-8 -*-
"""gate_timbre_seq.py —— 第 8 维：音色突变「按物理位置」三路检测（只报警，不判死）

来源：用户 2026-11-14 15:48 纠正 —— 音色突变最常见的是**标点停顿之后换句**那一刻，
不是句内。详见 DECISIONS.md「音色突变要按物理位置分三路测」与 `_dlg_seq_report.md`。

三路（互不重叠，实测 0 交集）：
  路 1 条间    同角色连续出场，|ΔF0 中位| ≥6 半音 **且** 换了参考档
               （同档 p95 只有 3.43 半音；换档 p95 12.69 ⇒ 6 是干净分界）
  路 2 停顿后  drift 窗序列里「跨停顿的相邻有效窗对」（中间 ≥2 失声窗），
               |ΔF0| ≥6 半音 **且** 谱质心比 ≥1.3（音高与声道形状同时变 = 真换音区）
  路 3 句内    drift profile=dlg 判 FAIL（声道形状双维同时超，持续）

**不参与 decide()**：三路都是「提示级」，只进报告的人耳队列。
原因（DECISIONS 16:1x）：路 1 的换档落差是**设计问题**（每句参考档不同），
不是单条 bug；路 2/路 3 有元音切换噪声，误报不低。

用法：
  import gate_timbre_seq as TS; TS.load(); TS.check(sid)
  python gate_timbre_seq.py            # 全库汇总
"""
import json
import math
import os
import sys

HERE = "G:/_setup"
PLAN = os.path.join(HERE, "_dlg_plan_v2.jsonl")
FP = os.path.join(HERE, "_dlg_fp.json")
DRIFT = os.path.join(HERE, "_drift_cache.json")

ST_ROAD1 = 6.0      # 半音（仅用于「记录落差」，不单独报警，见下）
ST_ROAD1_ALERT = 14.0   # 极端落差：换档 p95=12.7、max=16.3 ⇒ 14 是 p98 之外
ST_ROAD2 = 6.0
CEN_ROAD2 = 1.30

_PLAN = _FP = _DRIFT = _IDX = None


def _semi(a, b):
    if not a or not b or a <= 0 or b <= 0:
        return None
    return 12.0 * math.log2(b / a)


def load(force=False):
    global _PLAN, _FP, _DRIFT, _IDX
    if _PLAN is not None and not force:
        return
    _PLAN = {json.loads(l)["id"]: json.loads(l)
             for l in open(PLAN, encoding="utf-8") if l.strip()}
    _FP = json.load(open(FP, encoding="utf-8")) if os.path.exists(FP) else {}
    _DRIFT = {}
    if os.path.exists(DRIFT):
        for x in json.load(open(DRIFT, encoding="utf-8")):
            sid = os.path.basename(x["file"].replace("\\", "/"))[:-4]
            _DRIFT[sid] = x
    _IDX = _build_road1()


def _build_road1():
    """同角色按 id 排序的时间线，返回 {sid: [(other_id, delta_st, same_voice), ...]}"""
    bywho = {}
    for sid, r in _PLAN.items():
        bywho.setdefault(r["who"], []).append(sid)
    idx = {}
    for who, seq in bywho.items():
        seq.sort()
        for a, b in zip(seq, seq[1:]):
            fa = (_FP.get(a) or {}).get("f0")
            fb = (_FP.get(b) or {}).get("f0")
            d = _semi(fa, fb)
            if d is None:
                continue
            same_v = _PLAN[a].get("voice") == _PLAN[b].get("voice")
            idx.setdefault(a, []).append((b, d, same_v))
            idx.setdefault(b, []).append((a, -d, same_v))
    return idx


def road1(sid):
    """路 1：与相邻同角色条目的 F0 落差。

    ★ 2026-11-14 21:2x 实测修正：296 个换档相邻对里 |ΔF0| 中位就是 **6.4 半音**，
    p95 12.7 —— 也就是「换档必跳 6 半音」是**设计常态**（每句参考档不同），
    不是单条 bug。所以本路**不产生逐条报警**，只在 ≥14 半音（p98 之外）时记一笔，
    且报告里作为「设计层问题」单独统计，不并入待修清单。
    """
    out = []
    for other, d, same_v in (_IDX.get(sid) or []):
        if abs(d) >= ST_ROAD1 and not same_v:
            out.append(dict(other=other, delta_st=round(d, 2),
                            extreme=abs(d) >= ST_ROAD1_ALERT,
                            voice_self=(_PLAN.get(sid) or {}).get("voice"),
                            voice_other=(_PLAN.get(other) or {}).get("voice")))
    return out


try:
    from mt_seg_drift import JUDGE_VER as _JV
except Exception:  # noqa: BLE001
    _JV = None


def _drift_of(sid, wav=None):
    """取 drift 结果。**只有交付路径才允许用缓存**，其余一律实时算。

    ★ 2026-11-14 22:1x 修：缓存按文件名命中，候选与现役同名（不同目录）；
    而且 `c2_0372` 候选时长恰好等于现役（8.64s），连 dur 断言都拦不住。
    ⇒ 判据改成「路径必须是交付路径」，候选/回填验证全部实时算。
    """
    r = _DRIFT.get(sid)
    if r is not None and wav:
        _deliv = os.path.abspath(os.path.join("G:/_setup/_audio_ch123/out", sid + ".wav"))
        if os.path.abspath(wav).lower() != _deliv.lower():
            r = None
        else:
            cd = r.get("dur")
            if r.get("ver") != _JV:
                r = None
            try:
                import soundfile as sf
                if cd is None or abs(float(cd) - sf.info(wav).duration) > 0.05:
                    r = None
            except Exception:
                r = None
    if r is None and wav:
        try:
            import mt_seg_drift as D
            r = D.one(wav, profile="dlg")
        except Exception:
            r = None
    return r


def road2(sid, wav=None):
    """路 2：跨停顿（中间 ≥2 失声窗）的相邻有效窗对，ΔF0 与谱质心同时变。"""
    r = _drift_of(sid, wav) or {}
    out = []
    for p in (r.get("pairs") or []):
        gap = p.get("gap") or 0
        dst = p.get("dst")
        dcen = p.get("dcen")
        if gap < 2 or dst is None or not dcen:
            continue
        ratio = max(dcen, 1.0 / dcen)
        if abs(dst) >= ST_ROAD2 and ratio >= CEN_ROAD2:
            out.append(dict(t=round(float(p["t"]), 2), gap=gap,
                            delta_st=round(float(dst), 2), cen_ratio=round(float(ratio), 2)))
    return out


def road3(sid, wav=None):
    """路 3：句内声道形状突变（drift dlg 判 FAIL）。"""
    r = _drift_of(sid, wav) or {}
    if r.get("profile") != "dlg" or r.get("verdict") != "FAIL":
        return None
    ev = [e for e in (r.get("events") or []) if e.get("level") == "FAIL"]
    if not ev:
        return None
    return dict(t=round(float(ev[0]["t"]), 2), why="/".join(ev[0].get("why") or []))


def check(sid, wav=None):
    """返回 {'level': 'alert'|'ok', 'r1': [...], 'r2': [...], 'r3': {...}|None, 'why': str}

    `wav` 给了就按该文件实时算（候选/回填验证必须给），
    不给则读缓存（全量报告用，快）。
    ★ 报警只由路 2 / 路 3 触发。路 1 的落差是设计常态（中位 6.4 半音），
    只在 `extreme=True`（≥14 半音）时拼进 why 作参考，不改变 level。
    """
    load()
    r1, r2, r3 = road1(sid), road2(sid, wav), road3(sid, wav)
    hits = []
    ext = [x for x in r1 if x["extreme"]]
    if r2:
        h = max(r2, key=lambda x: abs(x["delta_st"]))
        hits.append("停顿后换音区 @%.2fs ΔF0%+.1f 谱质心×%.2f"
                    % (h["t"], h["delta_st"], h["cen_ratio"]))
    if r3:
        hits.append("句内声道突变 @%.2fs %s" % (r3["t"], r3["why"]))
    if ext:
        h = max(ext, key=lambda x: abs(x["delta_st"]))
        hits.append("（参考）条间极端换档 ΔF0%+.1f vs %s" % (h["delta_st"], h["other"]))
    return dict(level="alert" if (r2 or r3) else "ok", r1=r1, r2=r2, r3=r3,
                why="；".join(hits) if hits else "")


def main():
    load()
    rows = []
    for sid in sorted(_PLAN):
        c = check(sid)
        if c["level"] == "alert":
            rows.append((sid, _PLAN[sid]["who"], _PLAN[sid]["emo"],
                         bool(c["r1"]), len(c["r2"]), bool(c["r3"]), c["why"]))
    n1 = sum(1 for r in rows if r[3])
    n2 = sum(1 for r in rows if r[4])
    n3 = sum(1 for r in rows if r[5])
    print("对白 %d 条，三路报警 %d 条" % (len(_PLAN), len(rows)))
    print("  路1 条间 %d ｜ 路2 停顿后 %d ｜ 路3 句内 %d" % (n1, n2, n3))
    only2 = [r for r in rows if r[4] and not r[3] and not r[5]]
    print("  仅路2（用户最在意的场景）%d 条" % len(only2))
    print()
    for sid, who, emo, a, b, c, why in rows:
        print("  %-9s %-8s %-5s [%s%s%s] %s"
              % (sid, who, emo, "1" if a else "-", "2" if b else "-",
                 "3" if c else "-", why[:90]))


if __name__ == "__main__":
    main()
