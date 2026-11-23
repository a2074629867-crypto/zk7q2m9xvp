# -*- coding: utf-8 -*-
"""_proso_tg.py —— 用我们自己的词级对齐生成 Prosogram 需要的 TextGrid。

    G:/Python310/python.exe _proso_tg.py N0005            # 单条冒烟
    G:/Python310/python.exe _proso_tg.py --smoke 20       # 10 delivered + 10 ctl
    G:/Python310/python.exe _proso_tg.py --all            # 全量 403

为什么不用 Prosogram 的「自动分割音节核」：
它靠强度峰猜边界；我们的 wpt 对齐已经有精确词边界 + cmudict 音节数，
只要按音节数把词跨度等分，就能给它一个比它自己猜得更准的 `syll` tier。
Prosogram 的分段方式选 `Nuclei in syllables in "syll" and local peak`
（选项 6），音节核仍由它在区间内找强度峰 —— 这一步交给它，边界用我们的。

产物：_proso_in/<安全文件名>.wav + .TextGrid
安全文件名：把 gid/kind/seed 里的冒号斜杠换成下划线，映射写 _proso_map.json。
"""
import json
import os
import re
import shutil
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: os.path.join(ROOT, *p)
IN_DIR = os.environ.get("PROSO_DIR") or J("_proso_in")


def wav_dur(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def safe_name(tid):
    """tid = gid|kind|seed|md5 -> 只留字母数字和短横，避免 Praat 对冒号/竖线的处理问题。"""
    s = re.sub(r"[^0-9A-Za-z]+", "_", tid).strip("_")
    return s


def write_tg(path, xmax, intervals):
    """Praat 长文本格式 TextGrid，单层 IntervalTier，名字必须是 syll。"""
    L = []
    A = L.append
    A('File type = "ooTextFile"')
    A('Object class = "TextGrid"')
    A("")
    A("xmin = 0")
    A("xmax = %.6f" % xmax)
    A("tiers? <exists>")
    A("size = 1")
    A("item []:")
    A("    item [1]:")
    A('        class = "IntervalTier"')
    A('        name = "syll"')
    A("        xmin = 0")
    A("        xmax = %.6f" % xmax)
    A("        intervals: size = %d" % len(intervals))
    for i, (t0, t1, txt) in enumerate(intervals, 1):
        A("        intervals [%d]:" % i)
        A("            xmin = %.6f" % t0)
        A("            xmax = %.6f" % t1)
        A('            text = "%s"' % txt)
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")


def syll_intervals(rec):
    """每个词按 nsyl 等分成音节区间。空档（词间停顿）不建区间 —— Prosogram 只在区间内找核。"""
    out = []
    for w in rec["words"]:
        if not w.get("t0") or not w.get("t1"):
            continue
        n = max(1, int(w.get("nsyl") or 1))
        t0, t1 = float(w["t0"]), float(w["t1"])
        step = (t1 - t0) / n
        key = (w.get("key") or "syl").replace('"', "")
        for i in range(n):
            out.append((t0 + i * step, t0 + (i + 1) * step, "%s%d" % (key, i + 1)))
    return out


# ---------------- 有声区间版（默认） ----------------
# 我们的 take 是气声（HNR ~2dB），词跨度里 60% 是静音。
# 直接拿整个词跨度当音节区间，Prosogram 在区间内找不到强度峰 -> 只出 1~2 个核。
# 做法：先把词跨度按音节等分，再把每个分片收缩到它内部的「有声帧」范围，
# 并把自算的 Pitch 存成 .Pitch 让 Prosogram 直接读（默认阈值只认 12% 的帧）。

VT = 0.20          # Praat 默认 0.45 对气声太严；0.20 能把有声帧从 12% 提到 30%
F0_LO, F0_HI = 60, 250


def build_pitch(wav_path, out_pitch):
    """算 Pitch 并写成 Praat 文本格式，供 Prosogram 复用（它会优先读同目录 .Pitch）。"""
    import parselmouth
    snd = parselmouth.Sound(wav_path).resample(16000)
    pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=F0_LO, pitch_ceiling=F0_HI,
                          voicing_threshold=VT)
    parselmouth.praat.call(pit, "Save as text file", out_pitch)
    return pit


