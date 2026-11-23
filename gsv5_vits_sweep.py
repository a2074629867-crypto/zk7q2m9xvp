# -*- coding: utf-8 -*-
"""gsv5_vits_sweep.py —— 扫 SoVITS 各 epoch，找声纹最优的一版。

固定：base GPT（s1v3）+ 同参考 + 同文本 + seed 42 + speed 1.0
只变：SoVITS 权重（base / e1..e8）
输出：E:/tts-models/acpp/out/v5sweep/{tag}.wav
"""
import os, sys, time, json
import numpy as np, soundfile as sf

REPO = r'G:/_setup/gsv5probe'
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'GPT_SoVITS'))
os.chdir(REPO)
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

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

VDIR = 'SoVITS_weights_v5turbo'
CAND = [('base', _C['vits_weights_path'])]
for ep in [1, 2, 3, 4, 5, 6, 7, 8]:
    import glob
    g = glob.glob('%s/mcconaughey_v5full_df3hp_e%d_s*_l32.pth' % (VDIR, ep))
    if g:
        CAND.append(('e%d' % ep, g[0]))

print('候选 %d 个: %s' % (len(CAND), [c[0] for c in CAND]), flush=True)
t0 = time.time()
tts = TTS(TTS_Config(CFG))
tts.init_t2s_weights(_C['t2s_weights_path'])
print('[load] TTS 初始化 %.1fs' % (time.time() - t0), flush=True)

res = []
for tag, vits in CAND:
    try:
        t0 = time.time()
        tts.init_vits_weights(vits)
        tl = time.time() - t0
        t0 = time.time()
        sr, audio = None, None
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
        el = time.time() - t0
        p = os.path.join(OUT, tag + '.wav')
        sf.write(p, audio, sr)
        d = len(audio) / sr
        print('[ok] %-6s load %.1fs infer %.1fs dur %.2fs -> %s' % (tag, tl, el, d, p), flush=True)
        res.append(dict(tag=tag, dur=round(d, 2), wav=p))
    except Exception as e:
        import traceback; traceback.print_exc()
        print('[FAIL] %s: %s' % (tag, e), flush=True)

json.dump(res, open(OUT + '/sweep.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('\n[done] 共 %d 个' % len(res), flush=True)
