# -*- coding: utf-8 -*-
import json, os, collections
import soundfile as sf
ROOT = r"G:\_setup"

got = set()
for ln in open(os.path.join(ROOT, "_accent_feat_old.jsonl"), encoding="utf-8"):
    got.add(json.loads(ln)["id"])
print("old 已产出 %d 条，含 c2_0191 = %s" % (len(got), "c2_0191" in got))
ch = collections.Counter(x.split("_")[0] for x in got)
print("按章分布:", dict(ch))

wl = json.load(open(os.path.join(ROOT, "_wl_words.json"), encoding="utf-8"))
wl = {os.path.basename(k).rsplit(".", 1)[0]: v for k, v in wl.items()}
print("\n抽样看 末词end 与 音频时长：")
for sid in ["c1_0001", "c1_0003", "c1_0007", "c2_0191", "c2_0304", "c3_0641"]:
    p = os.path.join(ROOT, "_audio_ch123/out", sid + ".wav")
    if not os.path.exists(p) or sid not in wl:
        print("  %s 缺" % sid); continue
    d = sf.info(p).duration
    w = wl[sid]["words"]
    print("  %-8s dur=%6.2f  首词start=%6.2f  末词end=%6.2f  词数=%d  超时长=%s"
          % (sid, d, float(w[0]["start"]), float(w[-1]["end"]), len(w),
             float(w[-1]["end"]) > d * 1.02))
