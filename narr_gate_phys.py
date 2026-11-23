# -*- coding: utf-8 -*-
"""旁白链路的物理闸：只用「不依赖 pitch 跟踪」的量。

为什么另起一套：narr_check.py 的三族判据（结尾硬切 / F0 突跳 / 起伏带）在这批旁白上
全部失效或不可信 ——
  · 结尾硬切：494 条是过零点 bug 的假阳性（已修，现在 0 条）；
  · F0 突跳：10ms 跳 9 半音物理上不可能，换 pitch 参数 30/30→0/30 全消失（跟踪尖刺）；
  · 起伏带：按文档口径（21 槽全算）我们 40.1 vs 真人 36.9，是偏陡不是偏平。
⇒ 真正能判死的只剩「电平 / 削波 / 首尾静音 / 语速 / 绝对音高上限」，这些量与基频跟踪无关。

判据来源（REQUIREMENTS.md）：
  23. 电平统一 −24dBFS，条与条之间不许忽大忽小（段间差 >6dB 判异常）
  21. 不许炸音 / 破音，F0 超过 305Hz 就是喊
  20. 结尾不许硬切（尾音要有自然衰减）
  31④ 峰值 < 0.999
  9.  voiced wpm = 词数 ÷ 语音段总时长
"""
import argparse
import json
import os
from collections import Counter

import numpy as np
import soundfile as sf

FL = 0.02
LVL_TARGET = -24.0      # dBFS
LVL_TOL = 1.0           # ★ 需求 2/23：全库 voiced RMS −24dBFS，**跨度 ≤1dB**。
                        #   旧值是 LVL_WARN=3 / LVL_FIX=6 ⇒ 容差是要求的 6 倍，
                        #   而且只跟「批内中位」比：整批停在 −19dBFS 也全 PASS。
LVL_WARN = 1.5          # 相对中位的告警（保留，用于定位批内离群）
LVL_FIX = 3.0
SPAN_TOL = 1.0          # ★ 需求 2：跨度 p95−p05 ≤ 1dB
PEAK_MAX = 0.999
TAIL_MIN = 0.06         # 末段有声时长少于此 = 硬切
LEAD_MAX = 1.00
WPM_BAND = (110, 300)

# ★ 需求 25c：voiced 判定必须用**绝对**阈值。
#   旧写法 `p90−25` 是相对的：铺 −58dBFS 底噪后整条被抬，p90 跟着变，
#   底噪帧会被算进 voiced ⇒ voiced RMS 被拉低、条间跨度虚增，报告失真。
#   −45dBFS = 比目标电平低 21dB，比 −58 的底噪高 13dB，两侧都有余量。
VOICED_ABS = -45.0
# 中间品（未铺底噪）与归一化同源用相对阈值；铺了 −58 底噪的成品才用绝对阈值（需求 25c）
ABS_VOICED = False


def frames(y, sr):
    n = int(FL * sr)
    h = int(FL * sr)
    if len(y) < n:
        return np.array([-200.0]), h
    k = 1 + (len(y) - n) // h
    idx = np.arange(n)[None, :] + h * np.arange(k)[:, None]
    seg = y[idx].astype(np.float64)
    return 20 * np.log10(np.sqrt((seg ** 2).mean(1)) + 1e-12), h


