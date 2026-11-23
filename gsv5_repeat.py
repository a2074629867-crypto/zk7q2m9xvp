# -*- coding: utf-8 -*-
"""gsv5_repeat.py —— 同一权重重复 N 次（只跑 AR），验证输出长度是否可复现

如果同一权重、同一 seed、同一输入，n 每次都不同 => 采样非确定性，
则"单样本扫 epoch"结论不可靠，必须多 seed 平均。
"""
import os, sys, time
import numpy as np

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
tag = sys.argv[1] if len(sys.argv) > 1 else 'e18'
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
seeds = [int(x) for x in sys.argv[3:]] or [42] * N

tts = TTS(TTS_Config({'custom': _C}))
CLS = type(tts.t2s_model.model)
_REC = {}
_orig = CLS.__dict__['infer_panel_batch_infer']
def _wrap(self, *a, **kw):
    y, idx = _orig(self, *a, **kw)
    _REC['n'] = int(sum(int(i) for i in idx))
    K = 4
    return [t[:K] for t in y], [min(int(i), K) for i in idx]
CLS.infer_panel_batch_infer = _wrap

if tag != 'base':
    tts.init_t2s_weights('GPT_weights_v6/mcconaughey_v6-%s.ckpt' % tag)

REF = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
REF_TEXT = 'called Sirius, is reaching Earth after traveling at 186,000 miles per second.'
TEXT = open(r'G:/_setup/scene_calmdeep.txt', encoding='utf-8').read().strip()

print('权重 %s  重复 %d 次  seeds=%s' % (tag, len(seeds), seeds), flush=True)
ns = []
for i, sd in enumerate(seeds):
    _REC.clear()
    RUN = dict(text=TEXT, text_lang='en', ref_audio_path=REF, prompt_text=REF_TEXT, prompt_lang='en',
               top_k=15, top_p=1, temperature=1, text_split_method='cut0', batch_size=1,
               speed_factor=1.0, seed=sd, parallel_infer=True, repetition_penalty=1.35,
               use_cuda_graph=False, use_flash_attention=False)
    t0 = time.time()
    for _ in tts.run(RUN):
        pass
    n = _REC.get('n')
    ns.append(n)
    print('  #%d seed=%d  n=%s  dur=%.2fs  (%.1fs)' % (i + 1, sd, n, (n or 0) / 25.0, time.time() - t0), flush=True)

print('汇总 %s: n=%s  唯一值=%d' % (tag, ns, len(set(ns))), flush=True)
