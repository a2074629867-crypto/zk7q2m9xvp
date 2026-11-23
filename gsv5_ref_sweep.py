# -*- coding: utf-8 -*-
"""gsv5_ref_sweep.py —— 参考音频扫描：固定 GPT(v6-e18) + 零样本 SoVITS，只换参考音频

必须项：
  1. 先跑一次 warmup 丢弃（新进程首次推理会失控，n≈1499/60s）
  2. 参考音频/prompt_text 每次切换，prompt_cache 按路径失效，无需手动清
"""
import os, sys, time, json
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
GPT = 'GPT_weights_v6/mcconaughey_v6-e18.ckpt'
TEXT = open(r'G:/_setup/scene_calmdeep.txt', encoding='utf-8').read().strip()
CANDS = json.load(open(r'E:/tts-models/acpp/out/refs/candidates.json', encoding='utf-8'))
OUT = r'E:/tts-models/acpp/out/refsweep'
os.makedirs(OUT, exist_ok=True)

t0 = time.time()
tts = TTS(TTS_Config({'custom': _C}))
print('[load] %.1fs' % (time.time() - t0), flush=True)
tts.init_t2s_weights(GPT)

CLS = type(tts.t2s_model.model)
_REC = {}
_orig = CLS.__dict__['infer_panel_batch_infer']
def _wrap(self, *a, **kw):
    y, idx = _orig(self, *a, **kw)
    _REC['n'] = int(sum(int(i) for i in idx))
    return y, idx
CLS.infer_panel_batch_infer = _wrap

def run(ref, ref_text):
    _REC.clear()
    args = dict(text=TEXT, text_lang='en', ref_audio_path=ref, prompt_text=ref_text,
                prompt_lang='en', top_k=15, top_p=1, temperature=1,
                text_split_method='cut0', batch_size=1, speed_factor=1.0, seed=42,
                parallel_infer=True, repetition_penalty=1.35,
                use_cuda_graph=False, use_flash_attention=False)
    sr, audio = None, None
    for o in tts.run(args):
        if o is not None:
            sr, audio = o
    return sr, audio, _REC.get('n')

# ---- warmup（丢弃）----
w_ref, w_txt = CANDS[0]['path'], CANDS[0]['text']
t0 = time.time()
try:
    sr, a, n = run(w_ref, w_txt)
    print('[WARM] %.2fs n=%s (%.1fs) 丢失' % (len(a) / sr, n, time.time() - t0), flush=True)
except Exception as e:
    print('[WARM-ERR] %s' % str(e)[:160], flush=True)

res = []
for i, c in enumerate(CANDS):
    tag = c['tag']
    t0 = time.time()
    try:
        sr, a, n = run(c['path'], c['text'])
    except Exception as e:
        print('[ERR ] %-24s %s' % (tag, str(e)[:120]), flush=True)
        res.append(dict(tag=tag, err=str(e)[:120])); continue
    d = len(a) / sr
    p = os.path.join(OUT, tag + '.wav')
    sf.write(p, a, sr)
    print('[%2d/%d] %-24s ref=%5.2fs  out=%6.2fs n=%-4s (%.1fs)' % (
        i + 1, len(CANDS), tag, c['dur'], d, n, time.time() - t0), flush=True)
    res.append(dict(tag=tag, ref_dur=round(c['dur'], 2), out_dur=round(d, 2), n=n,
                    path=p, ref_path=c['path'], ref_text=c['text'],
                    voiced=c.get('voiced'), maxsil=c.get('maxsil'),
                    f0=c.get('f0'), f0sd=c.get('f0sd'), kind=c.get('kind', 'new')))

json.dump(res, open(os.path.join(OUT, 'sweep.json'), 'w'), ensure_ascii=False, indent=1)
print('DONE %d/%d' % (len([r for r in res if 'out_dur' in r]), len(CANDS)), flush=True)
