# -*- coding: utf-8 -*-
"""gsv5_long_ref_sweep.py —— 「更长的参考音频」扫描

固定 GPT(v6-e18) + 零样本 SoVITS(s2Gv5turbo)，只换参考音频长度（8.5s -> 28s）。
全部起于 566.14s，同一段话越读越长。
必须：先跑一次 warmup 丢弃（新进程首次推理会失控 n≈1499/60s）。
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
REFS_JSON = os.environ.get('REFS_JSON', r'E:/tts-models/acpp/out/refs_long/long_refs.json')
REFS = json.load(open(REFS_JSON, encoding='utf-8'))
# argv: tag 过滤（逗号分隔）+ 重复次数（默认 2，第 1 次可能撞冷启动伪影，用最后一次）
ONLY = [t for t in (sys.argv[1].split(',') if len(sys.argv) > 1 and sys.argv[1] else []) if t]
REPEAT = int(sys.argv[2]) if len(sys.argv) > 2 else 2
if ONLY:
    REFS = [r for r in REFS if r['tag'] in ONLY]
OUT = r'E:/tts-models/acpp/out/refs_long/out'
os.makedirs(OUT, exist_ok=True)
print('参考 %d 个: %s | 每个跑 %d 次' % (len(REFS), ','.join(r['tag'] for r in REFS), REPEAT), flush=True)

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
c = REFS[0]
t0 = time.time()
try:
    sr, a, n = run(c['path'], c['text'])
    print('[WARM] %.2fs n=%s (%.1fs) 丢失' % (len(a) / sr, n, time.time() - t0), flush=True)
except Exception as e:
    print('[WARM-ERR] %s' % str(e)[:200], flush=True)

res = []
for i, c in enumerate(REFS):
    last = None
    for k in range(REPEAT):
        t0 = time.time()
        try:
            sr, a, n = run(c['path'], c['text'])
        except Exception as e:
            print('[ERR ] %-6s %s' % (c['tag'], str(e)[:160]), flush=True)
            last = None; break
        d = len(a) / sr
        print('  [%d/%d] %-6s ref=%5.2fs try%d  out=%6.2fs n=%-4s (%.1fs)' % (
            i + 1, len(REFS), c['tag'], c['dur'], k + 1, d, n, time.time() - t0), flush=True)
        last = (sr, a, n, d)
    if last is None:
        res.append(dict(tag=c['tag'], err='fail')); continue
    sr, a, n, d = last
    p = os.path.join(OUT, c['tag'] + '.wav')
    sf.write(p, a, sr)
    res.append(dict(tag=c['tag'], ref_dur=c['dur'], ref_npart=c['n_part'],
                    ref_nword=c['n_word'], out_dur=round(d, 2), n=n,
                    path=p, ref_path=c['path'], ref_text=c['text']))

json.dump(res, open(os.path.join(OUT, 'long_sweep.json'), 'w'), ensure_ascii=False, indent=1)
print('DONE %d/%d' % (len([r for r in res if 'out_dur' in r]), len(REFS)), flush=True)
