"""mt_verify.py —— 前三章成品端到端验证（2026-10-21）

A. 计划层    对白残留（‘’/“” 成对引号）/ 脏字符 / 重复 id
B. 装配校验  用 mt_post 的同一套缓存键重建期望波形，与成品逐样本比对
C. 时间轴    每个单元的期望起止 vs 成品实测有声位置 + 段落间隙是否真静音
D. 电平      有声段 RMS / 5 分钟块跨度 / 峰值 / 削波
E. 语速      交付语速（处理后实测 voiced wpm）分布 + 10 分钟块平稳度
F. 音高      整章 F0 中位
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

ROOT = "G:/_setup"
PROC = os.path.join(ROOT, "_mt_proc")
PICK = os.path.join(ROOT, "_mt_pick")
OUTD = os.path.join(ROOT, "_mt_out")
SR = 48000
THR = -40.0

spec = importlib.util.spec_from_file_location("mp", os.path.join(ROOT, "mt_post.py"))
P = importlib.util.module_from_spec(spec)
_ARGV = sys.argv[:]                 # ★ 必须先存，否则 exec_module 里改 sys.argv 会吃掉本脚本的参数
sys.argv = ["mt_post.py"]
spec.loader.exec_module(P)
sys.argv = _ARGV


def frames_db(y, sr):
    w = int(0.02 * sr)
    n = len(y) // w
    z = y[:n * w].reshape(n, w)
    return 20 * np.log10(np.sqrt((z ** 2).mean(1)) + 1e-12)


def runs(mask, w=0.02):
    out, st = [], None
    for i, v in enumerate(mask):
        if v and st is None:
            st = i
        elif not v and st is not None:
            out.append((st * w, (i - st) * w))
            st = None
    if st is not None:
        out.append((st * w, (len(mask) - st) * w))
    return out


def cache_path(uid, target):
    """复刻 mt_post 的缓存键，拿到本次拼装实际使用的那一段。"""
    fp = os.path.join(PICK, uid + ".wav")
    if not os.path.exists(fp):
        return None
    t = P.line_tempo(0, 1)  # 占位，避免误用；下面按真实 wpm 重算
    return fp


def seg_of(uid, target, words):
    fp = os.path.join(PICK, uid + ".wav")
    if not os.path.exists(fp):
        return None, None, None
    wpm = P.voiced_wpm(fp, words)
    t = P.line_tempo(wpm, target, 1.0)
    key = "%s_%d_%d_%03d" % (uid, os.path.getsize(fp), int(os.path.getmtime(fp)), round(t * 100))
    cp = os.path.join(PROC, key + ".wav")
    if not os.path.exists(cp):
        # 缓存丢失：现场处理（与拼装时同参数），不写盘
        y, sr = P.process_one(fp, "verify_" + uid, t)
        return y, SR, t
    y, sr = sf.read(cp, dtype="float32", always_2d=True)
    return y.mean(1), sr, t


def check_plan(items):
    """成对引号才算对白残留；’ 夹在两个字母之间是撇号。"""
    dlg, dirty, dup = [], [], []
    seen = set()
    for p in items:
        t = p["text"]
        if p["id"] in seen:
            dup.append(p["id"])
        seen.add(p["id"])
        if "\u2018" in t or "\u201c" in t:
            dlg.append((p["id"], t[:70]))
        else:
            for m in re.finditer("\u2019|\u201d", t):
                i = m.start()
                prev = t[i - 1] if i > 0 else " "
                if not prev.isalpha():          # spiders’ webs 这种是所有格，不算对白
                    dlg.append((p["id"], t[:70]))
                    break
        if re.search(r"===|xhtml|第\s*\d+\s*节|[\u4e00-\u9fff]", t) or not t.strip():
            dirty.append((p["id"], t[:70]))
    return dlg, dirty, dup


def f0_med(y, sr):
    hop, win = int(0.02 * sr), int(0.04 * sr)
    lo, hi = int(sr / 400), int(sr / 70)
    out = []
    for i in range(0, len(y) - win, hop):
        f = y[i:i + win]
        if 20 * np.log10(np.sqrt((f ** 2).mean()) + 1e-12) < THR:
            continue
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[win - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        seg = ac[lo:hi]
        if len(seg) < 5 or seg.max() < 0.3:
            continue
        mx = seg.max()
        k = None
        for j in range(len(seg)):
            if seg[j] >= 0.85 * mx and seg[j] >= seg[j - 1] and (j + 1 >= len(seg) or seg[j] >= seg[j + 1]):
                k = j
                break
        out.append(sr / ((k if k is not None else int(np.argmax(seg))) + lo))
    return float(np.median(out)) if out else 0.0


def verify(ch, plan, target):
    items = [p for p in plan if p["ch"] == ch]
    print("=" * 70)
    print("【%s】%d 单元 / %d 词" % (ch, len(items), sum(len(p["text"].split()) for p in items)))

    dlg, dirty, dup = check_plan(items)
    print("  A 计划层：对白残留 %d | 脏字符 %d | 重复 id %d" % (len(dlg), len(dirty), len(dup)))
    for x in dlg[:6]:
        print("      对白 %s | %s" % x)
    for x in dirty[:3]:
        print("      脏字 %s | %s" % x)

    # ---- B/C：按拼装同一套键重建期望序列
    pieces, timeline = [], []
    t = 0.0
    for p in items:
        words = max(1, len(p["text"].split()))
        y, sr, tp = seg_of(p["id"], target, words)
        if y is None:
            pieces.append(np.zeros(int(0.01 * SR), dtype=np.float32))
            timeline.append((p["id"], t, 0, 1.0, 0.0, words))
            continue
        pieces.append(y)
        pieces.append(np.zeros(int(p["gap"] * SR), dtype=np.float32))
        vv = (frames_db(y, SR) > THR).sum() * 0.02
        timeline.append((p["id"], t, len(y) / sr, tp, words / max(vv, 0.1) * 60.0, words))
        t += len(y) / sr + p["gap"]
    exp = np.concatenate(pieces)

    m, sr = sf.read(os.path.join(OUTD, ch + ".wav"), dtype="float32", always_2d=True)
    m = m.mean(1)
    n = min(len(exp), len(m))
    a, b = exp[:n], m[:n]
    g = float(np.dot(a, b) / max(np.dot(a, a), 1e-9))     # 最佳增益
    err = np.abs(a * g - b)
    rms_sig = float(np.sqrt((b ** 2).mean()))
    corr = float(np.dot(a, b) / max(np.sqrt(np.dot(a, a) * np.dot(b, b)), 1e-12))
    print("  B 装配校验：期望 %.2f 秒 / 成品 %.2f 秒（差 %+.3f 秒）"
          % (len(exp) / SR, len(m) / sr, len(m) / sr - len(exp) / SR))
    print("      逐样本：增益 %.3f | 相关 %.6f | 误差 RMS %.1f dB（相对信号）| 最大误差 %.3f"
          % (g, corr, 20 * np.log10(np.sqrt((err ** 2).mean()) / rms_sig + 1e-12), float(err.max())))
    print("      误差 >0.02 的样本占比 %.4f%%（限幅器削峰处会差，属正常）"
          % float((err > 0.02).mean() * 100))
    del exp, a, b, err

    db = frames_db(m, sr)
    bad_gap, bad_seg = [], []
    for uid, st, d, tp, fw, wd in timeline:
        if d <= 0:
            continue
        i0, i1 = int((st + 0.06) / 0.02), int((st + d - 0.08) / 0.02)
        if i1 > i0 + 2:
            vf = (db[i0:i1] > THR).mean()
            if vf < 0.30:
                bad_seg.append((uid, round(st, 2), round(d, 2), round(vf, 2)))
        # 找这条的 gap（下一条的起点之前的静音）
        nxt = None
        for u2, s2, d2, _t2, _f2, _w2 in timeline:
            if s2 > st + 0.01:
                nxt = s2
                break
        if nxt:
            g0, g1 = int((st + d + 0.10) / 0.02), int((nxt - 0.05) / 0.02)
            if g1 > g0 + 2:
                sfr = float((db[g0:g1] > THR).mean())
                if sfr > 0.25:
                    bad_gap.append((uid, round(nxt - st - d, 2), round(sfr, 2)))
    print("  C 时间轴：该有语音却几乎无声 %d 条 | 段落间隙不够静 %d 处"
          % (len(bad_seg), len(bad_gap)))
    for x in bad_seg[:6]:
        print("        无声 %s @%.2fs 段长%.2f 有声比%.2f" % x)
    for x in bad_gap[:6]:
        print("        间隙 %s 计划%.2fs 有声比%.2f" % x)

    sil = [d for s, d in runs(db < THR) if 0.25 <= d <= 2.4]
    print("      实测间隙 %d 个：p10 %.2f / 中位 %.2f / p90 %.2f 秒"
          % (len(sil), np.percentile(sil, 10), np.median(sil), np.percentile(sil, 90)))

    # ---- D 电平
    v = db[db > THR]
    blk = []
    step = 5 * 60 * SR
    for i in range(0, len(m) - step // 2, step):
        d2 = frames_db(m[i:i + step], sr)
        vv = d2[d2 > THR]
        if len(vv) > 50:
            blk.append(20 * np.log10(np.sqrt(np.mean(10 ** (vv / 10))) + 1e-12))
    blk = np.array(blk)
    print("  D 电平：有声段 %.2f dB | 5 分钟块 %.2f~%.2f（跨 %.2f dB）| peak %.3f | 削波 %d"
          % (20 * np.log10(np.sqrt(np.mean(10 ** (v / 10))) + 1e-12),
             blk.min(), blk.max(), blk.max() - blk.min(), float(np.abs(m).max()),
             int((np.abs(m) > 0.999).sum())))

    # ---- E 语速：交付语速 = 处理后语音段上的 voiced wpm
    fin = np.array([t4 for _1, _2, d, _3, t4, _4 in timeline if d > 0])
    tp_used = np.array([t3 for _1, _2, d, t3, _4, _5 in timeline if d > 0])
    dev = np.abs(fin - target) / target
    print("  E 语速：交付 voiced wpm 中位 %.0f（目标 %.0f）| p10–p90 %.0f–%.0f | 最快 %.0f 最慢 %.0f"
          % (np.median(fin), target, np.percentile(fin, 10), np.percentile(fin, 90), fin.max(), fin.min()))
    print("      偏离 >10%% %d 条 | >20%% %d 条 | tempo 用例 %.2f~%.2f（未拉伸 %d 条）"
          % ((dev > .10).sum(), (dev > .20).sum(), tp_used.min(), tp_used.max(), (tp_used > .995).sum()))
    blocks = []
    for i in range(0, len(m) - 30 * SR, 10 * 60 * SR):
        d3 = frames_db(m[i:i + 10 * 60 * SR], sr)
        blocks.append((d3 > THR).mean())
    print("      10 分钟块有声占比：%s" % " ".join("%.0f%%" % (b * 100) for b in blocks))

    print("  F 音高：整章 F0 中位 %.0f Hz（基线 79）" % f0_med(m, sr))
    return {"ch": ch, "dur": len(m) / sr, "bad_seg": len(bad_seg), "bad_gap": len(bad_gap),
            "dlg": len(dlg), "dirty": len(dirty), "dup": len(dup),
            "corr": corr,
            "wpm": float(np.median(fin)), "peak": float(np.abs(m).max())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chs", default="ch1,ch2,ch3")
    ap.add_argument("--plan", default="mt_plan3b.json")
    a = ap.parse_args()
    plan = json.load(open(os.path.join(ROOT, a.plan), encoding="utf-8"))
    tgt = json.load(open(os.path.join(ROOT, "_mt_target.json"), encoding="utf-8"))
    out = []
    for ch in [c.strip() for c in a.chs.split(",") if c.strip()]:
        out.append(verify(ch, plan, tgt.get(ch, 190)))
    print("=" * 70)
    print("合计 %.2f 分钟 / %d 章" % (sum(o["dur"] for o in out) / 60, len(out)))
    print("%-5s %8s %9s %7s %6s %6s %6s %7s" % ("章", "时长", "装配相关", "语速", "无声", "间隙", "对白", "峰值"))
    for o in out:
        print("%-5s %8s %9.5f %7.0f %6d %6d %6d %7.3f"
              % (o["ch"], "%.1f分" % (o["dur"] / 60), o["corr"], o["wpm"],
                 o["bad_seg"], o["bad_gap"], o["dlg"], o["peak"]))
    bad = [o for o in out if o["bad_seg"] or o["dlg"] or o["dirty"] or o["dup"] or o["corr"] < 0.999]
    print("需处理的章：%s" % (", ".join(o["ch"] for o in bad) if bad else "无"))


if __name__ == "__main__":
    main()
