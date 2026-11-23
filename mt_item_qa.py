# -*- coding: utf-8 -*-
"""mt_item_qa.py —— 逐条体检：音质（NISQA 四维）+ 句内音色漂移。

★★ 为什么要有这一步（2026-10-31 用户追问）
  用户问「只用 RDR 是不是把 NISQA、音质检测都去掉了」。核实结果：
    · `mt_ch_pipeline.py`（交付链路）= 裁边 → RDR → 拼接，**不含音质**
    · `mt_loop.py`（回环门禁）= 重音 + 覆盖率，**不含音质**
    · `mt_audit.py`（交付体检）= dur/peak/rms/wpm，**不含 NISQA**
    · `mt_nisqa_all.py` = NISQA 四维，跑过 2161 条，但**是手动批次，没进任何判据**
  也就是说不是「被 RDR 替换掉了」，而是**一直没接进链路**。RDR 是语速/停顿密度，
  与音质正交，两者不能互相替代（NISQA DIS 是唯一可用的断流判据）。

★ 两层各管什么
  NISQA（mos/noi/col/dis/loud）—— 伪影、噪声、染色、断流。整条口径。
  seg_drift（mt_seg_drift）—— 句内音色突变/气声化。窗级口径。
  两者互补：整条 NISQA 正常、句内某段掉成气声，只有 seg_drift 看得见。

★ 判据（都不作自动拒收，只出清单）
  NISQA：mos < 2.5 或 dis < 2.0 → FAIL；mos < 3.0 或 dis < 3.0 → WARN
  ★ 短句慎用：实测 NISQA 与时长相关 r=0.42，<2s 的条目分数偏低不代表缺陷。
    <2s 的条目 NISQA 只记数值不参与定级。
  seg_drift：见 mt_seg_drift（阈值由 180 条正常旁白零分布定）

用法：
  G:/Python310/python.exe mt_item_qa.py --dir ch123_final --out _item_qa_dialog.json
  G:/Python310/python.exe mt_item_qa.py --dir ch123_final --no-nisqa
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile

import numpy as np

ROOT = "G:/_setup"
sys.path.insert(0, ROOT)
MODEL = "D:/eval_models/nisqa/nisqa.tar"

MOS_FAIL, MOS_WARN = 2.5, 3.0
DIS_FAIL, DIS_WARN = 2.0, 3.0
NISQA_MIN_DUR = 2.0        # 短于此只记数值，不定级


def run_nisqa(files):
    # ★ 不是 `import nisqa`：site-packages 里的 nisqa 包没有 run()，
    #   包装在 ch123_nisqa.py 里（mt_nisqa_all.py 用的就是这个）。
    import ch123_nisqa as N
    tmp = tempfile.mkdtemp(prefix="nis_", dir=os.path.join(ROOT, "_mt_tmp"))
    mp = {}
    for i, f in enumerate(files):
        key = "f%06d.wav" % i
        shutil.copy2(f, os.path.join(tmp, key))
        mp[key] = f
    df = N.run(tmp, MODEL)
    out = {}
    for _, r in df.iterrows():
        src = mp.get(str(r["deg"]))
        if not src:
            continue
        out[src] = dict(mos=round(float(r.get("mos_pred", 0)), 3),
                        noi=round(float(r.get("noi_pred", 0)), 3),
                        col=round(float(r.get("col_pred", 0)), 3),
                        dis=round(float(r.get("dis_pred", 0)), 3),
                        loud=round(float(r.get("loud_pred", 0)), 3))
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def has_inserted_pause(path, thr=1.20):
    """自动判断这条音频里有没有「插入的停顿」。

    ★ 为什么不能靠命令行 flag（2026-10-31 审查）：
      `no_pause` 守卫原本只看 `--paused`，默认 False。章级成品同样走默认值，
      守卫等于关闭 —— N0824 那种 DIS 1.87 照样判 FAIL。前置条件的真假必须来自
      输入本身的属性，不能来自「操作者记不记得加参数」。
    判据：最长静音 >= 1.20s（真人逗号 1.17 / 句号 1.76，句内自然停顿远短于此）。
    """
    import soundfile as sf
    try:
        x, sr = sf.read(path, dtype="float32")
    except Exception:  # noqa: BLE001
        return False
    if x.ndim > 1:
        x = x.mean(1)
    n = max(1, int(0.02 * sr))
    k = len(x) // n
    if k < 5:
        return False
    db = 20 * np.log10(np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(1)) + 1e-12)
    ref = float(np.percentile(db, 90))
    sil = db < ref - 40.0
    best = cur = 0
    for v in sil:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best * 0.02 >= thr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--glob", default="*.wav")
    ap.add_argument("--out", default="")
    ap.add_argument("--no-nisqa", action="store_true")
    ap.add_argument("--no-seg", action="store_true")
    ap.add_argument("--no-det", action="store_true", help="跳过条件化检测器（crest/span/气声/硬切）")
    ap.add_argument("--role", default="narr", help="narr|charles|hooper（决定 F0 提取参数）")
    ap.add_argument("--paused", action="store_true",
                    help="输入已插停顿（章级成品）时加上 —— NISQA-DIS 会把停顿当断流")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, a.glob)))
    if a.limit:
        files = files[:a.limit]
    if not files:
        print("没有文件", file=sys.stderr)
        return 2
    print("逐条体检 %d 条 <- %s" % (len(files), a.dir), flush=True)

    import wave
    dur = {}
    for f in files:
        try:
            w = wave.open(f, "rb")
            dur[f] = w.getnframes() / w.getframerate()
            w.close()
        except Exception:  # noqa: BLE001
            dur[f] = 0.0

    nis = {}
    if not a.no_nisqa:
        print("  NISQA ...", flush=True)
        try:
            nis = run_nisqa(files)
        except Exception as e:  # noqa: BLE001
            print("  !! NISQA 失败：%s（继续跑 seg_drift）" % e, file=sys.stderr)

    seg = {}
    if not a.no_seg:
        print("  seg_drift ...", flush=True)
        import mt_seg_drift as D
        for i, f in enumerate(files):
            try:
                seg[f] = D.one(f)
            except Exception as e:  # noqa: BLE001
                seg[f] = dict(verdict="ERROR", error=str(e), events=[], windows=[], span={})
            if (i + 1) % 20 == 0:
                print("    %d/%d" % (i + 1, len(files)), flush=True)

    det = {}
    band = {}
    if not a.no_det:
        print("  detectors（条件化）...", flush=True)
        import mt_detectors as DET
        # ★ 2026-10-31：起伏判据的对照带必须是**自产**分布，不是真人带。
        #   真人带（_rhythm_bands.json，n=159）的 p05/p95 是 8.9/22.55，我们自己的
        #   中位就有 16.1 —— 拿真人带判自产 take，一开就会 7.7~10.2% 判 FIX_HIGH。
        #   门禁要问的是「这条相对我们自己是否异常」，所以用 _span_band_own.json（自产 822 条）。
        band = {}
        try:
            bs = json.load(open(os.path.join(ROOT, "_rhythm_bands.json"), encoding="utf-8"))
            band = dict(bs.get(a.role) or {})
        except Exception:  # noqa: BLE001
            pass
        try:
            own = json.load(open(os.path.join(ROOT, "_span_band_own.json"), encoding="utf-8"))
            if (own.get(a.role) or {}).get("energy_span"):
                band["energy_span"] = own[a.role]["energy_span"]
            else:
                # 该角色没有自产带 → 宁可 SKIP，也不能退回真人带（那是另一个问题：
                # 「像不像真人」，一开就 7.7% FIX_HIGH，会淹掉真信号）
                band.pop("energy_span", None)
        except Exception:  # noqa: BLE001
            band.pop("energy_span", None)
        ctx0 = dict(band=band, n=len(files))
        for i, f in enumerate(files):
            try:
                m = DET.acoustics(f, a.role)
                m["nisqa"] = nis.get(f)
                det[f] = DET.item_check(m, dict(ctx0, path=f, seg=seg.get(f),
                                          paused=bool(a.paused) or has_inserted_pause(f)))
            except Exception as e:  # noqa: BLE001
                det[f] = [dict(id="detectors", name="检测器", level="info",
                               verdict="ERROR", why=str(e)[:80])]
            if (i + 1) % 20 == 0:
                print("    %d/%d" % (i + 1, len(files)), flush=True)

    rows = []
    for f in files:
        n = nis.get(f) or {}
        s = seg.get(f) or {}
        why = []
        notes = []
        v = "PASS"
        d = dur.get(f, 0)
        # ★ 2026-10-31 二次修：NISQA 不再走独立分支直接写 v="FAIL"。那条分支绕过了
        #   level/escalate —— 一个 warn 级检测器因此能以最高档落判（860 条里 31 条正常
        #   take 被硬判 FAIL）。现在统一交给 det 的 nisqa_dis / nisqa_mos（m["nisqa"] 已塞入）。
        if n and d < NISQA_MIN_DUR and n["mos"] < MOS_FAIL:
            notes.append("NISQA mos %.2f（短句不定级）" % n["mos"])
        # 旧 seg 通道只出数据（span/events），不再单独升判定 —— 判定统一由 det.seg_drift 负责，
        # 否则同一次事件被算两遍。
        sv = s.get("verdict")
        if sv == "FAIL":
            notes.append("句内漂移 %d 事件" % len([e for e in s.get("events", []) if e["level"] == "FAIL"]))
        elif sv == "WARN":
            notes.append("句内漂移 %d 处待复核"
                         % len([e for e in s.get("events", []) if e["level"] == "WARN"]))
        dr = det.get(f) or []
        for x in dr:
            # ★ 按登记表的 escalate 决定「哪一档才影响外层」。
            #   以前是「只要是 WARN 就抬」，接上 seg_drift 后 WARN 率从 6% 冲到 60%
            #   （它把「孤立事件」算 WARN，而孤立事件在正常旁白里很常见）。
            #   ★ 缺省必须是 ["FAIL"]：少写一个字段就静默失去判定权，这个坑已经踩过一次。
            esc = x.get("escalate")
            if esc is None:
                esc = ["FAIL"]
            if x["verdict"] not in esc:
                continue
            if x["level"] == "veto" and x["verdict"] in ("FAIL", "FIX_LOW", "FIX_HIGH"):
                v = "FAIL"
                why.append("%s: %s" % (x["name"], x["why"]))
            elif v == "PASS":
                v = "WARN"
                why.append("%s: %s" % (x["name"], x["why"]))
        # ★ 2026-10-31：全部 SKIP 以前会被写成 PASS。现在记成 UNCHECKED ——
        #   「没测」和「测过且通过」必须可区分，否则报告里全是假绿。
        cov = dict(ran=0, total=len(dr), skip=0)
        if dr:
            import mt_detectors as _D
            cov = _D.coverage(dr)
            if cov["ran"] == 0 and v == "PASS":
                v = "UNCHECKED"
                why.append("全部检测器 SKIP（无一项可判）")
        rows.append(dict(file=f, name=os.path.basename(f), dur=round(d, 2),
                         verdict=v, why=why, det=dr, cov=cov, nisqa=n or None,
                         notes=notes,
                         seg=dict(verdict=sv, span=s.get("span"),
                                  events=s.get("events")) if s else None))

    from collections import Counter
    cnt = Counter(r["verdict"] for r in rows)
    print("\n%-14s %6s %6s %6s %6s  %s"
          % ("文件", "时长", "mos", "dis", "判定", "原因"))
    for r in sorted(rows, key=lambda x: {"FAIL": 0, "WARN": 1}.get(x["verdict"], 2)):
        n = r["nisqa"] or {}
        print("%-14s %6.2f %6s %6s %6s  %s"
              % (r["name"], r["dur"],
                 ("%.2f" % n["mos"]) if n else "-",
                 ("%.2f" % n["dis"]) if n else "-",
                 r["verdict"], " / ".join(r["why"]) or "-"))
    print("\n汇总 %s（共 %d 条）" % (dict(cnt), len(rows)))
    # ★ 2026-10-31：覆盖度必须打出来。SKIP 在汇总里和 PASS 一样"不占负分"，
    #   对白 28.8% 的句子 <2s、NISQA 对它们零信息 —— 不计入绿字就等于假装测过。
    try:
        _nis_ok = sum(1 for r in rows if (r.get("nisqa") or {}).get("mos") is not None
                      and (r.get("dur") or 0) >= NISQA_MIN_DUR)
        _short = sum(1 for r in rows if (r.get("dur") or 0) < NISQA_MIN_DUR)
        _ran1 = sum(1 for r in rows if (r.get("cov") or {}).get("ran", 0) >= 1)
        _ran3 = sum(1 for r in rows if (r.get("cov") or {}).get("ran", 0) >= 3)
        print("覆盖度：NISQA 定级 %d/%d（%d 条 <%.1fs 只记不定级）｜"
              "≥1 项检测 %d/%d｜≥3 项 %d/%d"
              % (_nis_ok, len(rows), _short, NISQA_MIN_DUR,
                 _ran1, len(rows), _ran3, len(rows)))
        from collections import Counter as _C
        _sk = _C()
        for r in rows:
            for d in (r.get("det") or []):
                if d["verdict"] == "SKIP":
                    _sk[d["id"]] += 1
        if _sk:
            print("未测（SKIP 最多的几项）：%s"
                  % "、".join("%s %d" % (k, v) for k, v in _sk.most_common(4)))
    except Exception:  # noqa: BLE001
        pass
    if nis:
        m = np.array([x["mos"] for x in nis.values()])
        dd = np.array([x["dis"] for x in nis.values()])
        print("NISQA：mos 中位 %.2f (min %.2f) | dis 中位 %.2f (min %.2f)"
              % (np.median(m), m.min(), np.median(dd), dd.min()))

    if a.out:
        json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
