# -*- coding: utf-8 -*-
"""v5full_asr2.py —— 高质量标注：ASR + 停顿感知标点 + 质量检测

为什么不用 initial_prompt：实测它会致幻（低能量切片会把 prompt 原文当内容吐出来）。

标注 = 文本 + 标点，其中标点必须与音频里的真实停顿一致 —— 这是 GSV 学到停顿的前提。
流程：
  1) faster_whisper small.en 转写（word_timestamps=True，无 initial_prompt）
  2) 能量法 VAD 找音频内部静音区间
  3) 静音区间 → 定位到词间 → 补标点（逗号/句号），词自带标点的不重复补
  4) 质量检测：低能量、幻觉短语、词率异常、零长词 → 标记
  5) 输出 .list + 报告 json
"""
import os
import re
import sys
import glob
import json
import time

import numpy as np
import soundfile as sf

SLICED = os.environ.get('SLICED', r'G:/GPT-SoVITS/_dataset_v5full/sliced')
OUTLIST = os.environ.get('OUTLIST', r'G:/GPT-SoVITS/_dataset_v5full/wonder_v5full.list')
OUTREPORT = os.environ.get('OUTREPORT', r'G:/GPT-SoVITS/_dataset_v5full/asr_report.json')
SPK = 'mcconaughey'
LANG = 'en'
MODEL = os.environ.get('ASR_MODEL', 'small.en')

SR = 32000
THR_DB = -35.0          # 静音判定：相对本切片峰值
MIN_SIL = 0.30          # 至少这么长才算"停顿"
EDGE_SKIP = 0.20        # 忽略首尾这么长范围内的静音（属切片边界）
PAUSE_COMMA = 0.34      # 停顿 >= 此值 → 逗号
PAUSE_PERIOD = 0.62     # 停顿 >= 此值 → 句号

# whisper 在静音/噪声上的常见幻觉
HALLUC = [
    'thank you', 'thanks for watching', 'please subscribe', 'subtitles',
    'amara.org', 'transcription by', 'subscribe', 'bye', 'you',
    'the end', '. . .', '...', 'okay', 'yeah',
]


def read_wav(path):
    x, sr = sf.read(path, dtype='float64', always_2d=True)
    x = x.mean(1)
    return x, sr


