# -*- coding: utf-8 -*-
"""v5full_asr_full.py —— 整段转写 + 按切片边界切分（完整上下文的标注）

为什么不用逐切片 ASR：slicer2 在停顿处切分，每片独立转写会丢上下文
  → 首字母小写 / 一句话被切成两片 / 逗号被误判成句号。

做法：
  1) 对 26.92min 原始录音做一次整段转写（word_timestamps + vad_filter）
     ⇒ 标点与大小写基于完整上下文
  2) 用切片文件名里的帧号（32kHz）得到每个切片的时间区间
  3) 按词中点归属，把全局词序列切分到各切片
  4) 输出 .list + 报告 json（含每条的词数/时长/词率/可疑标记）
"""
import os
import re
import glob
import json
import time

import numpy as np
import soundfile as sf

SRC = os.environ.get('SRC', r'G:/GPT-SoVITS/_dataset/wonder_train.wav')
SLICED = os.environ.get('SLICED', r'G:/GPT-SoVITS/_dataset_v5full/sliced')
OUTLIST = os.environ.get('OUTLIST', r'G:/GPT-SoVITS/_dataset_v5full/wonder_v5full.list')
OUTJSON = os.environ.get('OUTJSON', r'G:/GPT-SoVITS/_dataset_v5full/asr_full.json')
SPK = 'mcconaughey'
LANG = 'en'
MODEL = os.environ.get('ASR_MODEL', 'small.en')
SR = 32000

MIN_WORDS = 3          # 少于这个词数视为可疑
MAX_WPS = 6.0          # 词/秒 上限
MIN_WPS = 0.6          # 词/秒 下限


def parse_slice(path):
    """从文件名解析 (t0, t1) 秒"""
    m = re.search(r'_(\d{10})_(\d{10})\.wav$', os.path.basename(path))
    if not m:
        return None, None
    return int(m.group(1)) / SR, int(m.group(2)) / SR


def join_words(ws):
    """ws: [(word, start, end)] → 文本（标点前不留空格）"""
    txt = ' '.join(t for t, _, _ in ws)
    txt = re.sub(r'\s+([.,?!;:])', r'\1', txt)
    txt = re.sub(r'\s{2,}', ' ', txt).strip()
    return txt


def main():
    from faster_whisper import WhisperModel

    files = sorted(glob.glob(os.path.join(SLICED, '*.wav')))
    if not files:
        raise SystemExit('没找到切片: ' + SLICED)
    print('切片 %d 个 | 模型 %s | 整段转写中...' % (len(files), MODEL), flush=True)

    m = WhisperModel(MODEL, device='cpu', compute_type='int8', cpu_threads=10)
    t0 = time.time()
    segs, info = m.transcribe(
        SRC, language='en', beam_size=5,
        word_timestamps=True, vad_filter=True,
        condition_on_previous_text=True,
    )
    words = []
    seg_texts = []
    for s in segs:
        seg_texts.append({'start': round(float(s.start), 2), 'end': round(float(s.end), 2),
                          'text': s.text.strip()})
        for w in (s.words or []):
            t = w.word.strip()
            if t:
                words.append((t, float(w.start), float(w.end)))
    dt = time.time() - t0
    print('整段转写完成: %d 词 / %d 段 | 耗时 %.1f min' % (len(words), len(seg_texts), dt / 60), flush=True)
    if words:
        print('  首词 %r @ %.2fs | 末词 %r @ %.2fs' % (words[0][0], words[0][1], words[-1][0], words[-1][2]), flush=True)

    # 按切片时间区间分配词（用词中点判定归属）
    rows = []
    report = []
    cursor = 0
    nwords = len(words)
    for idx, p in enumerate(files):
        t0s, t1s = parse_slice(p)
        if t0s is None:
            continue
        assigned = []
        # 从 cursor 起扫描，避免 O(n^2)
        j = cursor
        while j < nwords and (words[j][1] + words[j][2]) / 2.0 < t0s:
            j += 1
        cursor = j
        k = j
        while k < nwords and (words[k][1] + words[k][2]) / 2.0 < t1s:
            assigned.append(words[k])
            k += 1
        txt = join_words(assigned)
        dur = t1s - t0s
        nw = len(assigned)
        wps = nw / max(dur, 1e-6)
        flag = ''
        if nw < MIN_WORDS:
            flag = 'too_few_words(%d)' % nw
        elif wps > MAX_WPS:
            flag = 'wps_high(%.1f)' % wps
        elif wps < MIN_WPS:
            flag = 'wps_low(%.1f)' % wps
        report.append({'i': idx, 'file': os.path.basename(p), 't0': round(t0s, 2), 't1': round(t1s, 2),
                       'dur': round(dur, 2), 'nwords': nw, 'wps': round(wps, 2),
                       'text': txt, 'flag': flag})
        if txt:
            rows.append('%s|%s|%s|%s' % (p.replace('/', '\\'), SPK, LANG, txt))

    with open(OUTLIST, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows) + '\n')

    bad = [r for r in report if r['flag']]
    json.dump({'model': MODEL, 'total_slices': len(files), 'kept': len(rows),
               'total_words': nwords, 'transcribe_min': round(dt / 60, 1),
               'flagged': len(bad), 'segments': seg_texts, 'slices': report},
              open(OUTJSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('\n写出 %s  (%d 条)' % (OUTLIST, len(rows)))
    print('可疑 %d 条:' % len(bad))
    for r in bad[:25]:
        print('   [%03d] %5.2fs %2d词 wps=%.1f %-22s %s' % (r['i'], r['dur'], r['nwords'], r['wps'], r['flag'], r['text'][:60]))


if __name__ == '__main__':
    main()
