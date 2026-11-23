# -*- coding: utf-8 -*-
"""一次性验证：<rate, factor=0.70> 到底有没有把 died 拉长。

单条绝对时长不可比（整句会重新表演），唯一判据是 rel_z（句内归一词时长 z）。
链路：ASR 词级时间戳 → TextGrid → wpt(prom) → _align_lib.measure_take → rel_z。
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, "G:/_setup")
import _align_lib as L
from _wpt_run import write_textgrid

TEXT = ("Three months ago, his grandmother died, and then they had moved "
        "to this house.")
TG_DIR = "G:/_setup/_wpt_tg"
TMP = "G:/_setup/_wpt_tmp"
OUT_DIR = "G:/_setup/_wpt_out"
WPTPY = "G:/_setup/wpt_venv/Scripts/python.exe"
CFG = "G:/_setup/_wpt/mt.yaml"

PAIRS = [("stress_marked", "G:/_setup/_stress_smoke/c1_0001.wav"),
         ("stress_base", "G:/_setup/_stress_smoke_base/c1_0001.wav")]
TARGET = "died"

for d in (TG_DIR, TMP, OUT_DIR):
    os.makedirs(d, exist_ok=True)

# ---------- 1. ASR ----------
import _asr_lib
wavs = [p for _, p in PAIRS]
res = _asr_lib.transcribe(wavs)
asr = {}
for tag, wav in PAIRS:
    d = res.get(wav) or (list(res.values())[0] if res else {})
    asr[tag] = d
    print("[asr] %-14s dur=%.2f words=%d" % (tag, d.get("dur") or 0,
                                             len(d.get("words") or [])))

# ---------- 2. TextGrid + wpt ----------
prom = {}
for tag, wav in PAIRS:
    d = asr[tag]
    tg = os.path.join(TG_DIR, tag + ".TextGrid")
    write_textgrid(tg, d["dur"], d["words"])

    tmpw = os.path.join(TMP, tag + ".wav")
    tmpt = os.path.join(TMP, tag + ".TextGrid")
    shutil.copy2(wav, tmpw)
    shutil.copy2(tg, tmpt)
    r = subprocess.run([WPTPY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                        "-c", CFG, "-o", OUT_DIR, tmpw],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore", timeout=900)
    target = os.path.join(OUT_DIR, tag + ".prom")
    if not os.path.exists(target):
        print("[wpt] %s FAIL\n  %s" % (tag, (r.stdout or "")[-300:] + (r.stderr or "")[-500:]))
        continue
    prom[tag] = target
    print("[wpt] %-14s prom OK" % tag)
    try:
        os.remove(tmpw)
    except OSError:
        pass

# ---------- 3. measure + rel_z ----------
bl = L.load_baseline()
print("\nbaseline: n_words=%s A=%.4f B=%.4f SD=%.4f"
      % (bl.get("n_words"), bl["A"], bl["B"], bl["SD"]))
print("\n%-14s %8s %8s %8s %6s" % ("take", "died_s", "died_rel", "died_rel_z", "rank"))
rows = {}
for tag, _wav in PAIRS:
    if tag not in prom:
        continue
    rec = L.measure_take(PAIRS[[t for t, _ in PAIRS].index(tag)][1], prom[tag], TEXT)
    if not rec:
        print("%-14s 测量失败（内容词不足）" % tag)
        continue
    L.apply_rel_z(rec, bl)
    hit = None
    for w in rec["words"]:
        if str(w.get("key", "")).lower() == TARGET:
            hit = w
            break
    if not hit:
        print("%-14s 词表里没有 %s：%s"
              % (tag, TARGET, [w.get("key") for w in rec["words"]]))
        continue
    rows[tag] = hit
    print("%-14s %8.3f %8.3f %8.2f %3d/%d"
          % (tag, hit["span"], hit["rel"], hit["rel_z"] or 0,
             hit["rank"], rec["n_content"]))

if len(rows) == 2:
    a = rows["stress_marked"]["rel_z"]
    b = rows["stress_base"]["rel_z"]
    print("\nΔ rel_z（带标签 − 无标签）= %+.2f" % ((a or 0) - (b or 0)))
    print("判据 REL_Z_OK=1.6：带标签 %s / 无标签 %s"
          % ("PASS" if (a or 0) >= 1.6 else "未达",
             "PASS" if (b or 0) >= 1.6 else "未达"))

json.dump({k: {kk: v[kk] for kk in ("span", "rel", "rel_z", "rank")}
           for k, v in rows.items()},
          open("G:/_setup/_tmp_stress_verify.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n写出 G:/_setup/_tmp_stress_verify.json")
