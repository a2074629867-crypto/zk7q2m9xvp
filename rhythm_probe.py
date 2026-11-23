# -*- coding: utf-8 -*-
"""rhythm_probe.py —— 韵律保真度直接测量

核心思路：GSV v5turbo 的 AR 输出 = semantic token 序列，25Hz。
         token 数 <=> 该文本被念了多久（含停顿）。
         所以「模型认为这段话要念多久」vs「真人念了多久」就是韵律保真度。

两种测法：
  A) 短句：直接用 v6 切片自己的文本（真人时长已知）
  B) 长段：把连续切片文本合并（模拟真实段落），对比真人总 token

指标：ratio = n_model / n_human。1.0 = 完美复刻韵律；<1 = 偏快。

用 GPT_weights_v6/e18 + 零样本 s2Gv5turbo + baseA 参考。
必须 warmup（冷启动首跑会吐 1499 token/60s 的伪影）。
"""
import os, sys, time, json
import numpy as np

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
HZ = 25.0
OUT = r'E:/tts-models/acpp/out/rhythm'
os.makedirs(OUT, exist_ok=True)

print('[load]', flush=True)
t0 = time.time()
tts = TTS(TTS_Config(CFG))
print('[load] %.1fs' % (time.time() - t0), flush=True)

# ---------- patch 真实类：只跑 AR ----------
REC = {}
CLS = type(tts.t2s_model.model)


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
        return [t[:K] for t in y_list], [min(int(i), K) for i in idx_list]
    wrapper.__name__ = 'wrapper'
    return wrapper


for nm in ('infer_panel_batch_infer', 'infer_panel_naive', 'infer_panel_naive_batched'):
    if nm in CLS.__dict__:
        setattr(CLS, nm, _make(CLS.__dict__[nm]))


def run_text(text, verbose=False):
    REC.clear()
    args = dict(
        text=text, text_lang='en',
        ref_audio_path=REF, prompt_text=REF_TEXT, prompt_lang='en',
        top_k=15, top_p=1, temperature=1,
        text_split_method='cut0', batch_size=1,
        speed_factor=1.0, seed=42,
        parallel_infer=True, repetition_penalty=1.35,
        use_cuda_graph=False, use_flash_attention=False,
    )
    t = time.time()
    for _ in tts.run(args):
        pass
    n = REC.get('n')
    return n, time.time() - t


# ---------- warmup（丢弃） ----------
print('\n[WARM] 冷启动预热（结果丢弃）...', flush=True)
wn, wt = run_text('Rising he said with a smile.')
print('[WARM] n=%s (%.0fs)  <- 预期失控值 1499 或异常值' % (wn, wt), flush=True)
wn2, wt2 = run_text('Rising he said with a smile.')
print('[WARM] 二次 n=%s (%.0fs)  <- 应恢复正常' % (wn2, wt2), flush=True)

# ---------- 短句测试 ----------
probe = json.load(open(r'G:/_setup/rhythm_probe.json', encoding='utf-8'))
print('\n===== A) 短句：模型预测时长 vs 真人时长 =====')
print('  %-9s %-9s %-7s %-7s  %s' % ('真人', '模型', 'ratio', '真人wpm', '文本'))
rows = []
for r in probe:
    n, el = run_text(r['text'])
    if not n:
        print('  MISS %s' % r['text'][:40], flush=True)
        continue
    md = n / HZ
    ratio = n / r['sem']
    rows.append(dict(name=r['name'], text=r['text'], dur_h=r['dur'], sem_h=r['sem'],
                     n=n, dur_m=md, ratio=ratio, wpm_h=len(r['text'].split()) / r['dur'] * 60))
    print('  %6.2fs  %6.2fs  %6.3f   %5.0f   %s' % (r['dur'], md, ratio, rows[-1]['wpm_h'], r['text'][:46]), flush=True)

if rows:
    rr = np.array([x['ratio'] for x in rows])
    print('\n  短句 ratio: 中位 %.3f  均值 %.3f  范围 %.2f~%.2f' % (
        np.median(rr), rr.mean(), rr.min(), rr.max()))
    print('  相关系数(真人token vs 模型token): %.3f' % np.corrcoef(
        [x['sem_h'] for x in rows], [x['n'] for x in rows])[0, 1])

# ---------- 长段测试：连续切片拼接 ----------
print('\n===== B) 长段：连续切片合并（模拟真实段落）=====', flush=True)
rows.sort(key=lambda x: x['dur_h'])
chunks = [
    ('L5', rows[:3]),
    ('L8', rows[:5]),
    ('L12', rows),
]
long_rows = []
for tag, sub in chunks:
    if not sub:
        continue
    text = ' '.join(x['text'].strip() for x in sub)
    sem_h = sum(x['sem_h'] for x in sub)
    dur_h = sum(x['dur_h'] for x in sub)
    n, el = run_text(text)
    if not n:
        print('  MISS %s' % tag, flush=True)
        continue
    md = n / HZ
    print('  %-4s %2d词 真人%5.2fs/%3dtok 模型%5.2fs/%3dtok  ratio=%.3f  (%.0fs)' % (
        tag, len(text.split()), dur_h, sem_h, md, n, n / sem_h, el), flush=True)
    long_rows.append(dict(tag=tag, words=len(text.split()), dur_h=dur_h, sem_h=sem_h,
                          n=n, dur_m=md, ratio=n / sem_h, text=text))

json.dump(dict(short=rows, long=long_rows), open(os.path.join(OUT, 'rhythm.json'), 'w'),
          ensure_ascii=False, indent=1)
print('\n已写 %s' % os.path.join(OUT, 'rhythm.json'))
print('DONE')
