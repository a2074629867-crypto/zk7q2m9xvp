# -*- coding: utf-8 -*-
"""gsv5_diag.py —— 诊断 GPT/SoVITS 加载路径对输出长度的影响

用法： python gsv5_diag.py A|B|C
  A = config(t2s=s1v3, vits=base) + init_t2s_weights(v6 e18)   [full_infer 配方]
  B = config(t2s=v6 e18, vits=base)                            [iso 配方 → 曾出 60s]
  C = config(t2s=s1v3, vits=LoRA e6) + init_t2s_weights(v6 e18)
打印：configs.hz / max_sec / AR 生成 token 数 / 输出时长
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
BASE = PM + '/s1v3.ckpt'
VITS_BASE = PM + '/gsv-v5-pretrained/s2Gv5turbo.pth'
V6E18 = 'GPT_weights_v6/mcconaughey_v6-e18.ckpt'
LORA6 = 'SoVITS_weights_v5turbo/mcconaughey_v5full_df3hp_e6_s696_l32.pth'

mode = (sys.argv[1] if len(sys.argv) > 1 else 'A').upper()

if mode == 'A':
    _t2s_cfg, _vits_cfg, _init_t2s = BASE, VITS_BASE, V6E18
elif mode == 'B':
    _t2s_cfg, _vits_cfg, _init_t2s = V6E18, VITS_BASE, None
elif mode == 'C':
    _t2s_cfg, _vits_cfg, _init_t2s = BASE, LORA6, V6E18
else:
    raise SystemExit('mode A|B|C')

_C = {
    'device': 'cpu', 'is_half': False, 'version': 'v5turbo',
    'bert_base_path': PM + '/chinese-roberta-wwm-ext-large',
    'cnhuhbert_base_path': PM + '/chinese-hubert-base',
    't2s_weights_path': _t2s_cfg,
    'vits_weights_path': _vits_cfg,
}
print('MODE %s  cfg.t2s=%s  cfg.vits=%s  init_t2s=%s' % (mode, _t2s_cfg, _vits_cfg, _init_t2s), flush=True)

t0 = time.time()
tts = TTS(TTS_Config({'custom': _C}))
print('[load] %.1fs' % (time.time() - t0), flush=True)

CLS = type(tts.t2s_model.model)
_REC = {}
_orig = CLS.__dict__['infer_panel_batch_infer']
def _wrap(self, *a, **kw):
    y, idx = _orig(self, *a, **kw)
    _REC['n'] = int(sum(int(i) for i in idx))
    return y, idx
CLS.infer_panel_batch_infer = _wrap

if _init_t2s:
    tts.init_t2s_weights(_init_t2s)

print('[state] hz=%s  max_sec=%s  version=%s  t2s_now=%s' % (
    tts.configs.hz, tts.configs.max_sec, tts.configs.version,
    getattr(tts.configs, 't2s_weights_path', '?')), flush=True)

REF = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
REF_TEXT = 'called Sirius, is reaching Earth after traveling at 186,000 miles per second.'
TEXT = open(r'G:/_setup/scene_calmdeep.txt', encoding='utf-8').read().strip()
OUT = r'E:/tts-models/acpp/out/v6diag'
os.makedirs(OUT, exist_ok=True)

RUN = dict(text=TEXT, text_lang='en', ref_audio_path=REF, prompt_text=REF_TEXT, prompt_lang='en',
           top_k=15, top_p=1, temperature=1, text_split_method='cut0', batch_size=1,
           speed_factor=1.0, seed=42, parallel_infer=True, repetition_penalty=1.35,
           use_cuda_graph=False, use_flash_attention=False)

t0 = time.time()
sr, audio = None, None
for _out in tts.run(RUN):
    if _out is not None:
        sr, audio = _out
el = time.time() - t0
p = os.path.join(OUT, 'diag_%s.wav' % mode)
sf.write(p, audio, sr)
print('[OUT] MODE %s  hz=%s max_sec=%s  AR_n=%s  dur=%.2fs  (%.1fs)' % (
    mode, tts.configs.hz, tts.configs.max_sec, _REC.get('n'),
    len(audio) / sr, el), flush=True)
