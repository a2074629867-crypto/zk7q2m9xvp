# -*- coding: utf-8 -*-
"""gsv5_v6_sov_final.py —— SoVITS 对照（带预热，规避冷启动伪影）

发现：新进程第一次推理会给 ~1499 token / 60s 的失控结果（四份日志复现同一数字）。
      => 必须先跑一次 warmup 丢弃，再做正式推理。

流程：TTS(config: t2s=s1v3, vits=base) -> init_t2s_weights(v6 e18)
      -> warmup(丢弃) -> base / LoRA e2,e4,e6,e8 各出一次
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
VITS_BASE = PM + '/gsv-v5-pretrained/s2Gv5turbo.pth'
GPT = 'GPT_weights_v6/mcconaughey_v6-e18.ckpt'

_C = {
    'device': 'cpu', 'is_half': False, 'version': 'v5turbo',
    'bert_base_path': PM + '/chinese-roberta-wwm-ext-large',
    'cnhuhbert_base_path': PM + '/chinese-hubert-base',
    't2s_weights_path': PM + '/s1v3.ckpt',
    'vits_weights_path': VITS_BASE,
}
REF = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
REF_TEXT = 'called Sirius, is reaching Earth after traveling at 186,000 miles per second.'
TEXT = open(r'G:/_setup/scene_calmdeep.txt', encoding='utf-8').read().strip()
OUT = r'E:/tts-models/acpp/out/v6sovfinal'
os.makedirs(OUT, exist_ok=True)

t0 = time.time()
tts = TTS(TTS_Config({'custom': _C}))
print('[load] %.1fs' % (time.time() - t0), flush=True)
tts.init_t2s_weights(GPT)
print('[gpt ] %s' % GPT, flush=True)

# AR token 记录
CLS = type(tts.t2s_model.model)
_REC = {}
_orig = CLS.__dict__['infer_panel_batch_infer']
def _wrap(self, *a, **kw):
    y, idx = _orig(self, *a, **kw)
    _REC['n'] = int(sum(int(i) for i in idx))
    return y, idx
CLS.infer_panel_batch_infer = _wrap

def mkrun(seed=42):
    return dict(text=TEXT, text_lang='en', ref_audio_path=REF, prompt_text=REF_TEXT, prompt_lang='en',
                top_k=15, top_p=1, temperature=1, text_split_method='cut0', batch_size=1,
                speed_factor=1.0, seed=seed, parallel_infer=True, repetition_penalty=1.35,
                use_cuda_graph=False, use_flash_attention=False)

def go(tag, path=None, warm=False):
    if path:
        tts.init_vits_weights(path)
    _REC.clear()
    t0 = time.time()
    sr, audio = None, None
    for _out in tts.run(mkrun()):
        if _out is not None:
            sr, audio = _out
    el = time.time() - t0
    d = len(audio) / sr
    if warm:
        print('[WARM] %-12s dur=%6.2fs n=%s (%.1fs)  ← 丢弃' % (tag, d, _REC.get('n'), el), flush=True)
        return None
    p = os.path.join(OUT, 'sf_%s.wav' % tag)
    sf.write(p, audio, sr)
    print('[sov ] %-12s dur=%6.2fs n=%s (%.1fs) -> %s' % (tag, d, _REC.get('n'), el, p), flush=True)
    return dict(tag=tag, dur=round(d, 2), n=_REC.get('n'), path=p)

# ---- 预热（关键）----
go('warmup', None, warm=True)

res = []
res.append(go('base', VITS_BASE))
for v in ['e2_s232', 'e4_s464', 'e6_s696', 'e8_s928']:
    cands = glob.glob('SoVITS_weights_v5turbo/*%s*.pth' % v)
    if cands:
        res.append(go(v, cands[0]))

res = [r for r in res if r]
json.dump(res, open(OUT + '/sov_final.json', 'w'), ensure_ascii=False, indent=1)
print('DONE', flush=True)
