# -*- coding: utf-8 -*-
"""真实场景端到端：任意书籍文本 → 马修音色 + 韵律后处理 + 标点停顿

没有 donor 录音时的完整链路（这就是阅读器实际会走的流程）：
  ① 逐句 GPT-SoVITS 生成（BEST 配方：亮参考 + cut0 + 多 seed 选完整）
  ② 按 pause_bank 原型插入逗号/句末停顿
  ③ F0 夸张化（Praat）+ 高频补偿 EQ
  ④ whisper 回读校验（词完整性）

用法:
  python -u real_scene.py --text-file t.txt --out E:/tts-models/out/scene --tag castle1
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

REPO = r'G:/GPT-SoVITS'
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'GPT_SoVITS'))
sys.path.insert(0, r'G:/_setup')

FFMPEG = r'E:/tool/oopz/ffmpeg.exe'
SLICED = r'G:/GPT-SoVITS/_dataset/sliced'
REF_WAV = os.path.join(SLICED, 'wonder_train.wav_0018112640_0018378240.wav')  # 谱心 868，最亮
REF_TEXT = 'called Sirius, is reaching Earth after traveling at 186,000 miles per second.'
S2_W = 'SoVITS_weights_v2/mcconaughey_calm_e8_s1216.pth'
S1_W = 'GPT_weights_v2/mcconaughey_calm-e10.ckpt'
PAUSE_BANK = r'G:/_setup/pause_bank.json'

_TTS = None
_WHISPER = None


def log(*a):
    print(*a, flush=True)


def get_tts():
    global _TTS
    if _TTS is None:
        os.chdir(REPO)
        from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
        cfg = {'version': 'v2', 'custom': {
            'device': 'cpu', 'is_half': False, 'version': 'v2',
            't2s_weights_path': 'GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt',
            'vits_weights_path': 'GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth',
            'cnhuhbert_base_path': 'GPT_SoVITS/pretrained_models/chinese-hubert-base',
            'bert_base_path': 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'}}
        _TTS = TTS(TTS_Config(cfg))
        _TTS.init_vits_weights(S2_W)
        _TTS.init_t2s_weights(S1_W)
    return _TTS


def get_whisper():
    global _WHISPER
    if _WHISPER is None:
        os.environ.setdefault('HF_HOME', r'C:/Users/86178/.cache/huggingface')
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        from faster_whisper import WhisperModel
        _WHISPER = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=8)
    return _WHISPER


def asr(wav):
    m = get_whisper()
    segs, _ = m.transcribe(wav, language='en', beam_size=5, word_timestamps=True,
                           vad_filter=False, condition_on_previous_text=False)
    txt = ' '.join(s.text.strip() for s in segs)
    words = []
    for s in segs:
        for w in (s.words or []):
            if w.word.strip():
                words.append((float(w.start), float(w.end), w.word.strip()))
    return txt, words


def norm(s):
    return re.sub(r'[^a-z ]', '', s.lower()).split()


def clean_text(s):
    """文本预处理：GPT-SoVITS 英文前端会把词内连字符读成 "minus"（moth-like → moth minus like）。
    这里把词内连字符换成空格（读音等价），并统一引号。"""
    s = (s.replace('\u2019', "'").replace('\u2018', "'")
          .replace('\u201c', '"').replace('\u201d', '"'))
    s = re.sub(r'(?<=\w)-(?=\w)', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def gen_sentence(tts, text, seeds=(2024, 31337, 777, 123, 7)):
    """生成单句，用 ASR 选完整度最高的。"""
    exp = norm(text)
    best = None
    for sd in seeds:
        t0 = time.time()
        gen = tts.run(dict(text=text, text_lang='en', ref_audio_path=REF_WAV,
                           prompt_text=REF_TEXT, prompt_lang='en',
                           top_k=15, top_p=1, temperature=0.9,
                           text_split_method='cut0', batch_size=1,
                           speed_factor=float(os.environ.get('GSV_SPEED', '1.0')),
                           seed=sd, parallel_infer=True,
                           repetition_penalty=1.35))
        sr, audio = None, None
        for sr, audio in gen:
            pass
        d = len(audio) / sr
        tmp = os.path.join(os.environ.get('TMPDIR', r'G:/_setup'), '_gs_tmp.wav')
        sf.write(tmp, audio, sr)
        txt, _ = asr(tmp)
        got = norm(txt)
        r = difflib.SequenceMatcher(None, got, exp).ratio()
        log('    seed=%-6d %5.2fs  一致率%.2f  (%d/%d词)  %.0fs' %
            (sd, d, r, len(got), len(exp), time.time() - t0))
        if r >= 0.995:
            return audio, sr, sd, r
        if best is None or r > best[3]:
            best = (audio, sr, sd, r)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--text-file', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--tag', default='scene')
    ap.add_argument('--join-gap', type=float, default=0.28, help='逐句拼接时的粗间隔')
    ap.add_argument('--pause-strength', type=float, default=1.0)
    ap.add_argument('--ex-k', type=float, default=1.6, help='F0 夸张系数，0=不夸张')
    ap.add_argument('--eq-gain', type=float, default=1.2)
    ap.add_argument('--eq-freq', type=float, default=2600)
    ap.add_argument('--speed', type=float, default=1.0, help='最终 atempo')
    ap.add_argument('--skip-pause', action='store_true')
    ap.add_argument('--skip-ex', action='store_true')
    ap.add_argument('--reuse', action='store_true', help='复用已生成的 *_joined.wav，跳过 ① 生成')
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    raw = open(a.text_file, encoding='utf-8').read().strip()
    raw = clean_text(raw)
    # 按句切（保留标点）
    sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', raw) if s.strip()]
    log('=== %s  共 %d 句 ===' % (a.tag, len(sents)))
    for i, s in enumerate(sents):
        log('  [%d] %s' % (i, s))

    tts = get_tts()
    joined = os.path.join(a.out, '%s_joined.wav' % a.tag)
    if a.reuse and os.path.exists(joined):
        log('\n--- ① 复用已有拼接 %s ---' % joined)
        parts = []
        meta = []
    else:
        log('\n--- ① 逐句生成 ---')
        parts = []
        meta = []
        for i, s in enumerate(sents):
            log(' 句%d: %s' % (i, s[:80]))
            audio, sr, sd, r = gen_sentence(tts, s)
            p = os.path.join(a.out, '%s_s%d_raw.wav' % (a.tag, i))
            sf.write(p, audio, sr)
            parts.append((p, len(audio) / sr, r, sd))
            meta.append(dict(idx=i, text=s, seed=sd, consistency=r, dur=len(audio) / sr))

        # 拼接（粗间隔，让 whisper 能识别句边界）
        log('\n--- ② 拼接 ---')
        lst = os.path.join(a.out, '_concat.txt')
        with open(lst, 'w', encoding='utf-8') as f:
            for k, (p, d, r, sd) in enumerate(parts):
                f.write("file '%s'\n" % p.replace('\\', '/'))
                if k < len(parts) - 1:
                    sil = os.path.join(a.out, '_sil.wav')
                    sf.write(sil, np.zeros(int(a.join_gap * 24000), dtype=np.float32), 24000)
                    f.write("file '%s'\n" % sil.replace('\\', '/'))
        subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error',
                        '-f', 'concat', '-safe', '0', '-i', lst,
                        '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', joined], check=True)
        log('  拼接后 %.2fs' % sf.info(joined).duration)

    log('\n--- ③ 插停顿 ---')
    cur = joined
    if not a.skip_pause and os.path.exists(PAUSE_BANK):
        pd = os.path.join(a.out, '%s_pause.wav' % a.tag)
        cmd = [sys.executable, '-u', r'G:/_setup/insert_pauses.py',
               '--in', cur, '--out', pd, '--proto', PAUSE_BANK,
               '--strength', str(a.pause_strength),
               '--report', os.path.join(a.out, '%s_pauses.json' % a.tag)]
        env = dict(os.environ, HF_HOME=r'C:/Users/86178/.cache/huggingface', HF_HUB_OFFLINE='1')
        subprocess.run(cmd, env=env, check=True)
        cur = pd
    else:
        log('  (跳过停顿注入)')

    log('\n--- ④ F0 夸张 + EQ ---')
    if not a.skip_ex and a.ex_k > 0:
        ex = os.path.join(a.out, '%s_ex.wav' % a.tag)
        subprocess.run([sys.executable, '-u', r'G:/_setup/exaggerate_praat.py',
                        '--in', cur, '--out', ex, '--ks', str(a.ex_k)], check=True)
        cur = ex

    if a.eq_gain > 0:
        eq = os.path.join(a.out, '%s_eq.wav' % a.tag)
        subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', cur,
                        '-af', 'treble=g=%g:f=%g' % (a.eq_gain, a.eq_freq),
                        '-c:a', 'pcm_s16le', eq], check=True)
        cur = eq

    if abs(a.speed - 1.0) > 1e-3:
        sp = os.path.join(a.out, '%s_final.wav' % a.tag)
        subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', cur,
                        '-af', 'atempo=%g' % a.speed, '-c:a', 'pcm_s16le', sp], check=True)
        cur = sp
    else:
        fin = os.path.join(a.out, '%s_final.wav' % a.tag)
        if cur != fin:
            subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', cur,
                            '-c:a', 'pcm_s16le', fin], check=True)
        cur = fin

    log('\n--- ③ 校验 ---')
    txt, ws = asr(cur)
    exp = norm(raw)
    got = norm(txt)
    r = difflib.SequenceMatcher(None, got, exp).ratio()
    dur = sf.info(cur).duration
    wpm = len(got) / (dur / 60.0)
    log('  最终 %s' % cur)
    log('  %.2fs  词 %d/%d  一致率 %.3f  %.0f wpm' % (dur, len(got), len(exp), r, wpm))
    log('  转写: %s' % txt)
    meta.append(dict(final=cur, dur=dur, consistency=r, wpm=wpm, asr=txt))
    json.dump(meta, open(os.path.join(a.out, '%s_meta.json' % a.tag), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    log('\n[done] %s' % cur)


if __name__ == '__main__':
    main()
