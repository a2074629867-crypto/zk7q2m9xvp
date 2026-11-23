# -*- coding: utf-8 -*-
"""重音闭环（旁白 716）：
文本侧 LLM 标注的 stress 词 -> 声学侧三轴实测 -> 判「该读没读」
三轴（不合并）：rel_z 时长 / loc F0 句内残差 / rms_x 能量
词时间戳用旧对齐 + 停顿增减量平移（语音未动，精确可算）
"""
import json, os, glob, statistics as st
import numpy as np, soundfile as sf
import parselmouth
from parselmouth.praat import call

OUT_DIR = 'G:/_setup/_ann/out_full/narr/ds'
WOLD = 'G:/_setup/_wl_words.json'
NEW = 'G:/_setup/_audio_ch123/out'
OLD = 'G:/_setup/_audio_ch123/out_bak_prepause'
THR = -35.0


# ---------- 1. LLM 标注 ----------
stress = {}
for f in sorted(glob.glob(OUT_DIR + '/*.json')):
    for it in json.load(open(f, encoding='utf-8'))['items']:
        stress[it['sid']] = it.get('stress') or []
print('有标注句', len(stress), '标注重读处', sum(len(v) for v in stress.values()))


# ---------- 2. 词时间戳平移 ----------
def gaps(y, sr):
    h = max(1, int(sr * 0.01))
    n = len(y) // h
    if n < 3:
        return []
    db = 20 * np.log10(np.sqrt((y[:n*h].reshape(n, h) ** 2).mean(1) + 1e-12) + 1e-12)
    v = db > THR
    idx = np.flatnonzero(v)
    if len(idx) < 2:
        return []
    a, b = idx[0], idx[-1]
    out = []
    i = a
    while i <= b:
        if not v[i]:
            j = i
            while j <= b and not v[j]:
                j += 1
            if (j - i) * 0.01 >= 0.40:
                out.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return out


wold = json.load(open(WOLD, encoding='utf-8'))
key = {sid: ('G:/_setup/_audio_ch123/out/%s.wav' % sid) for sid in stress}
rows = []
miss_ts = 0
for sid in stress:
    k = key[sid]
    w = wold.get(k)
    if not w:
        miss_ts += 1
        continue
    yo, sr = sf.read(os.path.join(OLD, sid + '.wav'), dtype='float32')
    yn, sr2 = sf.read(os.path.join(NEW, sid + '.wav'), dtype='float32')
    if yo.ndim > 1:
        yo = yo.mean(1)
    if yn.ndim > 1:
        yn = yn.mean(1)
    go, gn = gaps(yo, sr), gaps(yn, sr2)
    if len(go) != len(gn):
        go = gn  # 对不上就不平移
    deltas = [(gn[i][0] - go[i][0], gn[i][1] - go[i][1]) for i in range(min(len(go), len(gn)))]
    words = w['words']
    # 平移：对每个旧 gap，累积长度差
    shift = []
    acc = 0.0
    for i in range(len(deltas)):
        g_old_end = go[i][1]
        acc += (gn[i][1] - gn[i][0]) - (go[i][1] - go[i][0])
        shift.append((g_old_end, acc))
    def mv(t):
        s = 0.0
        for e, a in shift:
            if t >= e:
                s = a
            else:
                break
        return t + s
    rows.append((sid, yn, sr2, [(x['w'], mv(x['start']), mv(x['end'])) for x in words]))
print('可算句', len(rows), '缺时间戳', miss_ts)

# ---------- 3. 三轴 ----------
res = {'n_words': 0, 'n_stress': 0, 'hit_any': 0, 'hit_dur': 0, 'hit_f0': 0, 'hit_eng': 0,
       'miss_all': 0, 'miss_list': [], 'over': 0, 'over_list': []}
per_sent = []
for sid, y, sr, words in rows:
    if len(words) < 3:
        continue
    snd = parselmouth.Sound(y, sampling_frequency=sr)
    pitch = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=400)
    f0 = pitch.selected_array['frequency']
    t = pitch.xs()
    dur = np.array([max(1e-3, e - s) for _, s, e in words])
    eng = np.array([float(np.sqrt((y[int(s*sr):max(int(s*sr)+1, int(e*sr))] ** 2).mean() + 1e-12)) for _, s, e in words])
    f0w = []
    for _, s, e in words:
        m = (t >= s) & (t <= e) & (f0 > 0)
        f0w.append(float(np.median(f0[m])) if m.any() else np.nan)
    def rz(v):
        v = np.asarray(v, dtype=float)
        m = np.nanmedian(v)
        d = np.nanmedian(np.abs(v - m)) * 1.4826 + 1e-9
        return (v - m) / d
    z_d = rz(np.log(dur))
    z_e = rz(np.log(eng))
    med_f = np.nanmedian(f0w) if np.any(~np.isnan(f0w)) else 0
    z_f = rz(np.array([(x - med_f) if not np.isnan(x) else med_f for x in f0w]))
    s_idx = [s['tok'] for s in stress[sid] if s['tok'] < len(words)]
    res['n_words'] += len(words)
    res['n_stress'] += len(s_idx)
    for i in s_idx:
        hd = z_d[i] >= 1.0
        hf = z_f[i] >= 1.0
        he = z_e[i] >= 1.0
        res['hit_dur'] += hd
        res['hit_f0'] += hf
        res['hit_eng'] += he
        if hd or hf or he:
            res['hit_any'] += 1
        if (not hd) and (not hf) and (not he):
            res['miss_all'] += 1
            if len(res['miss_list']) < 40:
                res['miss_list'].append({'sid': sid, 'w': words[i][0],
                                         'z': [round(float(z_d[i]), 2), round(float(z_f[i]), 2), round(float(z_e[i]), 2)]})
    lab = set(s_idx)
    for i in range(len(words)):
        if i in lab:
            continue
        if z_d[i] >= 1.5 and z_f[i] >= 1.5 and z_e[i] >= 1.5:
            res['over'] += 1
            if len(res['over_list']) < 20:
                res['over_list'].append({'sid': sid, 'w': words[i][0]})
    per_sent.append({'sid': sid, 'words': len(words), 'stress': len(s_idx), 'dur': np.round(z_d, 2).tolist()})

n = max(1, res['n_stress'])
print()
print('标注重读 %d 处 / 词 %d 个' % (res['n_stress'], res['n_words']))
print('命中率(至少一轴 z>=1): %d (%.1f%%)' % (res['hit_any'], 100 * res['hit_any'] / n))
print('  时长轴 %.1f%% / F0轴 %.1f%% / 能量轴 %.1f%%' % (100 * res['hit_dur'] / n, 100 * res['hit_f0'] / n, 100 * res['hit_eng'] / n))
print('三轴全无 (该读没读): %d (%.1f%%)' % (res['miss_all'], 100 * res['miss_all'] / n))
print('未标注词却三轴都>=1.5 (过度重读): %d 处' % res['over'])
json.dump(res, open('G:/_setup/_stress_loop_report.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('样例漏读', json.dumps(res['miss_list'][:5], ensure_ascii=False))
