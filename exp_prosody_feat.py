# -*- coding: utf-8 -*-
"""快速实验：加强特征 + 提高容量，验证词级 F0 预测的上升空间。

对比基线（原模型 best.pt）：test pitch_mae=1.150 (base 1.198) dur=0.358 corr=0.231

特征 v2 = [位置, 音节数/4, 逗号, 句末标点, 功能词, 句末词, 词长/10, 前词标点]
"""
import json
import random
import sys
import time

import numpy as np
import torch
from torch import nn

sys.path.insert(0, 'G:/_setup')
import prosody_model_a as M

FUNC = set('''a an the and or but of to in on at for with as that this these those it its
is was are were be been being he she they we you i his her their our your my him them us me
not no so if when while then than there here up down out off over from by into onto upon
about after before again just only very too also well oh ah like would could should will
can may might must have has had do does did am than now'''.split())

CUES2 = 8


def encode_v2(rec):
    words = rec['words']
    n = len(words)
    chars = np.array([M.ids(r['word']) for r in words], dtype=np.int64)
    cues = []
    for i, r in enumerate(words):
        w = r['word']
        tail = w[-1:] if w else ''
        prev_tail = words[i - 1]['word'][-1:] if i > 0 else ''
        cues.append([
            i / max(1, n - 1),
            min(4, r['syllables']) / 4,
            1.0 if tail == ',' else 0.0,
            1.0 if tail in '.!?' else 0.0,
            1.0 if M.clean(w) in FUNC else 0.0,
            1.0 if i == n - 1 else 0.0,
            min(10, len(M.clean(w))) / 10,
            1.0 if prev_tail in ',.;:' else 0.0,
        ])
    y = np.array([r['target'] for r in words], dtype=np.float32)
    voiced = np.array([r['voiced'] for r in words], dtype=np.float32)
    return (torch.from_numpy(chars)[None], torch.from_numpy(np.array(cues, dtype=np.float32))[None],
            torch.from_numpy(y)[None], torch.from_numpy(voiced)[None])


class Model2(nn.Module):
    def __init__(self, hidden=128, ncue=CUES2):
        super().__init__()
        self.embed = nn.Embedding(len(M.VOCAB) + 1, 32, padding_idx=0)
        self.char_conv = nn.Sequential(nn.Conv1d(32, 48, 3, padding=1), nn.ReLU(),
                                       nn.Conv1d(48, 48, 3, padding=1), nn.ReLU())
        self.gru = nn.GRU(48 + ncue, hidden, batch_first=True, bidirectional=True)
        self.head = nn.Sequential(nn.Linear(hidden * 2, 128), nn.ReLU(), nn.Dropout(.2),
                                  nn.Linear(128, M.OUT_DIM))

    def forward(self, chars, cues):
        b, n, c = chars.shape
        x = self.embed(chars.reshape(b * n, c)).transpose(1, 2)
        x = self.char_conv(x)
        m = (chars.reshape(b * n, c) != 0).unsqueeze(1)
        x = x.masked_fill(~m, -1e4).amax(2).reshape(b, n, -1)
        x = torch.cat([x, cues], dim=-1)
        h, _ = self.gru(x)
        return self.head(h)


def metric2(model, records, enc):
    model.eval()
    pa, pb, da, db, corr = [], [], [], [], []
    with torch.no_grad():
        for rec in records:
            c, cue, y, v = enc(rec)
            p = model(c, cue)[0].numpy()
            t = y[0].numpy()
            mask = v[0].numpy().astype(bool)
            if mask.any():
                pa.extend(abs(p[mask, :5] - t[mask, :5]).ravel())
                pb.extend(abs(t[mask, :5]).ravel())
            da.extend(abs(p[:, 5] - t[:, 5]))
            db.extend(abs(t[:, 5]))
            if mask.sum() >= 5:
                pp, tt = p[mask, :5].mean(1), t[mask, :5].mean(1)
                if pp.std() > .01 and tt.std() > .01:
                    corr.append(float(np.corrcoef(pp, tt)[0, 1]))
    return (float(np.mean(pa)), float(np.mean(pb)), float(np.mean(da)), float(np.mean(db)),
            float(np.mean(corr)) if corr else None)


def run(tag, hidden, epochs, lr, wd, enc):
    random.seed(42); np.random.seed(42); torch.manual_seed(42)
    torch.set_num_threads(4)
    records = json.loads((M.ROOT / 'features.json').read_text(encoding='utf-8'))
    pivot = int(len(records) * .85)
    test = records[pivot:]
    earlier = records[:pivot][:]
    rng = random.Random(42)
    rng.shuffle(earlier)
    val_len = max(15, int(len(earlier) * .13))
    train_rows, val = earlier[val_len:], earlier[:val_len]

    model = Model2(hidden=hidden)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    best, best_ep, bad = 1e9, 0, 0
    t0 = time.time()
    for ep in range(1, epochs + 1):
        rng.shuffle(train_rows)
        model.train()
        for rec in train_rows:
            c, cue, y, v = enc(rec)
            pred = model(c, cue)
            vp = v.unsqueeze(-1)
            pitch = (((pred[:, :, :5] - y[:, :, :5]) ** 2) * vp).sum() / (vp.sum() * 5 + 1e-5)
            other = (pred[:, :, 5:] - y[:, :, 5:]).square().mean()
            loss = pitch + .35 * other
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1)
            opt.step()
        pa, pb, da, db, _ = metric2(model, val, enc)
        obj = pa + .35 * da
        if obj < best - .003:
            best, best_ep, bad = obj, ep, 0
            torch.save(model.state_dict(), M.ROOT / ('exp_%s.pt' % tag))
        else:
            bad += 1
        if bad >= 15:
            break
    model.load_state_dict(torch.load(M.ROOT / ('exp_%s.pt' % tag), map_location='cpu'))
    tr = metric2(model, train_rows, enc)
    va = metric2(model, val, enc)
    te = metric2(model, test, enc)
    print('%-10s h=%d ep=%d(best%02d) | train p=%.3f d=%.3f c=%.2f | val p=%.3f c=%.2f | TEST p=%.3f (base %.3f) d=%.3f (base %.3f) corr=%.3f | %ds'
          % (tag, hidden, epochs, best_ep, tr[0], tr[2], tr[4] or 0, va[0], va[4] or 0,
             te[0], te[1], te[2], te[3], te[4] or 0, time.time() - t0), flush=True)
    return te


if __name__ == '__main__':
    only = sys.argv[1] if len(sys.argv) > 1 else ''
    if only in ('', 'v2h64'):
        run('v2h64', 64, 120, .0015, .03, encode_v2)
    if only in ('', 'v2h128'):
        run('v2h128', 128, 120, .0015, .03, encode_v2)
