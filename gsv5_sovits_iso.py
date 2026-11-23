# -*- coding: utf-8 -*-
"""gsv5_sovits_iso.py —— 单组合隔离运行：1 个 GPT + 1 个 SoVITS，一个进程只跑一次

用法：python gsv5_sovits_iso.py <gpt_tag|base> <sovits_path|base> <out_tag>
原因：同进程内反复 init_vits_weights 会出现状态污染（base 在循环里出 60.16s，
      隔离跑却是 18.84s）⇒ SoVITS 对比必须进程隔离。
"""
import os, sys, time
import numpy as np, soundfile as sf

REPO = r'G:/_setup/gsv5probe'
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, 'GPT_SoVITS'))
os.chdir(REPO)
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
os.environ['version'] = 'v5turbo'

from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

PM = 'GPT_SoVITS/pretrained_models'
VITS_BASE = PM + '/gsv-v5-pretrained/s2Gv5turbo.pth'

gpt_tag = sys.argv[1]
sov_path = sys.argv[2]
out_tag = sys.argv[3]

if gpt_tag == 'base':
    gpt_path = PM + '/s1v3.ckpt'
else:
    gpt_path = 'GPT_weights_v6/mcconaughey_v6-%s.ckpt' % gpt_tag
if sov_path == 'base':
    sov_path = VITS_BASE

_C = {
    'device': 'cpu', 'is_half': False, 'version': 'v5turbo',
    'bert_base_path': PM + '/chinese-roberta-wwm-ext-large',
    'cnhuhbert_base_path': PM + '/chinese-hubert-base',
    't2s_weights_path': gpt_path,
    'vits_weights_path': sov_path,
}
CFG = {'custom': _C}

REF = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
REF_TEXT = 'called Sirius, is reaching Earth after traveling at 186,000 miles per second.'
TEXT = open(r'G:/_setup/scene_calmdeep.txt', encoding='utf-8').read().strip()
OUT = r'E:/tts-models/acpp/out/v6soviso'
os.makedirs(OUT, exist_ok=True)

print('gpt=%s  sov=%s' % (gpt_path, sov_path), flush=True)
t0 = time.time()
tts = TTS(TTS_Config(CFG))
print('[load] %.1fs' % (time.time() - t0), flush=True)

RUN = dict(
    text=TEXT, text_lang='en',
    ref_audio_path=REF, prompt_text=REF_TEXT, prompt_lang='en',
    top_k=15, top_p=1, temperature=1,
    text_split_method='cut0', batch_size=1,
    speed_factor=1.0, seed=42,
    parallel_infer=True, repetition_penalty=1.35,
    use_cuda_graph=False, use_flash_attention=False,
)

t0 = time.time()
sr, audio = None, None
for _out in tts.run(RUN):
    if _out is not None:
        sr, audio = _out
el = time.time() - t0
p = os.path.join(OUT, 'iso_%s.wav' % out_tag)
sf.write(p, audio, sr)
print('[done] %-14s dur=%6.2fs (%.1fs) -> %s' % (out_tag, len(audio) / sr, el, p), flush=True)
