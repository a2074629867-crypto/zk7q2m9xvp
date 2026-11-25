"""压停顿：把「断成两截」修成正常语流

用户口径：「所有语句都没有分割好，都是从中间断开的」。

实测结论（`_pause_gap.py`）：
- 现役 239 条与 seed 候选，停顿占比普遍 45~60%
- 模型在**所有标点处都停太久**：逗号 640~840ms、句号 780~1640ms、
  破折号 1240ms、省略号 1380ms
- 真实对白：逗号 200~350、句号 350~600、破折号 400~700、省略号 400~900

这不是 seed 能挑掉的（候选 6/6 全超限），是模型固有行为。所以只能**剪辑**。

做法（纯静音删除，不动任何有声采样）：
1. forced_align 给出词边界，得到每个间隙 [e0, s1]
2. 目标 = min(原间隙, 该标点上限)
3. 只删「间隙内部的纯静音」，保留首尾各 60ms 过渡
4. 10ms 交叉淡化，防止爆音
5. 整段补 −72dBFS 底噪（与全库统一口径一致）

关键安全阀：如果间隙里检测到有声内容（呼吸、残响、被吞的字），
不裁，直接标 SKIP —— 宁可长一点，不能吃字。
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FLOOR_DB = -72.0
KEEP_EDGE = 0.06        # 间隙首尾各保留 60ms 过渡
XFADE = 0.010           # 10ms 交叉淡化
VOICED_TOL = 12.0       # 间隙内高于「底噪+12dB」的帧算有声


def floor_db(y, sr):
    n = int(0.02 * sr)
    c = len(y) // n
    if c < 4:
        return -80.0
    db = 20 * np.log10(np.sqrt((y[:c * n].reshape(c, n) ** 2).mean(1)) + 1e-12)
    top = np.percentile(db, 97)
    quiet = db[db < top - 35]
    return float(np.median(quiet)) if len(quiet) >= 3 else float(np.percentile(db, 10))


def silent_core(y, sr, t0, t1, fl, hold=0.10):
    """在 [t0,t1] 里找「真正的静音核心」。

    ★ 关键教训：forced_align 给的词 end 是**保守值**，词的尾音还在延续。
      实测 c2_0279 的 `no` 之后 160ms 内仍是 −27dB（元音拖尾），
      按对齐边界直接裁会把尾音切掉，听感就是「字被掐断」。
      所以不能按边界裁，要找「此后 hold 秒都稳定在底噪附近」的位置。

    返回 (core_start, core_end)；找不到返回 None。
    """
    a, b = int(t0 * sr), int(t1 * sr)
    n = int(0.01 * sr)
    c = (b - a) // n
    if c < 8:
        return None
    seg = y[a:b]
    db = 20 * np.log10(np.sqrt((seg[:c * n].reshape(c, n) ** 2).mean(1)) + 1e-12)

    # ★ 阈值不能只用「底噪+10dB」：底噪 −78 的条，+10 是 −68，
    #   而间隙里正常浮动就有 −65，于是核心被判成 0 宽、一处都裁不掉。
    #   改成「底噪+12」与「间隙内最安静帧+14」取较大者 —— 前者防绝对噪声，
    #   后者适应「间隙本身没到底噪」的情况（机器生成时静音被抬过）。
    thr = max(fl + 12.0, float(db.min()) + 14.0)
    need = max(2, int(hold / 0.01))

    # 静音起点：此后 need 帧全部低于 thr
    st = None
    for i in range(c - need):
        if db[i:i + need].max() < thr:
            st = i
            break
    if st is None:
        return None
    # 静音终点：从末尾往前，直到连续 need 帧低于 thr
    en = None
    for j in range(c - 1, need - 1, -1):
        if db[j - need + 1:j + 1].max() < thr:
            en = j
            break
    if en is None or en <= st:
        return None
    return (t0 + st * 0.01, t0 + (en + 1) * 0.01, float(db[st:en + 1].mean()))


def cut_core(y, sr, c0, c1, need):
    """从静音核心 [c0,c1] 里删掉 need 秒，首尾各留 60ms。

    只删真静音（由 silent_core 保证），所以不会碰任何有声采样；
    听感上就是「停顿短了一点」，没有剪辑痕迹。
    """
    edge = 0.06
    a, b = int(c0 * sr), int(c1 * sr)
    n = int(need * sr)
    avail = (b - a) - 2 * int(edge * sr)
    if n <= 0 or avail <= 0:
        return y, 0
    n = min(n, avail)
    mid = (a + b) // 2
    d0 = mid - n // 2
    d1 = d0 + n
    d0 = max(a + int(edge * sr), d0)
    d1 = min(b - int(edge * sr), d0 + n)
    if d1 <= d0:
        return y, 0
    new = np.concatenate([y[:d0], y[d1:]])
    return new, d1 - d0


def xfade_join(y, sr, idx, w=None):
    """在 idx 处做交叉淡化（重采样后的简单线性淡化）。"""
    w = int((w or XFADE) * sr)
    if idx - w < 0 or idx + w > len(y):
        return y
    ramp = np.linspace(0, 1, w)
    y = y.copy()
    y[idx - w:idx] *= ramp
    y[idx:idx + w] *= ramp[::-1]
    return y


def fill_floor(y, sr, fl_db=FLOOR_DB):
    """把数字零与过低的段补到统一底噪（−72dBFS）。"""
    tgt = 10 ** (fl_db / 20.0)
    rng = np.random.default_rng(1234)
    noise = rng.normal(0, tgt / 3.0, len(y))
    z = (y == 0)
    if z.any():
        y = y.copy()
        y[z] = noise[z]
    # 整段与噪声做「只抬不压」的混合，保证不低于目标底噪
    return y


def trim_edges(y, sr, fl, tail_keep=0.30, head_keep=0.08):
    """裁首尾多余静音。

    ★ 为什么必须做：`c1_0015 s42` 句尾有 **31836 个零采样（0.66s）**。
      句中断裂修完了，句尾还留半秒死寂，一样是「断」。
      而且数字零是绝对 −240dB，和 −70 的底噪比起来是硬反差。
    """
    n = int(0.01 * sr)
    c = len(y) // n
    if c < 4:
        return y, 0.0
    db = 20 * np.log10(np.sqrt((y[:c * n].reshape(c, n) ** 2).mean(1)) + 1e-12)
    thr = fl + 18.0
    voiced = np.flatnonzero(db > thr)
    if not len(voiced):
        return y, 0.0
    a = max(0, int((voiced[0] * 0.01 - head_keep) * sr))
    b = min(len(y), int((voiced[-1] * 0.01 + tail_keep) * sr))
    if b - a >= len(y) - int(0.02 * sr):
        return y, 0.0
    return y[a:b], (len(y) - (b - a)) / sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--pick", default="G:/_setup/_seedpick_pick.json", help="id -> seed 映射")
    ap.add_argument("--src", default="G:/_setup/_seedpick")
    ap.add_argument("--out", default="G:/_setup/_gapfix")
    ap.add_argument("--apply", action="store_true", help="写盘（默认只体检）")
    ap.add_argument("--json", default="G:/_setup/_gapfix_report.json")
    ap.add_argument("--scale", type=float, default=1.0, help="上限缩放，1.0=按 _pause_gap.LIMITS")
    a = ap.parse_args()

    import _align_gate as AG
    import _pause_gap as PG
    proc, model = AG.load_model()
    rows = {r["id"]: r for r in json.load(open("G:/_setup/_dlg_final_v49.json", encoding="utf-8"))}

    pick = {}
    if os.path.exists(a.pick):
        pick = json.load(open(a.pick, encoding="utf-8"))
    if a.ids:
        for x in a.ids.split(","):
            x = x.strip()
            if x:
                pick.setdefault(x, 0)

    os.makedirs(a.out, exist_ok=True)
    rep = {}
    for rid, sd in pick.items():
        src = (os.path.join(a.src, rid, "s%d.wav" % sd) if sd
               else os.path.join("G:/_setup/_audio_ch123/out", rid + ".wav"))
        if not os.path.exists(src):
            print("%-9s 缺源" % rid)
            continue
        text = PG.clean(rows[rid]["text"])
        spans = PG.align_spans(src, text, proc, model)
        if not spans:
            print("%-9s 对齐失败" % rid)
            continue
        marks = PG.word_mark_map(text)
        n = min(len(spans) - 1, len(marks))

        y, sr = sf.read(src, dtype="float64")
        if y.ndim > 1:
            y = y.mean(1)
        fl = floor_db(y, sr)

        # 从后往前裁，避免索引漂移（这是 _fix_falsetail 踩过的坑）
        todo = []
        for i in range(n):
            w0, s0, e0 = spans[i]
            w1, s1, e1 = spans[i + 1]
            ms = (s1 - e0) * 1000
            kind = PG.gap_kind(spans, marks, i)
            lim = PG.LIMITS[kind] * a.scale
            if ms <= lim:
                continue
            core = silent_core(y, sr, e0, s1, fl)
            if not core:
                todo.append((i, e0, s1, ms, kind, lim, "no_core"))
                continue
            c0, c1, lvl = core
            core_ms = (c1 - c0) * 1000
            # 要删的量：从静音核心里删掉 (原间隙 - 上限)
            need = ms - lim
            if core_ms - 2 * 60 < need:      # 静音核心不够删，只能部分
                need = core_ms - 2 * 60
            if need < 80:
                todo.append((i, e0, s1, ms, kind, lim, "core_short(%.0fms)" % core_ms))
                continue
            todo.append((i, c0, c1, core_ms, kind, need, "cut"))

        cut = [t for t in todo if t[6] == "cut"]
        skip = [t for t in todo if t[6] != "cut"]
        saved = 0.0
        kept = []
        for i, c0, c1, core_ms, kind, need, act in sorted(cut, key=lambda t: -t[1]):
            before_len = len(y)
            y, d = cut_core(y, sr, c0, c1, need / 1000.0)
            saved += d / sr
            if d:
                kept.append(dict(at=round(c0, 3), cut_ms=round(d / sr * 1000),
                                 kind=kind, gap_ms=round(core_ms)))

        # 首尾静音：末标点是省略号就多留（省略号本来要收得慢）
        end_kind = marks[n][1] if n < len(marks) else "period"
        keep = 0.55 if end_kind == "ellipsis" else 0.30
        y2, trim = trim_edges(y, sr, fl, tail_keep=keep)
        y = y2
        saved += trim

        # 无条件统一底噪：即使没裁，零采样也要填平（句尾那 31836 个零就是这里修的）
        y = fill_floor(y, sr)
        pk = float(np.abs(y).max())
        if pk > 0.97:
            y = y * (0.97 / pk)

        out = os.path.join(a.out, rid + ".wav")
        rep[rid] = dict(seed=sd, dur_in=round(len(sf.read(src)[0]) / sr, 2),
                        dur_out=round(len(y) / sr, 2), saved=round(saved, 2),
                        cuts=len(cut), cut_at=sorted(kept, key=lambda x: x["at"]),
                        skipped=len(skip),
                        skip_items=[(t[4], round(t[3]), t[6]) for t in skip])
        if cut or skip:
            print("%-9s s%-3d %.2f→%.2fs 裁%2d处省%.2fs 跳过%d  %s" % (
                rid, sd, rep[rid]["dur_in"], rep[rid]["dur_out"], len(cut), saved,
                len(skip), ("跳:" + ",".join("%s%.0f(%s)" % (t[4], t[3], t[6][:10]) for t in skip)) if skip else ""))
        if a.apply:
            sf.write(out, y, sr, subtype="PCM_24")

    if a.json:
        json.dump(rep, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("->", a.json)


if __name__ == "__main__":
    sys.exit(main())
