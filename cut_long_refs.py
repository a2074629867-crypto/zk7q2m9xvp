# -*- coding: utf-8 -*-
"""cut_long_refs.py —— 切「更长」的参考音频

关键点：
1. 源必须是**未降噪**母带 `_dataset/wonder_train.wav` —— 实测 DF3 降噪会伤音色
   （同段 0.8567 -> 0.8452），所以延长版一律走原始音频。
2. 全部以 566.00s 为同一锚点，只延长终点，保证「同一段话越读越长」，可严格对比。
3. 终点落在 VAD 切片边界（自然停顿处），避免把词切成两半。
4. prompt_text 从 v6 标签（455 片，含精确时间戳）拼接，保证与音频一致。
"""
import re, json, wave
import numpy as np
from pathlib import Path

SR = 32000
MASTER = r'G:/GPT-SoVITS/_dataset/wonder_train.wav'
LABELS = Path(r'G:/_setup/gsv5probe/logs/mcconaughey_v6/2-name2text.txt')
OUTDIR = Path(r'E:/tts-models/acpp/out/refs_long')
OUTDIR.mkdir(parents=True, exist_ok=True)

# 起终点全部落在 VAD 切片边界 => 不会有词被切成两半，prompt_text 与音频严格一致
START = 566.14
# (tag, end_s) —— 终点都落在切片边界
PLAN = [
    ('P08', 574.63),   # ≈ 现有参考(8.3s) 的等价物
    ('P12', 577.94),
    ('P15', 581.07),
    ('P18', 584.19),
    ('P21', 587.51),
    ('P27', 592.84),
    ('P28', 594.16),
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
        assert w.getframerate() == SR, w.getframerate()
        nch, sw = w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    assert sw == 2
    a = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    if nch > 1:
        a = a.reshape(-1, nch).mean(1)
    return a


def main():
    rows = load_labels()
    master = load_master()
    print('母带 %d 帧 = %.2fs' % (len(master), len(master) / SR))

    out = []
    for tag, end in PLAN:
        dur = end - START
        seg = master[int(START * SR):int(end * SR)]
        # 文本：完全落在区间内的切片
        parts = [t for s, e, t in rows if s >= START - 0.02 and e <= end + 0.02]
        # 检查边界是否有切片被切断
        cut = [(s, e, t) for s, e, t in rows if (s < START - 0.02 < e) or (s < end + 0.02 < e)]
        text = ' '.join(parts).strip()
        p = OUTDIR / (tag + '.wav')
        with wave.open(str(p), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(np.clip(seg * 32767, -32768, 32767).astype('<i2').tobytes())
        nw = len(text.split())
        print('\n--- %s   %.2f~%.2fs (%.2fs)  %d 片 / %d 词 ---' % (tag, START, end, dur, len(parts), nw))
        print('    TEXT: %s' % text)
        if cut:
            print('    ⚠ 边界被切断: %s' % [(round(s, 2), round(e, 2), t[:30]) for s, e, t in cut])
        out.append(dict(tag=tag, path=str(p), s=START, e=end, dur=round(dur, 2),
                        text=text, n_part=len(parts), n_word=nw,
                        rms=float(np.sqrt((seg ** 2).mean())),
                        peak=float(np.abs(seg).max())))

    json.dump(out, open(OUTDIR / 'long_refs.json', 'w'), ensure_ascii=False, indent=1)
    print('\n已写 %s (%d 个)' % (OUTDIR / 'long_refs.json', len(out)))


if __name__ == '__main__':
    main()
