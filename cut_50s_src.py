# -*- coding: utf-8 -*-
"""切《Wonder》50s 之后的段落作为 dots.edit 源音频（48k），按句边界分 3 块。"""
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

def cut(tag, s, e):
    txt = " ".join(t for (a, b, t) in rows if a >= s - 0.02 and b <= e + 0.02).strip()
    seg, _ = sf.read(MASTER, start=int(round(s * SR)), frames=int(round((e - s) * SR)), dtype="float32")
    if seg.ndim > 1:
        seg = seg.mean(1)
    n = int(round(len(seg) * 48000 / SR))
    y = np.interp(np.linspace(0, len(seg) - 1, n),
                  np.arange(len(seg), dtype=np.float64), seg).astype(np.float32)
    p = OUT / ("%s_%.2fs.wav" % (tag, len(y) / 48000))
    sf.write(str(p), y, 48000, subtype="PCM_16")
    (OUT / ("%s.txt" % tag)).write_text(txt, encoding="utf-8")
    dur = len(y) / 48000
    print("%-6s %7.2f~%7.2f  %.2fs  %2d词  mt=%d | %s" % (
        tag, s, e, dur, len(txt.split()), int(round(dur * 25)), txt[:76]))
    return dict(tag=tag, s=s, e=e, dur=dur, path=str(p), text=txt,
                max_tokens=int(round(dur * 25)))

res = []
res.append(cut("P1", 50.91, 65.59))   # A stock of prized possessions ... on the wall.
res.append(cut("P2", 66.53, 80.52))   # Green birds ... for good measure.
res.append(cut("P3", 81.36, 93.79))   # She knew ... sleeping soundly.
json.dump(res, open(OUT / "s50_src.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print()
print("真实间隙：65.59-66.53 = %.2fs ; 80.52-81.36 = %.2fs" % (66.53-65.59, 81.36-80.52))
print("总源长 %.2fs" % (93.79 - 50.91))
