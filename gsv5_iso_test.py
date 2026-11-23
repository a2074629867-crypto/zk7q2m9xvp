# -*- coding: utf-8 -*-
"""gsv5_iso_test.py —— 隔离测试：分别验证 微调SoVITS / 微调GPT 各自的问题。

组合（每个组合用全新 TTS 实例，避免权重串味）：
  1) ft_vits + base_gpt   -> 验证 SoVITS 微调质量（GPT 用官方）
  2) base_vits + ft_gpt   -> 验证 GPT 微调质量（SoVITS 用官方）
  3) ft_vits + ft_gpt_e8  -> 用上一轮（旧库）的 GPT e8
  4) base + base          -> 对照（应复现 base_1 21.00s）

只跑 speed 1.0（1.0x 即可看出时长是否被截断）。
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
OUT = r'E:/tts-models/acpp/out/v5iso'
os.makedirs(OUT, exist_ok=True)

FT_VITS = 'SoVITS_weights_v5turbo/mcconaughey_v5full_df3hp_e8_s928_l32.pth'
FT_GPT15 = 'GPT_weights_v5turbo/mcconaughey_v5full_df3hp-e15.ckpt'
FT_GPT_E8 = 'GPT_weights_v5turbo/mcconaughey_v5full_df3hp-e8.ckpt'

COMBOS = [
    ('1_ftvits_basegpt', FT_VITS, ''),
    ('2_basevits_ftgpt15', '', FT_GPT15),
    ('3_ftvits_ftgpt_e8', FT_VITS, FT_GPT_E8),
    ('4_base_base', '', ''),
]

res = []
for tag, vits, t2s in COMBOS:
    print('\n' + '=' * 62, flush=True)
    print('>>> %s   vits=%s  t2s=%s' % (tag, vits or '(base)', t2s or '(base)'), flush=True)
    print('=' * 62, flush=True)
    try:
        t0 = time.time()
        tts = TTS(TTS_Config(CFG))
        tts.init_vits_weights(vits or _C['vits_weights_path'])
        tts.init_t2s_weights(t2s or _C['t2s_weights_path'])
        print('[load] %.1fs' % (time.time() - t0), flush=True)
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
        print('[ok] %s  dur=%.2fs  推理 %.1fs  -> %s' % (tag, d, el, p), flush=True)
        res.append(dict(tag=tag, dur=round(d, 2), vits=vits or 'base', t2s=t2s or 'base'))
    except Exception as e:
        import traceback; traceback.print_exc()
        print('[FAIL] %s: %s' % (tag, e), flush=True)
        res.append(dict(tag=tag, dur=None, err=str(e)[:120]))
    del tts

json.dump(res, open(OUT + '/iso_result.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('\n=== 汇总（目标时长 ≈21s；明显偏短 = GPT 截断）===', flush=True)
for r in res:
    print('  %-22s %s' % (r['tag'], ('%.2fs' % r['dur']) if r.get('dur') else 'FAIL'), flush=True)
print('[done]', flush=True)
