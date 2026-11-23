# -*- coding: utf-8 -*-
"""gsv5_mask_experiment.py —— 决定性实验：验证训练侧 mask 与数据填充方向是否错配。

逻辑：
- 官方 s1v3.ckpt 是在「正确设置」下训练出来的（2025-02 时代，旧代码 make_pad_mask + 右填充数据）
- 对同一批真实训练数据，评估两种 mask 下的 loss / top3_acc：
    配置 A：make_pad_mask_left（当前代码，疑似错配 —— 把真实 token 屏蔽）
    配置 B：make_pad_mask    （右填充版，与 batch_sequences 的右填充匹配）
- 若 s1v3 在 B 下 loss 明显更低 -> 证明当前代码的 A 是错的（训练侧错配 bug）
"""
import os, sys, numpy as np, torch

REPO = r'G:/_setup/gsv5probe'
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'GPT_SoVITS'))
os.chdir(REPO)
os.environ['version'] = 'v5turbo'
os.environ['hz'] = '25hz'
os.environ.setdefault('NLTK_DATA', 'G:/nltk_data')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

from AR.data.dataset import Text2SemanticDataset
from AR.models.t2s_lightning_module import Text2SemanticLightningModule
import AR.models.t2s_model as TM
import AR.models.utils as U

D = 'logs/mcconaughey_v5full_df3hp'
ds = Text2SemanticDataset(phoneme_path=D + '/2-name2text.txt',
                          semantic_path=D + '/6-name2semantic.tsv')
print('dataset len: %d' % len(ds), flush=True)

lens = [len(ds.semantic_phoneme[i][1]) for i in range(len(ds))]
lens = np.array(lens)
order = np.argsort(lens)
# 选 4 个长度差很大的样本（最短 / 中 / 长 / 最长）
ids = [int(order[0]), int(order[len(order) // 3]), int(order[2 * len(order) // 3]), int(order[-1])]
items = [ds[i] for i in ids]
print()
print('选取样本：')
for i, it in zip(ids, items):
    print('  ds[%d]: phoneme=%d semantic=%d' % (i, it['phoneme_ids_len'], it['semantic_ids_len']))

batch = ds.collate(items)
x = batch['phoneme_ids']
x_lens = batch['phoneme_ids_len']
y = batch['semantic_ids']
y_lens = batch['semantic_ids_len']
bert = batch['bert_feature']

print()
print('phoneme 张量形状: %s  (max len = %d)' % (tuple(x.shape), int(x_lens.max())))
print('检查填充方向：样本0 前8位 = %s' % x[0, :8].tolist())
print('              样本0 后8位 = %s' % x[0, -8:].tolist())
print('  -> 若真实 token 在前、尾部全 0，则为右填充')

print()
print('加载 s1v3.ckpt ...', flush=True)
d = torch.load('GPT_SoVITS/pretrained_models/s1v3.ckpt', map_location='cpu', weights_only=False)
cfg = d['config']
model = Text2SemanticLightningModule(cfg, '****', is_train=False)
model.load_state_dict(d['weight'])
model = model.eval()
m = model.model

# 先做 mask 语义自检
with torch.no_grad():
    mA = U.make_pad_mask_left(x_lens)
    mB = U.make_pad_mask(x_lens)
print()
print('mask 对照（True=被屏蔽）：')
for i in range(len(ids)):
    real = (x[i] != 0).nonzero().flatten().tolist()
    maskA = mA[i].nonzero().flatten().tolist()
    maskB = mB[i].nonzero().flatten().tolist()
    print('  样本%d: 真实token位=%d个[0..%d] | A屏蔽位=%s | B屏蔽位=%s' % (
        i, len(real), real[-1] if real else -1,
        ('前%d个' % len(maskA)) if len(maskA) else '无',
        ('后%d个' % len(maskB)) if len(maskB) else '无'))

print()
print('===== 配置 A：当前代码（make_pad_mask_left）=====', flush=True)
with torch.no_grad():
    lossA, accA = m.forward_old(x, x_lens, y, y_lens, bert)
print('  loss = %.1f   top3_acc_avg = %.4f' % (lossA.item(), accA), flush=True)

print()
print('===== 配置 B：make_pad_mask（右填充版）=====', flush=True)
_orig = TM.make_pad_mask_left
TM.make_pad_mask_left = U.make_pad_mask   # monkeypatch
with torch.no_grad():
    lossB, accB = m.forward_old(x, x_lens, y, y_lens, bert)
TM.make_pad_mask_left = _orig
print('  loss = %.1f   top3_acc_avg = %.4f' % (lossB.item(), accB), flush=True)

print()
print('===== 汇总（batch n=%d）=====' % len(ids))
tot_tok = int(y_lens.sum())
print('  配置 A (left mask, 当前): loss_mean/token = %.4f | top3 = %.4f' % (lossA.item() / tot_tok, accA))
print('  配置 B (right mask)     : loss_mean/token = %.4f | top3 = %.4f' % (lossB.item() / tot_tok, accB))
print()
if lossB.item() < lossA.item() * 0.8:
    print('  >>> 结论：B 明显优于 A —— s1v3（正确训练的权重）在 A 下崩坏，实锤当前代码训练侧错配！')
elif lossA.item() < lossB.item() * 0.8:
    print('  >>> 结论：A 明显优于 B —— 出乎预料，说明 left mask 才是对的（需重新分析）')
else:
    print('  >>> 两者接近，此实验不能区分（换更多样本/更长 batch 再试）')
print('DONE', flush=True)
