# -*- coding: utf-8 -*-
"""验证 CAM++ 在本项目音频上的区分力：参考音（真人）之间能不能分开。"""
import glob, itertools, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch123_segcheck as SC

os.environ.setdefault("SEGCHK_DIR", "D:/_segchk_calib")
os.makedirs(os.environ["SEGCHK_DIR"], exist_ok=True)
SC.SEGDIR = os.environ["SEGCHK_DIR"]

SRC = "_cloud_backup/voice_lib"
files = sorted(glob.glob(os.path.join(SRC, "*.wav")))
def who(p):
    return os.path.basename(p).split("_")[0]

embs = {}
for f in files:
    a, sr = SC.read_wav(f)
    d = len(a) / sr
    if d < 0.6:
        continue
    if d < SC.PAD_TO:
        a = np.tile(a, int(np.ceil(SC.PAD_TO / d)))
    p = os.path.join(SC.SEGDIR, "ref_" + os.path.basename(f))
    SC.write_wav(p, a, sr)
    embs[f] = SC.SPK.embed(p)

print("ref 可用 %d 条, 角色 %d 个" % (len(embs), len(set(who(f) for f in embs))))
same, diff = [], []
for f1, f2 in itertools.combinations(embs, 2):
    c = float(SC.SPK.cos(embs[f1], embs[f2]))
    (same if who(f1) == who(f2) else diff).append(c)
def st(n, a):
    if not a: print(n, "无样本"); return
    s = sorted(a)
    print("%-14s n=%-4d min %6.3f p10 %6.3f med %6.3f p90 %6.3f max %6.3f"
          % (n, len(s), s[0], s[int(len(s)*.1)], s[len(s)//2], s[int(len(s)*.9)], s[-1]))
st("同角色 ref", same)
st("异角色 ref", diff)
if same and diff:
    print("\n同角色 p10 %.3f | 异角色 p90 %.3f" % (sorted(same)[int(len(same)*.1)], sorted(diff)[int(len(diff)*.9)]))
    print("可分" if sorted(same)[int(len(same)*.1)] > sorted(diff)[int(len(diff)*.9)] else "不可分")
