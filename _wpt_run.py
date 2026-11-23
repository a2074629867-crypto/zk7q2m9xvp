# -*- coding: utf-8 -*-
"""把 ASR 词级时间戳转成 Praat TextGrid（wpt 的输入格式），再批量跑 wavelet prosody labeller。

用法:
  python _wpt_run.py --make          # 只为 _stress_words.json 里的 wav 造 TextGrid
  python _wpt_run.py --run --n 3     # 跑前 n 条（试水）
  python _wpt_run.py --run           # 全量

输出: _wpt_out/<basename>.prom   （tab/逗号分隔：Basename,start,end,label,prominence,boundary）
"""
import argparse
import json
import os
import subprocess
import sys

SRC = "G:/_setup/_stress_words.json"
WPTPY = "G:/_setup/wpt_venv/Scripts/python.exe"
CFG = "G:/_setup/_wpt/mt.yaml"
TG_DIR = "G:/_setup/_wpt_tg"
OUT_DIR = "G:/_setup/_wpt_out"
TMP = "G:/_setup/_wpt_tmp"


def read_wav_dur(path):
    import wave
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
    return n / sr, sr, ch


def write_textgrid(path, dur, words):
    """写单 tier IntervalTier，tier 名必须是 words（config 里 annotation_tier）。"""
    ivs = []
    t = 0.0
    for w in words:
        s = max(0.0, float(w["start"]))
        e = min(dur, float(w["end"]))
        if e <= s:
            continue
        # 补空隙（停顿）为静音 interval
        if s - t > 1e-4:
            ivs.append((t, s, ""))
        ivs.append((s, e, w["w"]))
        t = e
    if dur - t > 1e-4:
        ivs.append((t, dur, ""))
    if not ivs:
        ivs = [(0.0, dur, "")]

    L = []
    L.append('File type = "ooTextFile"')
    L.append('Object class = "TextGrid"')
    L.append("")
    L.append("xmin = 0")
    L.append("xmax = %.6f" % dur)
    L.append("tiers? <exists>")
    L.append("size = 1")
    L.append("item []:")
    L.append("    item [1]:")
    L.append('        class = "IntervalTier"')
    L.append('        name = "words"')
    L.append("        xmin = 0")
    L.append("        xmax = %.6f" % dur)
    L.append("        intervals: size = %d" % len(ivs))
    for i, (s, e, txt) in enumerate(ivs, 1):
        L.append("        intervals [%d]:" % i)
        L.append("            xmin = %.6f" % s)
        L.append("            xmax = %.6f" % e)
        L.append('            text = "%s"' % txt.replace('"', "'"))
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


def do_make():
    os.makedirs(TG_DIR, exist_ok=True)
    d = json.load(open(SRC, encoding="utf-8"))
    n = 0
    miss = []
    for k, v in d.items():
        wav = k.replace("\\", "/")
        if not os.path.exists(wav):
            miss.append(wav)
            continue
        base = os.path.splitext(os.path.basename(wav))[0]
        dur, sr, ch = read_wav_dur(wav)
        # 子目录名加进文件名避免 seed 冲突（N0001 在 s42/s1234/srate 里都有）
        tag = os.path.basename(os.path.dirname(wav))
        name = "%s__%s" % (tag, base)
        write_textgrid(os.path.join(TG_DIR, name + ".TextGrid"), dur, v["words"])
        n += 1
    print("生成 TextGrid %d 个" % n)
    if miss:
        print("wav 缺失 %d 个，例：%s" % (len(miss), miss[:3]))


def build_items():
    """返回 [(wav, textgrid)]，名字对应。"""
    d = json.load(open(SRC, encoding="utf-8"))
    items = []
    for k, v in d.items():
        wav = k.replace("\\", "/")
        if not os.path.exists(wav):
            continue
        tag = os.path.basename(os.path.dirname(wav))
        base = os.path.splitext(os.path.basename(wav))[0]
        name = "%s__%s" % (tag, base)
        tg = os.path.join(TG_DIR, name + ".TextGrid")
        if os.path.exists(tg):
            items.append((wav, tg, name))
    return items


def do_run(n=None, njobs=1):
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    items = build_items()
    if n:
        items = items[:n]
    print("待跑 %d 条" % len(items))
    ok = fail = 0
    for i, (wav, tg, name) in enumerate(items, 1):
        # wpt 要求 wav 与 TextGrid 同名同目录，或 -a 指定标注目录且同名
        # 这里用软链会带来跨盘问题，直接复制到临时目录
        tmpw = os.path.join(TMP, name + ".wav")
        tmpt = os.path.join(TMP, name + ".TextGrid")
        import shutil
        if not os.path.exists(tmpw):
            shutil.copy2(wav, tmpw)
        if not os.path.exists(tmpt):
            shutil.copy2(tg, tmpt)
        r = subprocess.run([WPTPY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                            "-c", CFG, "-o", OUT_DIR, tmpw],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="ignore", timeout=600)
        target = os.path.join(OUT_DIR, name + ".prom")
        if os.path.exists(target):
            ok += 1
            if ok <= 3:
                print("  [%d] %s OK" % (i, name))
        else:
            fail += 1
            if fail <= 3:
                print("  [%d] %s FAIL" % (i, name))
                print("     stdout:", (r.stdout or "")[-400:])
                print("     stderr:", (r.stderr or "")[-600:])
        if i % 20 == 0:
            print("  ... %d/%d  成功 %d 失败 %d" % (i, len(items), ok, fail))
        # 清理临时 wav 省空间
        try:
            os.remove(tmpw)
        except OSError:
            pass
    print("完成：成功 %d 失败 %d" % (ok, fail))
    if ok:
        p = os.path.join(OUT_DIR, items[0][2] + ".prom")
        print("\n=== 样例输出 %s ===" % os.path.basename(p))
        with open(p, encoding="utf-8") as f:
            for i, line in enumerate(f):
                print("  " + line.rstrip())
                if i > 12:
                    break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--n", type=int, default=None)
    a = ap.parse_args()
    if a.make:
        do_make()
    if a.run:
        do_run(a.n)


if __name__ == "__main__":
    main()
