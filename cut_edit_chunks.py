# -*- coding: utf-8 -*-
"""切 dots.edit 用的分块源音频（真人原声 771.07~799.76s，按句边界分两块），
并切一个「更靠前」的参考音频（33.69~42.23s，8.54s）。全部 48k。"""
import re, json
from pathlib import Path
import numpy as np, soundfile as sf

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
OUT = Path("G:/_setup/dots_edit2")
LAB = Path("G:/_setup/gsv5probe/logs/mcconaughey_v6/2-name2text.txt")

rows = []
for line in LAB.read_text(encoding="utf-8").splitlines():
    p = line.split("\t")
    if len(p) < 4:
        continue
    m = re.search(r"_(\d+)_(\d+)\.wav$", p[0])
    if not m:
        continue
    rows.append((int(m.group(1)) / 32000, int(m.group(2)) / 32000, p[3].strip()))
rows.sort()
SR = sf.info(MASTER).samplerate

def cut(tag, s, e, sr_out=48000):
    txt = " ".join(t for (a, b, t) in rows if a >= s - 0.02 and b <= e + 0.02).strip()
    seg, _ = sf.read(MASTER, start=int(round(s * SR)), frames=int(round((e - s) * SR)), dtype="float32")
    if seg.ndim > 1:
        seg = seg.mean(1)
    if sr_out != SR:
        n = int(round(len(seg) * sr_out / SR))
        seg = np.interp(np.linspace(0, len(seg) - 1, n),
                        np.arange(len(seg), dtype=np.float64), seg).astype(np.float32)
    p = OUT / ("%s_%.2fs.wav" % (tag, len(seg) / sr_out))
    sf.write(str(p), seg, sr_out, subtype="PCM_16")
    (OUT / ("%s.txt" % tag)).write_text(txt, encoding="utf-8")
    print("%-14s %7.2f~%7.2f  %.2fs  %2d词 | %s" % (tag, s, e, len(seg) / sr_out, len(txt.split()), txt[:76]))
    return dict(tag=tag, s=s, e=e, dur=len(seg) / sr_out, path=str(p), text=txt)

res = []
res.append(cut("C1_src", 771.07, 786.20))   # 15.13s
res.append(cut("C2_src", 786.86, 799.76))   # 12.90s
res.append(cut("REF_early", 33.69, 42.23))  # 8.54s 参考（早段）
json.dump(res, open(OUT / "chunks.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
