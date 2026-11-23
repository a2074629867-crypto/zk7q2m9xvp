# -*- coding: utf-8 -*-
"""measure_mc_prosody.py —— 从真人录音里量「麦康纳睡前朗读」的可编程韵律参数。

输出：
  1) 每个停顿间隙的时长 + 前后文（标点类型）
  2) 每个语音段的 wpm
  3) 句内 F0 弧线（首词 / 中段 / 末词的半音差）—— 决定 <pitch> 用多少
"""
import sys, json, re
import numpy as np, soundfile as sf

SR = 48000
P = sys.argv[1] if len(sys.argv) > 1 else "E:/tts-models/acpp/out/calmdeep_final/real_trim.wav"
TEXT = open(sys.argv[2], encoding="utf-8").read().strip() if len(sys.argv) > 2 else \
    open("G:/_setup/scene_calmdeep.txt", encoding="utf-8").read().strip()

x, sr = sf.read(P, dtype="float64", always_2d=True)
x = x.mean(1)
assert sr == SR, sr

# --- 能量 VAD（-35dB rel peak, 10ms） ---
hop = int(SR * 0.010)
n = len(x) // hop
fr = x[:n*hop].reshape(n, hop)
db = 20*np.log10(np.sqrt((fr**2).mean(1)) + 1e-12)
thr = db.max() - 35.0
sp = db > thr
# 平滑：<80ms 的洞填上，<120ms 的岛去掉
def smooth(m, min_gap=8, min_island=12):
    m = m.copy()
    i = 0
    while i < len(m):
        if not m[i]:
            j = i
            while j < len(m) and not m[j]: j += 1
            if i > 0 and j < len(m) and (j-i) < min_gap: m[i:j] = True
            i = j
        else: i += 1
    i = 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]: j += 1
            if (j-i) < min_island: m[i:j] = False
            i = j
        else: i += 1
    return m
sp = smooth(sp)

# --- 提取语音段与间隙 ---
segs, gaps = [], []
i = 0
while i < n:
    if sp[i]:
        j = i
        while j < n and sp[j]: j += 1
        segs.append((i*0.01, j*0.01)); i = j
    else:
        j = i
        while j < n and not sp[j]: j += 1
        if segs: gaps.append((i*0.01, j*0.01))
        i = j

words = TEXT.split()
print("真人 %s" % P.split("/")[-1])
print("总时长 %.2fs  语音段 %d  间隙 %d  文本 %d 词" % (len(x)/SR, len(segs), len(gaps), len(words)))
print()
print("=== 语音段（时长 / 分配的文本） ===")
tot_v = sum(b-a for a,b in segs)
print("语音总长 %.2fs  静音总长 %.2fs  语音占比 %.3f" % (tot_v, len(x)/SR-tot_v, tot_v/(len(x)/SR)))

# 按间隙大小把文本分配到段（假设每个间隙对应一个标点）
print()
print("=== 间隙序列 ===")
for k,(a,b) in enumerate(gaps):
    print("  #%d  %.3fs  @ %.2f~%.2f" % (k+1, b-a, a, b))
gs = np.array([b-a for a,b in gaps])
if len(gs):
    print("  间隙中位 %.3fs  max %.3fs  min %.3fs  总和 %.2fs" % (np.median(gs), gs.max(), gs.min(), gs.sum()))

# 标点统计
ncomma = TEXT.count(","); nper = TEXT.count(".")
print()
print("标点：逗号 %d  句号 %d" % (ncomma, nper))
print("若每个标点一个间隙：平均 %.3fs（逗号+句号共 %d 个，实测间隙 %d 个）" % (
    gs.sum()/max(1,ncomma+nper), ncomma+nper, len(gs)))

# --- F0 弧线：整段前 1/3 vs 后 1/3（按语音帧） ---
import parselmouth
snd = parselmouth.Sound(x.astype(np.float64), sampling_frequency=SR)
pit = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=400,
                      voicing_threshold=0.35, octave_jump_cost=1.0, octave_cost=0.01)
f0 = np.asarray(pit.selected_array["frequency"], dtype=np.float64)
t = np.asarray(pit.xs(), dtype=np.float64)
v = f0 > 0
f0v, tv = f0[v], t[v]
def st(a,b): return 12*np.log2(a/b)
if len(f0v) > 100:
    k = len(f0v)
    head = f0v[:k//5].mean(); mid = f0v[k*2//5:k*3//5].mean(); tail = f0v[-k//5:].mean()
    print()
    print("=== F0 弧线（整段） ===")
    print("  首20%% %.1f Hz  中段 %.1f Hz  末20%% %.1f Hz" % (head, mid, tail))
    print("  首→中 %.2f 半音   中→末 %.2f 半音   首→末 %.2f 半音" % (st(mid,head), st(tail,mid), st(tail,head)))
    print("  F0 中位 %.1f Hz  p10 %.1f  p90 %.1f  跨度 %.2f 半音" % (
        np.median(f0v), np.percentile(f0v,10), np.percentile(f0v,90),
        st(np.percentile(f0v,90), np.percentile(f0v,10))))
