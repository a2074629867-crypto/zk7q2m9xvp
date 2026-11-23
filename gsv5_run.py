# -*- coding: utf-8 -*-
"""gsv5_run.py —— GPT-SoVITS v5 (v5turbo) 零样本推理，用马修 Calm Wonder 素材。

与 v2 的差别：
  - 版本 version='v5turbo'（4 步采样，v5dev 要 32 步）
  - vits 权重 = gsv-v5-pretrained/s2Gv5turbo.pth（未微调，零样本）
  - t2s 权重 = s1v3.ckpt（v3/v4/v5 共用）
  - 参考音频 = Calm Wonder 真人切片（8.3s）

输出：E:/tts-models/acpp/out/v5/
"""
import os, sys, time, json, argparse
import numpy as np, soundfile as sf

REPO = r'G:/_setup/gsv5probe'
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'GPT_SoVITS'))
os.chdir(REPO)

os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

PM = 'GPT_SoVITS/pretrained_models'
# 注意：TTS_Config 只读 configs['custom'] 这一层（否则回退到 v2 默认）
_C = {
    'device': 'cpu',
    'is_half': False,
    'version': 'v5turbo',
    'bert_base_path': PM + '/chinese-roberta-wwm-ext-large',
    'cnhuhbert_base_path': PM + '/chinese-hubert-base',
    't2s_weights_path': PM + '/s1v3.ckpt',
    'vits_weights_path': PM + '/gsv-v5-pretrained/s2Gv5turbo.pth',
}
CFG = {'custom': _C}

# ---- 素材：马修 Calm 读 Wonder ----
REF = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
REF_TEXT = 'called Sirius, is reaching Earth after traveling at 186,000 miles per second.'
TEXT_FILE = r'G:/_setup/scene_calmdeep.txt'
OUT = r'E:/tts-models/acpp/out/v5'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--text-file', default=TEXT_FILE)
    ap.add_argument('--ref', default=REF)
    ap.add_argument('--ref-text', default=REF_TEXT)
    ap.add_argument('--speeds', default='1.0,0.88')
    ap.add_argument('--vocoder', action='store_true', help='启用 vocoder.pth（新声码器）')
    ap.add_argument('--tag-prefix', default='v5')
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    text = open(a.text_file, encoding='utf-8').read().strip()
    print('[text] %d 词: %s' % (len(text.split()), text[:100] + '...'))
    print('[ref ] %s  (%.2fs)' % (os.path.basename(a.ref), sf.info(a.ref).duration))

    t0 = time.time()
    cfg = TTS_Config(CFG)
    tts = TTS(cfg)
    print('[load] TTS 初始化 %.1fs' % (time.time() - t0))

    t0 = time.time()
    tts.init_vits_weights(_C['vits_weights_path'])
    tts.init_t2s_weights(_C['t2s_weights_path'])
    print('[load] 权重加载 %.1fs' % (time.time() - t0))

    if a.vocoder:
        try:
            tts.init_vocoder(_C['version'])
            print('[load] vocoder 已启用')
        except Exception as e:
            print('[warn] vocoder 启用失败:', e)

    for spd in [float(x) for x in a.speeds.split(',')]:
        tag = '%s_%s%s' % (a.tag_prefix, ('%g' % spd).replace('.', 'p'),
                           '_voc' if a.vocoder else '')
        print('--- %s  speed_factor=%s ---' % (tag, spd))
        t0 = time.time()
        try:
            # v5 的 run() 改成了生成器，需迭代取最后一个产出
            sr, audio = None, None
            for _out in tts.run({
                'text': text,
                'text_lang': 'en',
                'ref_audio_path': a.ref,
                'prompt_text': a.ref_text,
                'prompt_lang': 'en',
                'top_k': 15, 'top_p': 1, 'temperature': 1,
                'text_split_method': 'cut0',
                'batch_size': 1,
                'speed_factor': spd,
                'seed': 42,
                'parallel_infer': True,
                'repetition_penalty': 1.35,
                'use_cuda_graph': False,
                'use_flash_attention': False,
            }):
                if _out is not None:
                    sr, audio = _out
            if audio is None:
                raise RuntimeError('run() 未产出音频')
        except Exception as e:
            import traceback
            traceback.print_exc()
            print('[FAIL] %s: %s' % (tag, e))
            continue
        el = time.time() - t0
        p = os.path.join(a.out, tag + '.wav')
        sf.write(p, audio, sr)
        print('[ok] %s  sr=%d  dur=%.2fs  推理 %.1fs  -> %s' % (tag, sr, len(audio) / sr, el, p))

    print('[done]')


if __name__ == '__main__':
    main()
