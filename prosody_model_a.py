# -*- coding: utf-8 -*-
"""Route A: word-level contextual prosody predictor; CPU, no pretrained weights.

prep: align Wonder words by Whisper, extract 5-bin semitone contour and relative log duration.
train: grouped held-out test (last 15% chronological clips), 12% validation from train.
predict: outputs a per-word contour JSON for previously unseen text.
"""
import argparse
import json
import math
import os
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, 'G:/_setup')

import numpy as np
import soundfile as sf
import torch
from torch import nn

ROOT = Path('G:/_setup/route_a')
LIST = Path('G:/GPT-SoVITS/_dataset/wonder.list')
VOCAB = " abcdefghijklmnopqrstuvwxyz'-,.!?;:"
V = {c: i + 1 for i, c in enumerate(VOCAB)}
PITCH_BINS = 5
OUT_DIM = PITCH_BINS + 2  # F0 profile, log word-duration per syllable, log relative energy


def clean(w):
    return re.sub(r"[^a-z']", '', w.lower())


def tokens(text):
    return re.findall(r"[a-zA-Z]+(?:['\-][a-zA-Z]+)*[.,!?;:]?", text)


def syllables(word):
    w = clean(word)
    if not w:
        return 1
    n = len(re.findall(r'[aeiouy]+', w))
    if len(w) > 3 and w.endswith('e') and not w.endswith(('le', 'ye')):
        n -= 1
    return max(1, n)


def ids(word, length=22):
    return [V.get(c, 0) for c in word.lower()[:length]].__add__([0] * max(0, length - len(word)))


def _normal_words(text):
    return [clean(w) for w in tokens(text) if clean(w)]


def extract_one(path, text, whisper):
    from difflib import SequenceMatcher
    from prosody_arc import read_f0, clean_f0
    segs, _ = whisper.transcribe(str(path), language='en', beam_size=5,
                                 word_timestamps=True, vad_filter=False,
                                 condition_on_previous_text=False)
    raw = [w for s in segs for w in (s.words or []) if clean(w.word)]
    expected = tokens(text)
    exp_words = _normal_words(text)
    got = [clean(w.word) for w in raw]
    if not raw or len(exp_words) != len(got) or SequenceMatcher(None, got, exp_words).ratio() < 0.88:
        return None
    duration = sf.info(str(path)).duration
    if duration < 1.0 or duration > 22:
        return None
    f0, ft, _ = read_f0(str(path))
    f0, _ = clean_f0(f0)
    valid = f0 > 0
    if valid.sum() < 10:
        return None
    med = float(np.median(f0[valid]))
    x, sr = sf.read(str(path), dtype='float32')
    if x.ndim > 1:
        x = x.mean(axis=1)
    records = []
    for w, label in zip(raw, expected):
        start, end = max(0, float(w.start)), min(duration, float(w.end))
        if end - start < .065:
            return None
        mask = (ft >= start) & (ft <= end) & valid
        points = np.zeros(PITCH_BINS, dtype=np.float32)
        voiced = int(mask.sum())
        if voiced >= 3:
            vt = ft[mask]
            st = 12 * np.log2(f0[mask] / med)
            points[:] = np.interp(np.linspace(start, end, PITCH_BINS), vt, st)
            points[:] = np.clip(points, -7, 7)
        a, b = int(start * sr), max(int(end * sr), int(start * sr) + 1)
        energy = np.sqrt(np.mean(x[a:b] ** 2) + 1e-10)
        records.append(dict(word=label, pitch=points.tolist(), voiced=voiced >= 3,
                            duration=end - start, syllables=syllables(label), energy=float(energy)))
    dbase = np.median([r['duration'] / r['syllables'] for r in records])
    ebase = np.median([r['energy'] for r in records])
    for r in records:
        r['target'] = r.pop('pitch') + [float(np.clip(np.log((r['duration'] / r['syllables']) / dbase), -1.2, 1.2)),
                                         float(np.clip(np.log(r['energy'] / ebase), -1.2, 1.2))]
    return dict(text=text, path=str(path), words=records)


