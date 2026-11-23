# -*- coding: utf-8 -*-
"""word_times 带磁盘缓存（59 条全跑一次 ~2 分钟，迭代时不该重复付这个成本）。"""
import json
import os

CACHE = r'G:/_setup/_wt_cache.json'
_MEM = None


def _load():
    global _MEM
    if _MEM is None:
        _MEM = json.load(open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}
    return _MEM


def word_times_cached(wav):
    from transplant_prosody2 import word_times
    c = _load()
    st = os.stat(wav)
    key = '%s|%d|%d' % (os.path.basename(wav), st.st_size, int(st.st_mtime))
    if key in c:
        return [tuple(x) for x in c[key]]
    rw = word_times(wav)
    c[key] = [list(x) for x in rw]
    json.dump(c, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    return rw
