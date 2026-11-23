"""Wespeaker ResNet ONNX 声纹嵌入（Kaldi fbank，无需 wespeaker 库）。

用法：
    from sv_onnx import SV
    m = SV()                      # 默认 resnet293
    e = m.embed("x.wav")          # 256 维，已 L2 归一化
"""
import os
import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly
from math import gcd
import onnxruntime as ort
from torchaudio.compliance import kaldi

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as _P

ROOT = _P.SV_ONNX_DIR
MODELS = {
    "r293": os.path.join(ROOT, "voxceleb_resnet293_LM.onnx"),
    "r34": os.path.join(ROOT, "voxceleb_resnet34_LM.onnx"),
}


def load16(p):
    x, sr = sf.read(p, dtype="float32", always_2d=True)
    x = x.mean(1)
    if sr != 16000:
        g = gcd(int(sr), 16000)
        x = resample_poly(x, 16000 // g, sr // g).astype(np.float32)
    return x


class SV:
    def __init__(self, name="r293", threads=4):
        path = MODELS.get(name, name)
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        self.s = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        self.iname = self.s.get_inputs()[0].name
        self.oname = self.s.get_outputs()[0].name

    def embed(self, p):
        x = load16(p)
        w = torch.from_numpy(x).unsqueeze(0)
        f = kaldi.fbank(w, num_mel_bins=80, sample_frequency=16000,
                        dither=0.0, energy_floor=0.0)
        f = f - f.mean(0, keepdim=True)          # CMN，wespeaker 标准
        out = self.s.run([self.oname], {self.iname: f.unsqueeze(0).numpy()})[0]
        e = out[0].astype(np.float32)
        return e / (np.linalg.norm(e) + 1e-9)


def cos(a, b):
    return float(np.dot(a, b))