def sil_spans(x, sr, thr_db=THR_DB, min_sil=MIN_SIL, edge=EDGE_SKIP):
    """能量法找内部静音区间 [(t_start, t_end)]，忽略首尾 edge 秒内的。"""
    fl = int(0.025 * sr)
    hop = int(0.010 * sr)
    m = max(1, (len(x) - fl) // hop + 1)
    idx = np.arange(fl)[None, :] + hop * np.arange(m)[:, None]
    idx = np.clip(idx, 0, len(x) - 1)
    r = np.sqrt((x[idx] ** 2).mean(1) + 1e-20)
    rdb = 20 * np.log10(r + 1e-12)
    v = rdb > (rdb.max() + thr_db)
    spans = []
    i = 0
    L = int(min_sil * sr / hop)
    E = int(edge * sr / hop)
    while i < m:
        if not v[i]:
            j = i
            while j < m and not v[j]:
                j += 1
            if j - i >= L and i > E and j < m - E:
                spans.append((i * hop / sr, j * hop / sr))
            i = j
        else:
            i += 1
    return spans


def speech_stats(x, sr):
    """语音段电平统计（用能量法剔除静音后）"""
    fl = int(0.025 * sr)
    hop = int(0.010 * sr)
    m = max(1, (len(x) - fl) // hop + 1)
    idx = np.arange(fl)[None, :] + hop * np.arange(m)[:, None]
    idx = np.clip(idx, 0, len(x) - 1)
    r = np.sqrt((x[idx] ** 2).mean(1) + 1e-20)
    rdb = 20 * np.log10(r + 1e-12)
    g = rdb > (rdb.max() + THR_DB)
    peak = 20 * np.log10(np.abs(x).max() + 1e-12)
    speech_frac = float(g.mean())
    speech_rms = 20 * np.log10(np.sqrt((r[g] ** 2).mean() + 1e-30) + 1e-12) if g.any() else -99.0
    return peak, speech_rms, speech_frac


def build_text(words, spans):
    """words: [(w, start, end)]；spans: 静音区间 → 在词间补标点。返回 (text, inserted)"""
    if not words:
        return '', 0
    out = []
    inserted = 0
    for i, (w, s, e) in enumerate(words):
        out.append(w)
        if i + 1 < len(words):
            nxt_start = words[i + 1][1]
            mark = ''
            for (a, b) in spans:
                mid = (a + b) / 2.0
                # 静音中点落在当前词结束与该词起点之间 → 该处是停顿
                if e - 0.05 <= mid <= nxt_start + 0.05:
                    dur = b - a
                    if dur >= PAUSE_PERIOD:
                        mark = '.'
                    elif dur >= PAUSE_COMMA:
                        mark = ','
                    break
            if mark and not re.search(r'[.,?!;:—\-]$', w):
                out.append(mark)
                inserted += 1
    txt = ' '.join(out)
    txt = re.sub(r'\s+([.,?!;:])', r'\1', txt)
    txt = re.sub(r'\s{2,}', ' ', txt).strip()
    return txt, inserted


def check_quality(text, words, dur, peak, speech_rms, speech_frac):
    """返回 (ok, reason)"""
    low = text.lower().strip(' .')
    if len(re.findall(r'[A-Za-z]', text)) < 6:
        return False, 'text_too_short'
    if low in HALLUC:
        return False, 'hallucination_phrase'
    nw = len(words)
    if nw == 0:
        return False, 'no_words'
    # 词率异常（正常朗读 1.5~5 词/秒）
    wps = nw / max(dur, 1e-6)
    if wps > 6.0:
        return False, 'wps_too_high(%.1f)' % wps
    if wps < 0.5:
        return False, 'wps_too_low(%.1f)' % wps
    # 零长度词占比（whisper 对齐失败的信号）
    zero = sum(1 for _, s, e in words if e - s < 1e-6)
    if zero / nw > 0.35:
        return False, 'zero_len_words(%.0f%%)' % (100 * zero / nw)
    # 单字跨度异常（一个词占 >1.5s 说明对齐崩了）
    if any(e - s > 1.5 for _, s, e in words):
        return False, 'word_span_gt_1.5s'
    # 能量太低（多半是静音/气声被切成片）—— peak / speech_rms 均为 dB
    if peak < -26.0 or speech_rms < -45.0:
        return False, 'too_quiet(peak=%.1fdB rms=%.1fdB)' % (peak, speech_rms)
    if speech_frac < 0.15:
        return False, 'speech_frac_low(%.2f)' % speech_frac
    return True, ''


def main():
    files = sorted(glob.glob(os.path.join(SLICED, '*.wav')))
    if not files:
        sys.exit('没找到切片: ' + SLICED)
    print('切片 %d 个 | ASR=%s | 停顿阈值 逗号%.2fs 句号%.2fs' % (len(files), MODEL, PAUSE_COMMA, PAUSE_PERIOD), flush=True)

    from faster_whisper import WhisperModel
    m = WhisperModel(MODEL, device='cpu', compute_type='int8', cpu_threads=10)

    rows, rejected, suspicious = [], [], []
    n_insert = 0
    t0 = time.time()
    for i, p in enumerate(files, 1):
        name = os.path.basename(p)
        try:
            x, sr = read_wav(p)
            dur = len(x) / sr
            peak, srms, sfrac = speech_stats(x, sr)
            spans = sil_spans(x, sr)
            segs, _info = m.transcribe(p, language='en', beam_size=5,
                                       word_timestamps=True, vad_filter=False,
                                       condition_on_previous_text=False)
            words = []
            for s in segs:
                for w in (s.words or []):
                    t = w.word.strip()
                    if t:
                        words.append((t, float(w.start), float(w.end)))
        except Exception as e:
            rejected.append((name, 'asr_error: %s' % e))
            continue

        ok, why = check_quality(' '.join(w[0] for w in words), words, dur, peak, srms, sfrac)
        text, ins = build_text(words, spans)
        n_insert += ins

        if not ok:
            rejected.append((name, why))
            suspicious.append({'file': name, 'reason': why, 'text': text, 'dur': round(dur, 2)})
            continue

        rows.append('%s|%s|%s|%s' % (p, SPK, LANG, text))
        if i % 25 == 0 or i == len(files):
            el = time.time() - t0
            print('  %d/%d  已用 %.1f min  剩余约 %.1f min  已收 %d 拒 %d'
                  % (i, len(files), el / 60, el / i * (len(files) - i) / 60, len(rows), len(rejected)), flush=True)

    with open(OUTLIST, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows) + '\n')

    rep = {'total': len(files), 'kept': len(rows), 'rejected': len(rejected),
           'punct_inserted': n_insert, 'model': MODEL,
           'pause_comma': PAUSE_COMMA, 'pause_period': PAUSE_PERIOD,
           'reject_detail': rejected[:80], 'suspicious': suspicious[:80]}
    json.dump(rep, open(OUTREPORT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('\n写出 %s' % OUTLIST)
    print('保留 %d / 拒绝 %d | 停顿补标点 %d 个 | 平均每条补 %.2f 个'
          % (len(rows), len(rejected), n_insert, n_insert / max(len(rows), 1)))
    from collections import Counter
    c = Counter(r.split('(')[0] for _, r in rejected)
    print('拒绝原因:', dict(c.most_common(10)))


if __name__ == '__main__':
    main()
