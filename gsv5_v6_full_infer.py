# -*- coding: utf-8 -*-
"""gsv5_v6_full_infer.py —— 用指定 v6 GPT 权重 + v5turbo SoVITS 出完整音频

用法：python gsv5_v6_full_infer.py e8 e10 e12   （不带参数则只跑 base）
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
OUT = r'E:/tts-models/acpp/out/v6full'
os.makedirs(OUT, exist_ok=True)

TAGS = sys.argv[1:] or ['base']
GPT_DIR = 'GPT_weights_v6/'
BASE = PM + '/s1v3.ckpt'

print('TEXT 词数: %d' % len(TEXT.split()), flush=True)
t0 = time.time()
tts = TTS(TTS_Config(CFG))
print('[load TTS] %.1fs' % (time.time() - t0), flush=True)

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
for tag in TAGS:
    path = BASE if tag == 'base' else GPT_DIR + 'mcconaughey_v6-%s.ckpt' % tag
    if not os.path.exists(path):
        print('[MISS] %s' % tag, flush=True); continue
    tts.init_t2s_weights(path)
    t0 = time.time()
    sr, audio = None, None
    try:
        for _out in tts.run(RUN):
            if _out is not None:
                sr, audio = _out
    except Exception as e:
        print('[ERR ] %-6s %s' % (tag, str(e)[:130]), flush=True)
        res.append(dict(tag=tag, dur=None, err=str(e)[:100])); continue
    el = time.time() - t0
    p = os.path.join(OUT, 'v6_%s.wav' % tag)
    sf.write(p, audio, sr)
    d = len(audio) / sr
    print('[full] %-6s dur=%6.2fs  (%.1fs)  -> %s' % (tag, d, el, p), flush=True)
    res.append(dict(tag=tag, dur=round(d, 2), path=p))

json.dump(res, open(OUT + '/full_result.json', 'w'), ensure_ascii=False, indent=1)
print('DONE', flush=True)
