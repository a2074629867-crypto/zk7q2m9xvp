# -*- coding: utf-8 -*-
"""从原始母带切两段「更靠前」的 edit 源音频（32k -> 48k），并生成精确文本。
区域 A: 538.75~566.14s（紧邻现用参考 baseA 之前）
区域 B: 172.20~199.53s（整段录音早段）
"""
import re, json
from pathlib import Path
import numpy as np, soundfile as sf

MASTER = "G:/GPT-SoVITS/_dataset/wonder_train.wav"
OUT = Path("G:/_setup/dots_edit2")
LAB = Path("G:/_setup/gsv5probe/logs/mcconaughey_v6/2-name2text.txt")
SR_LAB = 32000

rows = []
for line in LAB.read_text(encoding="utf-8").splitlines():
    p = line.split("\t")
    if len(p) < 4:
        continue
    m = re.search(r"_(\d+)_(\d+)\.wav$", p[0])
    if not m:
        continue
    rows.append((int(m.group(1)) / SR_LAB, int(m.group(2)) / SR_LAB, p[3].strip()))
rows.sort()

info = sf.info(MASTER)
SR = info.samplerate
print("master sr=%d dur=%.2fs" % (SR, info.frames / SR))

def build(tag, s, e):
    # 只取完全落在 [s,e] 内的切片文本
    parts = [t for (a, b, t) in rows if a >= s - 0.02 and b <= e + 0.02]
    txt = " ".join(parts).strip()
    a0, a1 = int(round(s * SR)), int(round(e * SR))
    seg, _ = sf.read(MASTER, start=a0, frames=a1 - a0, dtype="float32")
    if seg.ndim > 1:
        seg = seg.mean(1)
    n = int(round(len(seg) * 48000 / SR))
    y = np.interp(np.linspace(0, len(seg) - 1, n),
                  np.arange(len(seg), dtype=np.float64), seg).astype(np.float32)
    p = OUT / ("SRC_%s_%.2fs.wav" % (tag, len(y) / 48000))
    sf.write(str(p), y, 48000, subtype="PCM_16")
    print("\n=== %s  %.2fs~%.2fs  -> %.2fs ===" % (tag, s, e, len(y) / 48000))
    print("文本(%d 词): %s" % (len(txt.split()), txt))
    (OUT / ("SRC_%s.txt" % tag)).write_text(txt, encoding="utf-8")
    return dict(tag=tag, s=s, e=e, dur=len(y) / 48000, path=str(p), text=txt)

res = []
res.append(build("A_early", 538.75, 566.14))
res.append(build("B_early", 172.20, 199.53))

TARGET = ("And heating into vapor. It is swirling in lakes. Swelling in oceans. "
          "And evaporating into skies. It is gathering into clouds. Raining down onto hills. "
          "Dripping down from leafy trees. Trickling into streams. Flowing down rivers,")
(OUT / "TARGET.txt").write_text(TARGET, encoding="utf-8")
print("\n=== 目标文本 (%d 词) ===\n%s" % (len(TARGET.split()), TARGET))
json.dump(res, open(OUT / "early_src.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
