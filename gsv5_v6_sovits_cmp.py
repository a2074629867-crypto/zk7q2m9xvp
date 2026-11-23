# -*- coding: utf-8 -*-
"""gsv5_v6_sovits_cmp.py —— 固定 GPT(v6 e18)，对比不同 SoVITS 权重

目的：确认「零样本底模 s2Gv5turbo」vs「我们微调的 v5turbo LoRA」哪个声纹更好。
用法：python gsv5_v6_sovits_cmp.py [gpt_tag] [sovits_tag1 sovits_tag2 ...]
      不带参数 = gpt e18 + 全部 8 个微调 SoVITS + base
"""
import os, sys, time, json, glob
import numpy as np, soundfile as sf

REPO = r'G:/_setup/gsv5probe'
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, 'GPT_SoVITS'))
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
OUT = r'E:/tts-models/acpp/out/v6sovits'
os.makedirs(OUT, exist_ok=True)

GPT_TAG = sys.argv[1] if len(sys.argv) > 1 else 'e18'
SOV = sys.argv[2:] or [
    'base',
    'e2_s232', 'e4_s464', 'e6_s696', 'e8_s928',
]

GPT_PATH = ('GPT_weights_v6/mcconaughey_v6-%s.ckpt' % GPT_TAG) if GPT_TAG != 'base' else (PM + '/s1v3.ckpt')
SOV_DIR = 'SoVITS_weights_v5turbo'
SOV_BASE = PM + '/gsv-v5-pretrained/s2Gv5turbo.pth'

print('GPT = %s' % GPT_PATH, flush=True)
print('TEXT 词数: %d' % len(TEXT.split()), flush=True)

t0 = time.time()
tts = TTS(TTS_Config(CFG))
print('[load TTS] %.1fs' % (time.time() - t0), flush=True)
tts.init_t2s_weights(GPT_PATH)
print('[load GPT] ok', flush=True)

RUN = dict(
    text=TEXT, text_lang='en',
    ref_audio_path=REF, prompt_text=REF_TEXT, prompt_lang='en',
    top_k=15, top_p=1, temperature=1,
    text_split_method='cut0', batch_size=1,
    speed_factor=1.0, seed=42,
    parallel_infer=True, repetition_penalty=1.35,
    use_cuda_graph=False, use_flash_attention=False,
)

res = []
for tag in SOV:
    if tag == 'base':
        vp = SOV_BASE
    else:
        cands = glob.glob(os.path.join(SOV_DIR, '*%s*.pth' % tag))
        if not cands:
            print('[MISS] %s' % tag, flush=True); continue
        vp = cands[0]
    try:
        tts.init_vits_weights(vp)
    except Exception as e:
        print('[ERRload] %-10s %s' % (tag, str(e)[:120]), flush=True); continue
    t0 = time.time()
    sr, audio = None, None
    try:
        for _out in tts.run(RUN):
            if _out is not None:
                sr, audio = _out
    except Exception as e:
        print('[ERR ] %-10s %s' % (tag, str(e)[:130]), flush=True); continue
    el = time.time() - t0
    p = os.path.join(OUT, 'sov_%s.wav' % tag)
    sf.write(p, audio, sr)
    d = len(audio) / sr
    print('[sov] %-10s dur=%6.2fs (%.1fs) -> %s' % (tag, d, el, p), flush=True)
    res.append(dict(tag=tag, dur=round(d, 2), path=p))

json.dump(res, open(OUT + '/sov_result.json', 'w'), ensure_ascii=False, indent=1)
print('DONE', flush=True)
