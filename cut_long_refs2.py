# -*- coding: utf-8 -*-
"""cut_long_refs2.py —— 以「现有最优参考 baseA」为前缀的延长版

设计要点（比第一版严谨）：
1. **前缀完全一致**：所有版本都是母带 566.00s 起切，前 8.30s 与 baseA 逐采样相同。
   第一版从 566.14s 起切，结果 P08 连续两次失控（1499 token / 60s），拿不到可用基准。
2. 源用**未降噪**母带（实测 DF3 降噪伤音色：0.8567 -> 0.8452）。
3. 终点落在 VAD 切片边界，prompt_text = baseA 原文本 + 后续切片文本，与音频严格一致。
"""
import re, json, wave, shutil
import numpy as np
from pathlib import Path

SR = 32000
MASTER = r'G:/GPT-SoVITS/_dataset/wonder_train.wav'
BASE_A = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
BASE_A_TEXT = 'called Sirius, is reaching Earth after traveling at 186,000 miles per second.'
LABELS = Path(r'G:/_setup/gsv5probe/logs/mcconaughey_v6/2-name2text.txt')
OUTDIR = Path(r'E:/tts-models/acpp/out/refs_long2')
OUTDIR.mkdir(parents=True, exist_ok=True)

START = 566.00
BASE_A_END = 574.30
PLAN = [
    ('R08', None),          # 直接复制 baseA 原文件
    ('R11', 577.94),
    ('R15', 581.07),
    ('R21', 587.51),
    ('R28', 594.16),
]


def load_labels():
    rows = []
    for line in LABELS.read_text(encoding='utf-8').splitlines():
        p = line.split('\t')
        if len(p) < 4:
            continue
        m = re.search(r'_(\d+)_(\d+)\.wav$', p[0])
        if not m:
            continue
        rows.append((int(m.group(1)) / SR, int(m.group(2)) / SR, p[3].strip()))
    rows.sort()
    return rows


def load_master():
    with wave.open(MASTER, 'rb') as w:
        raw = w.readframes(w.getnframes())
        nch, sw = w.getnchannels(), w.getsampwidth()
    a = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    if nch > 1:
        a = a.reshape(-1, nch).mean(1)
    return a


def main():
    rows = load_labels()
    master = load_master()
    out = []
    for tag, end in PLAN:
        if end is None:
            p = OUTDIR / (tag + '.wav')
            shutil.copyfile(BASE_A, p)
            text = BASE_A_TEXT
            dur = (len(np.frombuffer(open(BASE_A, 'rb').read()[-0:], dtype=np.uint8)) or 0) and 0
            with wave.open(BASE_A, 'rb') as w:
                dur = w.getnframes() / w.getframerate()
            print('\n--- %s  baseA 原样 (%.2fs) ---\n    TEXT: %s' % (tag, dur, text))
            out.append(dict(tag=tag, path=str(p), s=START, e=BASE_A_END, dur=round(dur, 2),
                            text=text, n_part=2, n_word=len(text.split())))
            continue

        dur = end - START
        seg = master[int(START * SR):int(end * SR)]
        # 延长部分的文本：切片完全落在 (BASE_A_END, end] 内
        parts = [t for s, e, t in rows if s >= BASE_A_END - 0.02 and e <= end + 0.02]
        text = (BASE_A_TEXT + ' ' + ' '.join(parts)).strip()
        p = OUTDIR / (tag + '.wav')
        with wave.open(str(p), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(np.clip(seg * 32767, -32768, 32767).astype('<i2').tobytes())
        print('\n--- %s  566.00~%.2fs (%.2fs)  延长段 %d 片 ---' % (tag, end, dur, len(parts)))
        print('    延长文本: %s' % ' '.join(parts))
        out.append(dict(tag=tag, path=str(p), s=START, e=end, dur=round(dur, 2),
                        text=text, n_part=len(parts) + 2, n_word=len(text.split())))

    json.dump(out, open(OUTDIR / 'long_refs.json', 'w'), ensure_ascii=False, indent=1)
    print('\n已写 %s (%d 个)' % (OUTDIR / 'long_refs.json', len(out)))


if __name__ == '__main__':
    main()
