# -*- coding: utf-8 -*-
"""gsv5_epoch_sweep.py —— 逐 epoch 扫描：找 GPT 输出从哪个 epoch 开始崩。

设计：只创建一次 TTS 实例（base SoVITS），反复 init_t2s_weights 切换 GPT 权重，
每次用完全相同参数推理，记录输出时长。
- base 应 ~21.0s
- 若 e1 就崩 -> 训练数据/配置与推理不匹配
- 若后期才崩 -> 过拟合/训练退化
"""
import os, sys, time, json
import numpy as np, soundfile as sf

REPO = r'G:/_setup/gsv5probe'
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'GPT_SoVITS'))
os.chdir(REPO)
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
os.environ['version'] = 'v5turbo'

from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

PM = 'GPT_SoVITS/pretrained_models'
_C = {
    'device': 'cpu', 'is_half': False, 'version': 'v5turbo',
    'bert_base_path': PM + '/chinese-roberta-wwm-ext-large',
    'cnhuhbert_base_path': PM + '/chinese-hubert-base',
    't2s_weights_path': PM + '/s1v3.ckpt',
    'vits_weights_path': PM + '/gsv-v5-pretrained/s2Gv5turbo.pth',
}
CFG = {'custom': _C}

REF = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
REF_TEXT = 'called Sirius, is reaching Earth after traveling at 186,000 miles per second.'
TEXT = open(r'G:/_setup/scene_calmdeep.txt', encoding='utf-8').read().strip()
OUT = r'E:/tts-models/acpp/out/v5sweep'
os.makedirs(OUT, exist_ok=True)

GPT_DIR = 'GPT_weights_v5turbo/'
BASE = PM + '/s1v3.ckpt'
EPS = ['e1', 'e2', 'e3', 'e5', 'e8', 'e11', 'e15']

print('TEXT 词数: %d' % len(TEXT.split()), flush=True)

t0 = time.time()
tts = TTS(TTS_Config(CFG))
print('[load TTS] %.1fs' % (time.time() - t0), flush=True)

res = []
def run_one(tag, t2s_path):
    if not os.path.exists(t2s_path):
        print('[MISS] %s -> %s' % (tag, t2s_path), flush=True)
        return
    t0 = time.time()
    tts.init_t2s_weights(t2s_path)
    tl = time.time() - t0
    t0 = time.time()
    sr, audio = None, None
    try:
        for _out in tts.run({
            'text': TEXT, 'text_lang': 'en',
            'ref_audio_path': REF, 'prompt_text': REF_TEXT, 'prompt_lang': 'en',
            'top_k': 15, 'top_p': 1, 'temperature': 1,
            'text_split_method': 'cut0', 'batch_size': 1,
            'speed_factor': 1.0, 'seed': 42,
            'parallel_infer': True, 'repetition_penalty': 1.35,
            'use_cuda_graph': False, 'use_flash_attention': False,
        }):
            if _out is not None:
                sr, audio = _out
    except Exception as e:
        print('[ERR ] %-8s %s' % (tag, str(e)[:100]), flush=True)
        res.append(dict(tag=tag, dur=None, err=str(e)[:120]))
        return
    el = time.time() - t0
    p = os.path.join(OUT, tag + '.wav')
    sf.write(p, audio, sr)
    d = len(audio) / sr
    verdict = 'OK 完整' if d > 15 else ('偏短' if d > 5 else '崩(截断)')
    print('[run ] %-8s dur=%6.2fs  %s  权重加载%.1fs 推理%.1fs' % (tag, d, verdict, tl, el), flush=True)
    res.append(dict(tag=tag, dur=round(d, 2)))

print('\n===== base 基线 =====', flush=True)
run_one('base', BASE)
print('\n===== 逐 epoch =====', flush=True)
for e in EPS:
    run_one(e, GPT_DIR + 'mcconaughey_v5full_df3hp-%s.ckpt' % e)

json.dump(res, open(OUT + '/sweep_result.json', 'w'), ensure_ascii=False, indent=1)
print('\n===== 汇总 =====', flush=True)
for r in res:
    print('  %-8s %s' % (r['tag'], ('%.2fs' % r['dur']) if r.get('dur') is not None else 'ERR'), flush=True)
print('DONE', flush=True)