def prepare():
    from faster_whisper import WhisperModel
    ROOT.mkdir(exist_ok=True)
    all_rows = []
    for line in LIST.read_text(encoding='utf-8').splitlines():
        p = line.split('|', 3)
        if len(p) == 4 and Path(p[0]).exists():
            all_rows.append((p[0], p[3]))
    print('素材 %d 条，加载 whisper small.en...' % len(all_rows), flush=True)
    os.environ['HF_HOME'] = 'C:/Users/86178/.cache/huggingface'
    os.environ['HF_HUB_OFFLINE'] = '1'
    whisper = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=6)
    records = []
    for i, (path, text) in enumerate(all_rows):
        try:
            rec = extract_one(path, text, whisper)
            if rec:
                records.append(rec)
        except Exception as e:
            print('skip %d %s' % (i, str(e)[:100]), flush=True)
        if (i + 1) % 25 == 0:
            print('  %d/%d accepted=%d' % (i + 1, len(all_rows), len(records)), flush=True)
    output = ROOT / 'features.json'
    output.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
    print('保存 %d/%d 句，%d 词 -> %s' % (len(records), len(all_rows),
          sum(len(r['words']) for r in records), output), flush=True)


class Model(nn.Module):
    def __init__(self, hidden=64):
        super().__init__()
        self.embed = nn.Embedding(len(VOCAB) + 1, 32, padding_idx=0)
        self.char_conv = nn.Sequential(nn.Conv1d(32, 48, 3, padding=1), nn.ReLU(),
                                       nn.Conv1d(48, 48, 3, padding=1), nn.ReLU())
        self.gru = nn.GRU(48 + 3, hidden, batch_first=True, bidirectional=True)
        self.head = nn.Sequential(nn.Linear(hidden * 2, 96), nn.ReLU(), nn.Dropout(.15),
                                  nn.Linear(96, OUT_DIM))

    def forward(self, chars, cues):
        b, n, c = chars.shape
        x = self.embed(chars.reshape(b * n, c)).transpose(1, 2)
        x = self.char_conv(x)
        m = (chars.reshape(b * n, c) != 0).unsqueeze(1)
        x = x.masked_fill(~m, -1e4).amax(2).reshape(b, n, -1)
        x = torch.cat([x, cues], dim=-1)
        h, _ = self.gru(x)
        return self.head(h)


def encode(rec):
    words = rec['words']
    n = len(words)
    chars = np.array([ids(r['word']) for r in words], dtype=np.int64)
    cues = np.array([[i / max(1, n - 1), min(4, r['syllables']) / 4,
                      1.0 if r['word'][-1:] in ',.;:!?' else 0.0]
                     for i, r in enumerate(words)], dtype=np.float32)
    y = np.array([r['target'] for r in words], dtype=np.float32)
    voiced = np.array([r['voiced'] for r in words], dtype=np.float32)
    return (torch.from_numpy(chars)[None], torch.from_numpy(cues)[None],
            torch.from_numpy(y)[None], torch.from_numpy(voiced)[None])


def metric(model, records, baseline=None):
    model.eval()
    pitch_abs = []
    pitch_base = []
    dur_abs = []
    dur_base = []
    corr = []
    with torch.no_grad():
        for rec in records:
            c, cue, y, v = encode(rec)
            pred = model(c, cue)[0].numpy()
            truth = y[0].numpy()
            mask = v[0].numpy().astype(bool)
            if mask.any():
                pitch_abs.extend(abs(pred[mask, :5] - truth[mask, :5]).ravel())
                pitch_base.extend(abs(truth[mask, :5]).ravel())
            dur_abs.extend(abs(pred[:, 5] - truth[:, 5]))
            dur_base.extend(abs(truth[:, 5]))
            if mask.sum() >= 5:
                p, t = pred[mask, :5].mean(1), truth[mask, :5].mean(1)
                if p.std() > .01 and t.std() > .01:
                    corr.append(float(np.corrcoef(p, t)[0, 1]))
    return dict(pitch_mae=float(np.mean(pitch_abs)), pitch_baseline_mae=float(np.mean(pitch_base)),
                dur_mae=float(np.mean(dur_abs)), dur_baseline_mae=float(np.mean(dur_base)),
                word_pitch_corr=float(np.mean(corr)) if corr else None,
                evaluated_words=int(len(dur_abs)))


