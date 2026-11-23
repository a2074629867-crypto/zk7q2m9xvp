# -*- coding: utf-8 -*-
"""对切片跑 ASR，生成 GPT-SoVITS 训练用的 .list（faster_whisper small.en，CPU）。"""
import os, sys, glob, re, time

SLICED = os.environ.get('SLICED', r'G:/GPT-SoVITS/_dataset_v5full/sliced')
OUTLIST = os.environ.get('OUTLIST', r'G:/GPT-SoVITS/_dataset_v5full/wonder_v5full.list')
SPK = 'mcconaughey'
LANG = 'en'
MODEL = os.environ.get('ASR_MODEL', 'small.en')


def main():
    files = sorted(glob.glob(os.path.join(SLICED, '*.wav')))
    if not files:
        sys.exit('没找到切片: ' + SLICED)
    print('切片 %d 个，ASR 模型 = %s' % (len(files), MODEL), flush=True)

    from faster_whisper import WhisperModel
    m = WhisperModel(MODEL, device='cpu', compute_type='int8', cpu_threads=10)

    rows, bad = [], []
    t0 = time.time()
    for i, p in enumerate(files, 1):
        name = os.path.basename(p)
        try:
            segs, info = m.transcribe(p, language='en', beam_size=5,
                                      vad_filter=False, condition_on_previous_text=False)
            text = ' '.join(s.text.strip() for s in segs).strip()
        except Exception as e:
            bad.append((name, 'ASR失败: %s' % e))
            continue
        text = re.sub(r'\s+', ' ', text).strip()
        letters = len(re.findall(r'[A-Za-z]', text))
        if letters < 8:
            bad.append((name, '文本过短: %r' % text))
            continue
        rows.append('%s|%s|%s|%s' % (p, SPK, LANG, text))
        if i % 25 == 0 or i == len(files):
            el = time.time() - t0
            print('  %d/%d  已用 %.1f min  预计剩余 %.1f min'
                  % (i, len(files), el / 60, el / i * (len(files) - i) / 60), flush=True)

    with open(OUTLIST, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows) + '\n')
    print('写出 %s  有效 %d 条，丢弃 %d 条' % (OUTLIST, len(rows), len(bad)), flush=True)
    for n, r in bad[:30]:
        print('   丢弃 %s  %s' % (n, r), flush=True)


if __name__ == '__main__':
    main()
