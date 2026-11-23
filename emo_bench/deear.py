# -*- coding: utf-8 -*-
"""DeEAR 表达力评分封装（Interspeech 2026 Oral, FreedomIntelligence）

论文：Decoding the Ear (arXiv 2510.20513)
  — 三维分解：Emotion / Prosody / Spontaneity
  — 与人耳 SRCC = 0.86（<500 条标注样本）；系统排序 SRCC = 0.96
  — 融合分 0–100（XGBoost 三输入）

模型两段：
  Stage1  ParallelExpressivenessModel (Wav2Vec2-large) → score_arousal / prosody / nature
  Stage2  XGBoost → score_expressive (0–100)

用法：
  python deear.py --dir <wav目录> --out out/deear_xxx.jsonl
"""
import os, sys, json, argparse, logging
import numpy as np
import torch
import torch.nn as nn
import torchaudio
from torch.utils.data import Dataset, DataLoader
from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2Model, Wav2Vec2PreTrainedModel

MODEL_DIR = "G:/_setup/models/ms/FreedomIntelligence/DeEAR_Base"
XGB_PATH = "G:/_setup/xgb_model.json"
SR = 16000
MAX_S = 15.0


class RegressionHead(nn.Module):
    def __init__(self, input_dim, hidden_dim=1024, dropout=0.1):
        super().__init__()
        self.dense = nn.Linear(input_dim, hidden_dim)
        self.dropout = nn.Dropout(dropout)
        self.out_proj = nn.Linear(hidden_dim, 1)

    def forward(self, features):
        x = self.dropout(features)
        x = self.dense(x)
        x = torch.tanh(x)
        x = self.dropout(x)
        return self.out_proj(x)


class ParallelExpressivenessModel(Wav2Vec2PreTrainedModel):
    def __init__(self, config):
        super().__init__(config)
        self.wav2vec2 = Wav2Vec2Model(config)
        self.head_arousal = RegressionHead(config.hidden_size)
        self.head_prosody = RegressionHead(config.hidden_size)
        self.head_nature = RegressionHead(config.hidden_size)

    def forward(self, input_values, attention_mask=None):
        out = self.wav2vec2(input_values, attention_mask=attention_mask)
        pooled = torch.mean(out.last_hidden_state, dim=1)
        return {
            "s_arousal": self.head_arousal(pooled).squeeze(-1),
            "s_prosody": self.head_prosody(pooled).squeeze(-1),
            "s_nature": self.head_nature(pooled).squeeze(-1),
        }


def _load_wav(path, fe):
    wav, sr = torchaudio.load(path)
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    if sr != SR:
        wav = torchaudio.transforms.Resample(sr, SR)(wav)
    n = int(MAX_S * SR)
    if wav.shape[1] > n:
        wav = wav[:, :n]
    return wav.squeeze(0).numpy()


class _DS(Dataset):
    def __init__(self, files, fe):
        self.files = files
        self.fe = fe

    def __len__(self):
        return len(self.files)

    def __getitem__(self, i):
        p = self.files[i]
        try:
            return p, _load_wav(p, self.fe)
        except Exception as e:
            logging.warning("skip %s: %s", p, e)
            return p, None


def _collate(batch):
    ok = [(p, w) for p, w in batch if w is not None]
    if not ok:
        return [], None
    paths = [p for p, _ in ok]
    feats = [{"input_values": w} for _, w in ok]
    return paths, feats


class DeEAR:
    def __init__(self, model_dir=MODEL_DIR, xgb_path=XGB_PATH, device="cpu"):
        import xgboost as xgb
        self.fe = Wav2Vec2FeatureExtractor.from_pretrained(model_dir)
        self.model = ParallelExpressivenessModel.from_pretrained(model_dir).to(device).eval()
        self.dev = torch.device(device)
        self.xgb = xgb.Booster()
        self.xgb.load_model(xgb_path)

    def score(self, files, batch_size=8):
        import pandas as pd
        rows = []
        dl = DataLoader(_DS(files, self.fe), batch_size=batch_size, collate_fn=_collate, num_workers=0)
        with torch.no_grad():
            for paths, feats in dl:
                if not paths:
                    continue
                padded = self.fe.pad(feats, return_tensors="pt", padding=True)
                padded = {k: v.to(self.dev) for k, v in padded.items()}
                pred = self.model(input_values=padded["input_values"],
                                  attention_mask=padded.get("attention_mask"))
                for i, p in enumerate(paths):
                    rows.append({
                        "path": p,
                        "score_arousal": float(pred["s_arousal"][i]),
                        "score_prosody": float(pred["s_prosody"][i]),
                        "score_nature": float(pred["score_nature"][i]) if "score_nature" in pred else float(pred["s_nature"][i]),
                    })
        if not rows:
            return []
        df = pd.DataFrame(rows)
        df["score_expressive"] = self.xgb.predict(
            __import__("xgboost").DMatrix(df[["score_arousal", "score_prosody", "score_nature"]]))
        return df.to_dict("records")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    ap.add_argument("--files", default=None, help="文本文件，每行一个 wav 路径")
    ap.add_argument("--out", default=None)
    ap.add_argument("--batch", type=int, default=8)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if a.files:
        files = [l.strip() for l in open(a.files, encoding="utf-8") if l.strip()]
    else:
        files = []
        for r, _, fs in os.walk(a.dir):
            for f in fs:
                if f.lower().endswith(".wav"):
                    files.append(os.path.join(r, f))
    files.sort()
    print("files", len(files), flush=True)
    d = DeEAR()
    rows = d.score(files, a.batch)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    vals = [r["score_expressive"] for r in rows]
    if vals:
        print("expressive  n=%d  mean=%.1f  p10=%.1f  p50=%.1f  p90=%.1f" % (
            len(vals), np.mean(vals), np.percentile(vals, 10), np.percentile(vals, 50), np.percentile(vals, 90)))
    return rows


if __name__ == "__main__":
    main()