def train(epochs=70):
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    torch.set_num_threads(4)
    records = json.loads((ROOT / 'features.json').read_text(encoding='utf-8'))
    if len(records) < 110:
        raise RuntimeError('高质量对齐句不足：%d (<110)' % len(records))
    # File order follows source chronology; last 15% completely held out.
    pivot = int(len(records) * .85)
    test = records[pivot:]
    earlier = records[:pivot]
    rng = random.Random(42)
    rng.shuffle(earlier)
    val_len = max(15, int(len(earlier) * .13))
    train_rows, val = earlier[val_len:], earlier[:val_len]
    model = Model()
    opt = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.02)
    best, best_epoch, bad = 1e9, 0, 0
    start = time.time()
    for ep in range(1, epochs + 1):
        rng.shuffle(train_rows)
        model.train()
        losses = []
        for rec in train_rows:
            c, cue, y, v = encode(rec)
            pred = model(c, cue)
            vp = v.unsqueeze(-1)
            pitch = (((pred[:, :, :5] - y[:, :, :5]) ** 2) * vp).sum() / (vp.sum() * 5 + 1e-5)
            other = (pred[:, :, 5:] - y[:, :, 5:]).square().mean()
            loss = pitch + .35 * other
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1)
            opt.step()
            losses.append(float(loss))
        vm = metric(model, val)
        objective = vm['pitch_mae'] + .35 * vm['dur_mae']
        if objective < best - .003:
            best, best_epoch, bad = objective, ep, 0
            torch.save(dict(state=model.state_dict(), epoch=ep, train=len(train_rows), val=len(val),
                            test=len(test), vocab=VOCAB), ROOT / 'best.pt')
        else:
            bad += 1
        if ep == 1 or ep % 5 == 0:
            print('epoch=%03d train=%.3f val_pitch=%.3f val_duration=%.3f best=%03d time=%ds' %
                  (ep, np.mean(losses), vm['pitch_mae'], vm['dur_mae'], best_epoch, time.time()-start), flush=True)
        if bad >= 12:
            print('early stop at epoch', ep, flush=True)
            break
    model.load_state_dict(torch.load(ROOT / 'best.pt', map_location='cpu', weights_only=False)['state'])
    result = dict(n_sentences=len(records), train=len(train_rows), val=len(val), test=len(test),
                  best_epoch=best_epoch, test_metrics=metric(model, test),
                  split='chronological final 15% held-out by source order; no augmentation')
    (ROOT / 'metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('HELD_OUT', json.dumps(result, ensure_ascii=False), flush=True)


def predict(text):
    path = ROOT / 'best.pt'
    model = Model()
    model.load_state_dict(torch.load(path, map_location='cpu', weights_only=False)['state'])
    model.eval()
    words = tokens(text)
    if not words:
        raise ValueError('输入中没有英文词')
    rec = dict(words=[dict(word=w, syllables=syllables(w), target=[0.0]*OUT_DIM, voiced=True) for w in words])
    c, cue, _, _ = encode(rec)
    with torch.no_grad():
        p = model(c, cue)[0].numpy()
    result = [dict(word=w, f0_st=[round(float(z), 2) for z in np.clip(p[i, :5], -7, 7)],
                   dur_factor=round(float(np.exp(np.clip(p[i, 5], -1.2, 1.2))), 3),
                   energy_factor=round(float(np.exp(np.clip(p[i, 6], -1.2, 1.2))), 3))
              for i, w in enumerate(words)]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('command', choices=['prep', 'train', 'predict'])
    ap.add_argument('--text', default='')
    ap.add_argument('--epochs', type=int, default=70)
    a = ap.parse_args()
    if a.command == 'prep':
        prepare()
    elif a.command == 'train':
        train(a.epochs)
    else:
        predict(a.text)
