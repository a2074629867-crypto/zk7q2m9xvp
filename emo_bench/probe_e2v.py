# -*- coding: utf-8 -*-
"""emotion2vec 可用性探针：能否加载 + 输出结构是什么。"""
import os, sys, time, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("MODELSCOPE_CACHE", "G:/_setup/models/ms")
os.environ.setdefault("HF_HOME", "G:/_setup/models/hf")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

t0 = time.time()
from funasr import AutoModel
print("[%.0fs] funasr imported" % (time.time() - t0), flush=True)

for name in ["iic/emotion2vec_plus_large", "iic/emotion2vec_plus_base"]:
    try:
        print("[%.0fs] loading %s ..." % (time.time() - t0, name), flush=True)
        m = AutoModel(model=name, disable_update=True, device="cpu")
        print("[%.0fs] loaded %s" % (time.time() - t0, name), flush=True)
        w = "G:/_setup/castle_fr_ref/1_charles_normal.wav"
        r = m.generate(w, granularity="utterance", extract_embedding=False)
        print("type", type(r))
        print(str(r)[:1200])
        break
    except Exception as e:
        print("FAIL %s: %r" % (name, e), flush=True)
