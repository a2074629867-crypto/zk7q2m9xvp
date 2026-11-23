# -*- coding: utf-8 -*-
"""gsv5_v6_sweep_ar.py —— v6 逐 epoch 快速扫描（只跑 AR，跳过 VITS 解码）

原理：patch 实例真实类的方法，记录真实 AR token 数后把结果截断成 4 token，
      VITS 只解 4 token -> 极快。n / 25Hz = 输出时长（秒）。

注意：TTS.py 走的是顶层 `AR` 包（sys.path 含 repo/GPT_SoVITS），
      与 `import GPT_SoVITS.AR...` 不是同一个模块对象，
      因此必须在 TTS 实例化后 patch `type(tts.t2s_model.model)`。
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
OUT = r'E:/tts-models/acpp/out/v6sweep'
os.makedirs(OUT, exist_ok=True)

print('TEXT 词数: %d' % len(TEXT.split()), flush=True)
t0 = time.time()
tts = TTS(TTS_Config(CFG))
print('[load TTS] %.1fs' % (time.time() - t0), flush=True)

# ---------- patch 真实类 ----------
REC = {}
CLS = type(tts.t2s_model.model)
print('[patch] target class = %s.%s' % (CLS.__module__, CLS.__name__), flush=True)

def _make(orig):
    def wrapper(self, *a, **kw):
        y_list, idx_list = orig(self, *a, **kw)
        try:
            n = int(sum(int(i) for i in idx_list))
        except Exception:
            n = int(y_list[0].shape[-1]) if len(y_list) else 0
        REC['n'] = n
        REC['per'] = [int(i) for i in idx_list]
        K = 4
        y2 = [t[:K] for t in y_list]
        i2 = [min(int(i), K) for i in idx_list]
        return y2, i2
    wrapper.__name__ = getattr(orig, '__name__', 'wrapper')
    return wrapper

PATCHED = []
for nm in ('infer_panel_batch_infer', 'infer_panel_naive', 'infer_panel_naive_batched'):
    if nm in CLS.__dict__:
        setattr(CLS, nm, _make(CLS.__dict__[nm]))
        PATCHED.append(nm)
print('[patch] %s' % PATCHED, flush=True)

# 自检：绑定后应拿到 wrapper
b = getattr(tts.t2s_model.model, 'infer_panel_batch_infer')
print('[patch] bound %s -> %s' % (getattr(b, '__name__', '?'), 'OK' if getattr(b, '__name__', '') == 'wrapper' else 'FAIL'), flush=True)

GPT_DIR = 'GPT_weights_v6/'
BASE = PM + '/s1v3.ckpt'
EPS = ['e%d' % i for i in range(1, 21)]

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
def run_one(tag, path):
    if not os.path.exists(path):
        print('[MISS] %s -> %s' % (tag, path), flush=True)
        res.append(dict(tag=tag, n=None, dur=None, err='missing')); return
    REC.clear()
    try:
        tts.init_t2s_weights(path)
    except Exception as e:
        print('[ERRload] %s %s' % (tag, str(e)[:120]), flush=True)
        res.append(dict(tag=tag, n=None, dur=None, err='load:' + str(e)[:80])); return
    t0 = time.time()
    try:
        for _out in tts.run(RUN):
            pass
    except Exception as e:
        print('[ERR ] %-6s %s' % (tag, str(e)[:130]), flush=True)
        res.append(dict(tag=tag, n=REC.get('n'), dur=None, err=str(e)[:100])); return
    el = time.time() - t0
    n = REC.get('n')
    dur = (n / 25.0) if n else None
    v = ''
    if dur is not None:
        v = 'OK 完整' if dur > 15 else ('偏短' if dur > 5 else '崩(截断)')
    print('[AR  ] %-6s n=%-5s dur=%6.2fs  %s  (%.1fs)' % (tag, n, dur if dur else 0, v, el), flush=True)
    res.append(dict(tag=tag, n=n, dur=round(dur, 2) if dur else None))

print('\n===== base 基线 =====', flush=True)
run_one('base', BASE)
print('\n===== 逐 epoch =====', flush=True)
for e in EPS:
    run_one(e, GPT_DIR + 'mcconaughey_v6-%s.ckpt' % e)

json.dump(res, open(OUT + '/sweep_ar_result.json', 'w'), ensure_ascii=False, indent=1)
print('\n===== 汇总 =====', flush=True)
for r in res:
    print('  %-6s %-8s %s' % (r['tag'], ('%.2fs' % r['dur']) if r.get('dur') else 'ERR', r.get('err', '')), flush=True)
print('DONE', flush=True)