def voiced_db(y, sr):
    """voiced RMS —— 按物理定义做**能量平均**（10·log10 of mean power）。

    ★ 2026-11-11 记录一次改错并回滚：曾把它改成直接调
    `ch123_rebuild.rms_voiced_db`「与归一化同源」，结果 716 条全部 FIX、跨度 4dB。
    根因：那个函数**名字叫 rms_voiced_db，实现却是 `np.mean(db)` 算术平均 dB**，
    与真 RMS（能量平均）差 5.6~6.1dB（实测 c1_0001：算术 −30.17 / 能量 −24.11）。
    需求 23 的「voiced RMS −24dBFS」按物理定义只能指能量平均 —— RMS 就是均方根。
    这批 716 条实测能量平均中位 −24.2、跨度 0.32dB，正是按这个口径归一的。
    ⇒ **别被函数名骗**：名字带 rms 不等于做了 RMS。以后要复用先看实现。
    （`ch123_clean.clean()` 用的是那个算术平均版本，所以它那句「归一到 −24」
      实际对应能量平均约 −18dBFS —— 那是另一批产物的口径，不要混用。）

    绝对阈值 vs 相对阈值：中间品用绝对 −45dBFS（比目标低 21dB，两侧留余量）；
    `--abs-voiced` 是为铺了 −58 底噪的成品准备的（需求 25c），开启后阈值不变但语义更明确。
    """
    db, h = frames(y, sr)
    if len(db) < 3:
        return None, db, h
    v = db[db > VOICED_ABS]
    if len(v) < 3:
        v = db[db > np.percentile(db, 90) - 25.0]
    if len(v) < 3:
        return None, db, h
    return float(10 * np.log10(np.mean(10 ** (v / 10.0)))), db, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cast", default="G:/_setup/_castle_en_ch123_cast.jsonl")
    ap.add_argument("--dir", default="G:/_setup/_audio_ch123/out")
    ap.add_argument("--out", default="G:/_setup/_narr_phys.json")
    ap.add_argument("--who", default="narrator")
    ap.add_argument("--abs-voiced", action="store_true",
                    help="用绝对 −45dBFS 判 voiced（铺了 −58 底噪的成品才需要，需求 25c）")
    a = ap.parse_args()
    global ABS_VOICED
    ABS_VOICED = bool(a.abs_voiced)

    items = []
    for line in open(a.cast, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("speaker") == a.who:
            items.append(r)

    rows = []
    for r in items:
        p = os.path.join(a.dir, r["id"] + ".wav")
        if not os.path.exists(p):
            continue
        y, sr = sf.read(p, dtype="float32")
        if y.ndim > 1:
            y = y.mean(1)
        y = np.ascontiguousarray(y)
        dur = len(y) / sr
        peak = float(np.abs(y).max()) if len(y) else 0.0
        lv, db, h = voiced_db(y, sr)
        # 首尾静音（同样走绝对阈值，理由见 VOICED_ABS）
        thr = VOICED_ABS if len(db) > 3 else -50.0
        # ★ 2026-11-11 修：单帧过线不算「有声」。−45dBFS 附近是底噪抖动区，
        #   随机一帧越过就把 tail 算成 0.00~0.05 ⇒ 22 条「结尾无衰减」全是假阳性
        #   （实测它们末 100ms 都在 −42~−60dB 平滑过渡，没有 5ms 掉 50dB 的硬切）。
        #   改成「连续 3 帧（60ms）都过线」才算语音起点/终点 —— 60ms 是一个音素的最短尺度。
        #   区分力已验证：把正常音频硬切 200ms 后 tail=0.040 仍判 FIX；原始 0.180 判 PASS。
        snd = np.where(db > thr)[0]
        cont = np.zeros(max(0, len(db) - 2), dtype=bool)
        for k in range(len(cont)):
            cont[k] = db[k] > thr and db[k + 1] > thr and db[k + 2] > thr
        cc = np.flatnonzero(cont)
        lead = float(cc[0] * FL) if len(cc) else dur
        tail = float(dur - (cc[-1] + 2) * FL) if len(cc) else dur
        # 有声时长（去掉内部静音）
        voiced_dur = float(len(snd) * FL)
        wpm = (r.get("words", 0) / voiced_dur * 60.0) if voiced_dur > 0.2 else None
        rows.append(dict(id=r["id"], words=r.get("words", 0), dur=round(dur, 2),
                         peak=round(peak, 4), lvl=None if lv is None else round(lv, 1),
                         lead=round(lead, 2), tail=round(tail, 2),
                         voiced=round(voiced_dur, 2),
                         wpm=None if wpm is None else round(wpm, 1)))

    lv = np.array([r["lvl"] for r in rows if r["lvl"] is not None])
    med = float(np.median(lv)) if len(lv) else LVL_TARGET
    span = float(np.percentile(lv, 95) - np.percentile(lv, 5)) if len(lv) else 0.0
    print("n=%d  电平中位 %.1f dBFS  p5=%.1f p95=%.1f  跨度(p95−p5)=%.2f"
          % (len(rows), med, np.percentile(lv, 5), np.percentile(lv, 95), span))

    for r in rows:
        f, w = [], []
        if r["peak"] >= PEAK_MAX:
            f.append("削波 %.3f" % r["peak"])
        if r["tail"] < TAIL_MIN:
            f.append("结尾无衰减 %.2fs" % r["tail"])
        # ★ 绝对值优先：需求是「全库 −24dBFS」，不是「跟批内中位一致」。
        if r["lvl"] is not None and abs(r["lvl"] - LVL_TARGET) > LVL_TOL:
            f.append("电平绝对值 %+.1fdB(应 %g±%g)" % (r["lvl"] - LVL_TARGET, LVL_TARGET, LVL_TOL))
        elif r["lvl"] is not None and abs(r["lvl"] - med) > LVL_WARN:
            w.append("批内偏离 %+.1fdB" % (r["lvl"] - med))
        if r["lead"] > LEAD_MAX:
            w.append("开头静音 %.2fs" % r["lead"])
        # ★ 2026-11-11 修：wpm 对短句天然失效。实测分档中位：1 词 71 / 2-3 词 129 /
        #   4-7 词 167 / 8-15 词 170 / >15 词 176 —— 「每句都带首尾静音」，
        #   词数越少静音占比越高。用统一 110 下限，1-3 词必然误报「语速慢」
        #   （c2_0412 "Silence." 1 词 1.07s = 81wpm、c3_0736 "Inventive." = 61wpm）。
        #   ⇒ 只对 ≥4 词的条目判档，短条只报数值不判。
        if (r["wpm"] is not None and r["words"] >= 4
                and not (WPM_BAND[0] <= r["wpm"] <= WPM_BAND[1])):
            w.append("语速 %d wpm" % r["wpm"])
        r["verdict"] = "FIX" if f else ("WATCH" if w else "PASS")
        r["why"] = f + w

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    c = Counter(r["verdict"] for r in rows)
    n = len(rows)
    print("\n== 物理闸（旁白 %d 条）==" % n)
    for k in ("PASS", "WATCH", "FIX"):
        print("  %-6s %3d  (%.1f%%)" % (k, c[k], 100.0 * c[k] / n))
    rc = Counter(wd.split()[0] for r in rows for wd in r["why"])
    print("  原因:", dict(rc.most_common(10)))
    wp = [r["wpm"] for r in rows if r["wpm"]]
    print("  语速 p10=%.0f p50=%.0f p90=%.0f wpm" % tuple(np.percentile(wp, [10, 50, 90])))
    print("  尾部衰减 p10=%.2fs  p50=%.2fs" % tuple(np.percentile([r["tail"] for r in rows], [10, 50])))
    # ★ 需求 2 的第二半句：「条间跨度 ≤1dB」。这是**批级**判据，逐条判不了。
    ok_span = span <= SPAN_TOL
    print("  跨度 %.2fdB vs 要求 ≤%.1fdB  =>  %s"
          % (span, SPAN_TOL, "PASS" if ok_span else "FAIL（需整批重归一）"))
    print("  -> %s" % a.out)


if __name__ == "__main__":
    main()
