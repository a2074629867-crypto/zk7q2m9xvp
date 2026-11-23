# -*- coding: utf-8 -*-
"""绕开 funasr 的整仓下载 bug：手动 snapshot，忽略 404 的 png。"""
import os, sys
os.environ.setdefault("MODELSCOPE_CACHE", "G:/_setup/models/ms")
from modelscope import snapshot_download

for mid, sub in [("iic/emotion2vec_plus_large", "e2v_large"),
                 ("iic/emotion2vec_plus_base", "e2v_base")]:
    try:
        p = snapshot_download(mid, cache_dir="G:/_setup/models/ms",
                              ignore_file_pattern=[r".*\.png$", r".*\.DS_Store$"])
        print("OK", mid, "->", p, flush=True)
    except Exception as e:
        print("FAIL", mid, repr(e)[:300], flush=True)
