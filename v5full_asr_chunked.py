# -*- coding: utf-8 -*-
"""v5full_asr_chunked.py —— 分块转写 + 上下文接力（替代「整段一次转写」）

要解决的问题
------------
① 长音频一次转写（26.9min）存在时间戳漂移风险；
② 逐片转写（1~8s）丢上下文 → 丢大写 / 句子被切碎 / 逗号误判句号。

做法
----
以**切片边界**（= 真实停顿）为切点，把 468 个连续切片贪心分组为 ~26s 的窗；
每个窗取**原始录音的连续片段**转写，`initial_prompt` = 上文尾部（真实上文，不会幻觉）；
词时间戳是窗内局部时间 → 加窗偏移 → 全局时间（无长程漂移）；
再按切片 [t0,t1] 分配词（词中点归属）。

输出
----
<out>.list        路径|说话人|语言|文本      （可直接喂 1-get-text.py）
<out>.json        完整中间数据（words / windows / 质检）
"""
import argparse, json, os, re, sys, time
import numpy as np
import soundfile as sf


def read_mono(path):
    x, sr = sf.read(path, dtype='float64', always_2d=True)
    return x.mean(1), sr


def group_slices(slices, target=26.0):
    """把按时间排好的切片贪心分组，每组跨度尽量接近 target（不超 target+单片）。"""
    groups, cur = [], []
    for s in slices:
        if not cur:
            cur = [s]
            continue
        if s['t1'] - cur[0]['t0'] <= target:
            cur.append(s)
        else:
            groups.append(cur)
            cur = [s]
    if cur:
        groups.append(cur)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True, help='faster-whisper 模型名或本地目录')
    ap.add_argument('--src', default='G:/GPT-SoVITS/_dataset/wonder_train.wav')
    ap.add_argument('--slices-json', default='G:/GPT-SoVITS/_dataset_v5full/asr_full.json',
                    help='含 slices[].t0/t1/file 的 json（用切片边界做切窗锚点）')
    ap.add_argument('--sliced-dir', default='G:/GPT-SoVITS/_dataset_v5full/sliced')
    ap.add_argument('--out', required=True, help='输出前缀（.list / .json）')
    ap.add_argument('--speaker', default='mcconaughey')
    ap.add_argument('--lang', default='en')
    ap.add_argument('--target', type=float, default=26.0, help='窗长目标（秒）')
    ap.add_argument('--prompt-chars', type=int, default=200, help='上下文接力长度（字符）')
    ap.add_argument('--beam', type=int, default=5)
    ap.add_argument('--threads', type=int, default=10)
    ap.add_argument('--range', default='', help='调试：只跑第 a:b 组窗')
    args = ap.parse_args()

    from faster_whisper import WhisperModel

    J = json.load(open(args.slices_json, encoding='utf-8'))
    slices = sorted(J['slices'], key=lambda s: s['t0'])
    print('切片 %d 条 | 录音区间 %.2f - %.2f s' % (len(slices), slices[0]['t0'], slices[-1]['t1']))

    x, sr = read_mono(args.src)
    total = len(x) / sr
    print('原始录音 %.2fs = %.2f min @ %d Hz' % (total, total / 60, sr))

    groups = group_slices(slices, target=args.target)
    spans = [g[-1]['t1'] - g[0]['t0'] for g in groups]
    print('分窗 %d 个 | 窗长 中位 %.1fs 最短 %.1fs 最长 %.1fs' %
          (len(groups), float(np.median(spans)), min(spans), max(spans)))

    if args.range:
        a, b = (int(v) for v in args.range.split(':'))
        groups = groups[a:b]
        print('  [调试] 只跑第 %d:%d 组' % (a, b))

    t0 = time.time()
    model = WhisperModel(args.model, device='cpu', compute_type='int8', cpu_threads=args.threads)
    print('[load] 模型加载 %.1fs' % (time.time() - t0))

    all_words = []      # (global_start, global_end, word)
    windows = []
    ctx = ''
    for gi, g in enumerate(groups):
        a, b = g[0]['t0'], g[-1]['t1']
        seg = x[int(a * sr):int(b * sr)].astype(np.float32)
        t0 = time.time()
        try:
            segs, info = model.transcribe(
                seg, language=args.lang, beam_size=args.beam,
                word_timestamps=True, condition_on_previous_text=False,
                initial_prompt=(ctx[-args.prompt_chars:] if ctx else None),
                vad_filter=False,
            )
            ws, txt = [], ''
            for s in segs:
                txt += s.text
                for w in (s.words or []):
                    ws.append((a + float(w.start), a + float(w.end), w.word))
        except Exception as e:
            print('  [warn] 窗 %d (%.1f-%.1fs) 失败: %s' % (gi, a, b, str(e)[:90]))
            ws, txt = [], ''
        dt = time.time() - t0
        all_words.extend(ws)
        ctx += txt
        windows.append(dict(i=gi, t0=round(a, 2), t1=round(b, 2), n=len(g), nwords=len(ws),
                            sec=round(dt, 1), text=txt.strip()))
        if gi % 10 == 0 or gi == len(groups) - 1:
            print('  窗 %3d/%d  %7.2f-%7.2f (%4.1fs, %2d片) -> %2d词  %.1fs  | 累计词 %d'
                  % (gi, len(groups) - 1, a, b, b - a, len(g), len(ws), dt, len(all_words)))

    print('\n转写完成 %.1f min，得 %d 词' % ((time.time() - t0) / 60, len(all_words)))

    # ---- 按切片分配词（词中点归属）----
    rows = []
    for s in slices:
        rows.append(dict(file=s['file'], t0=s['t0'], t1=s['t1'], words=[], text=''))
    wi = 0
    for (ws, we, w) in all_words:
        mid = (ws + we) / 2.0
        while wi < len(rows) - 1 and mid > rows[wi]['t1']:
            wi += 1
        while wi > 0 and mid < rows[wi]['t0']:
            wi -= 1
        rows[wi]['words'].append((ws, we, w))

    for r in rows:
        r['text'] = re.sub(r'\s+', ' ', ''.join(w for _, _, w in r['words'])).strip()

    empty = [r for r in rows if not r['text']]
    print('切片分配：有文本 %d / 无文本 %d' % (len(rows) - len(empty), len(empty)))
    for r in empty[:12]:
        print('   空: %s  (%.2f-%.2fs)' % (r['file'][-44:], r['t0'], r['t1']))

    # ---- 写 list ----
    out_list = args.out + '.list'
    nw = 0
    with open(out_list, 'w', encoding='utf-8') as f:
        for r in rows:
            if not r['text']:
                continue
            p = os.path.join(args.sliced_dir, r['file'])
            f.write('%s|%s|%s|%s\n' % (p, args.speaker, args.lang, r['text']))
            nw += len(r['text'].split())
    print('写出 %s（%d 条 / %d 词）' % (out_list, sum(1 for r in rows if r['text']), nw))

    json.dump(dict(model=args.model, src=args.src, total_sec=round(total, 2),
                   n_slices=len(slices), n_windows=len(groups),
                   n_words=len(all_words), windows=windows,
                   slices=[dict(file=r['file'], t0=r['t0'], t1=r['t1'], text=r['text'],
                                nwords=len(r['words']),
                                words=[[round(a, 3), round(b, 3), w] for a, b, w in r['words']])
                           for r in rows]),
              open(args.out + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('写出 %s.json' % args.out)
    print('CHUNKDONE')


if __name__ == '__main__':
    main()