def voiced_intervals(rec, pit):
    """音节区间 = 词内按音节等分后，收缩到分片里真正有声的那一段。"""
    import numpy as np
    t = pit.xs()
    f = pit.selected_array["frequency"]
    out = []
    for w in rec["words"]:
        if not w.get("t0") or not w.get("t1"):
            continue
        n = max(1, int(w.get("nsyl") or 1))
        t0, t1 = float(w["t0"]), float(w["t1"])
        step = (t1 - t0) / n
        key = (w.get("key") or "syl").replace('"', "")
        for i in range(n):
            a, b = t0 + i * step, t0 + (i + 1) * step
            m = (t >= a) & (t <= b) & (f > 0)
            if m.sum() < 3:          # 少于 30ms 有声，放弃这一片
                continue
            idx = np.where(m)[0]
            out.append((float(t[idx[0]]), float(t[idx[-1]]), "%s%d" % (key, i + 1)))
    return out


def pick(records, mode):
    narr = [r for r in records if r["side"] == "narr"]
    hum = [r for r in records if r["side"] == "human"]
    if mode == "all":
        return hum + narr
    d = [r for r in narr if (r["take"] or {}).get("kind") == "delivered"]
    c = [r for r in narr if (r["take"] or {}).get("kind") == "ctl"]
    n = int(mode)
    half = max(1, n // 2)
    return d[:half] + c[:half]


def main():
    args = sys.argv[1:]
    mode = "20"
    only = None
    if args:
        if args[0] in ("--all", "--span"):
            mode = "all"
        elif args[0].startswith("--"):
            mode = args[1] if len(args) > 1 else "20"
        else:
            only = args[0]

    d = json.load(open(J("_align_dataset.json"), encoding="utf-8"))
    recs = [r for r in d["records"] if r["side"] == "narr"]
    if only:
        recs = [r for r in recs if only in r["gid"] and (r["take"] or {}).get("kind") == "delivered"]
        recs = recs[:1]
    else:
        recs = pick(d["records"], mode)

    os.makedirs(IN_DIR, exist_ok=True)
    mp = {}
    n_ok = 0
    use_span = "--span" in sys.argv
    for r in recs:
        wav = os.path.join(ROOT, r["wav"])
        if not os.path.exists(wav):
            print("  缺 wav:", r["wav"])
            continue
        name = safe_name(r["tid"])
        dst_wav = os.path.join(IN_DIR, name + ".wav")
        shutil.copy2(wav, dst_wav)
        pit = build_pitch(dst_wav, os.path.join(IN_DIR, name + ".Pitch"))
        iv = syll_intervals(r) if use_span else voiced_intervals(r, pit)
        if len(iv) < 2:
            print("  区间太少，跳过:", r["tid"], len(iv))
            continue
        write_tg(os.path.join(IN_DIR, name + ".TextGrid"), wav_dur(dst_wav), iv)
        mp[name] = dict(tid=r["tid"], gid=r["gid"], kind=(r["take"] or {}).get("kind"),
                        seed=(r["take"] or {}).get("seed"), adv=r["adv"],
                        wav=r["wav"], n_syll=len(iv),
                        n_syll_cmu=sum(max(1, int(w.get("nsyl") or 1)) for w in r["words"]))
        n_ok += 1

    json.dump(mp, open(J("_proso_map.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→ _proso_in/ %d 组 wav+TextGrid，映射 _proso_map.json" % n_ok)
    print("  音节区间合计 %d" % sum(v["n_syll"] for v in mp.values()))
    if mp:
        k = next(iter(mp))
        print("  例：%s  ←  %s" % (k, mp[k]["tid"]))


if __name__ == "__main__":
    main()
