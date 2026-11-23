import os, time, sys
sys.path.insert(0, "G:/_venvs/dmlsite")   # numpy 2.2.6 + onnx 兼容 + DirectML 版 ORT
import torch
from transformers import Wav2Vec2ForAudioFrameClassification, Wav2Vec2Config

torch.set_grad_enabled(False)
D = "G:/_setup/models/EmphaClass"
OUT = "G:/_setup/models/EmphaClass_onnx"
os.makedirs(OUT, exist_ok=True)
t0 = time.time()

print("[1] mmap load weights", flush=True)
sd = torch.load(os.path.join(D, "pytorch_model.bin"), map_location="cpu", mmap=True, weights_only=True)
print("    keys=%d %.1fs" % (len(sd), time.time()-t0), flush=True)

print("[2] meta build + assign", flush=True)
cfg = Wav2Vec2Config.from_pretrained(D)
with torch.device("meta"):
    model = Wav2Vec2ForAudioFrameClassification(cfg)
missing, unexpected = model.load_state_dict(sd, assign=True, strict=False)
del sd
model.eval()
print("    missing=%d unexpected=%d %.1fs" % (len(missing), len(unexpected), time.time()-t0), flush=True)

class Wrap(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m
    def forward(self, x):
        return self.m(x).logits

w = Wrap(model).eval()
x = torch.randn(1, 16000 * 10)
print("[3] tracing/export…", flush=True)
torch.onnx.export(
    w, (x,), os.path.join(OUT, "emphaclass_en.onnx"),
    input_names=["input_values"], output_names=["logits"],
    dynamic_axes={"input_values": {1: "time"}, "logits": {1: "frames"}},
    opset_version=17, do_constant_folding=True, dynamo=False,
)
p = os.path.join(OUT, "emphaclass_en.onnx")
print("[4] DONE proto=%.2f MB total_dir=%.2f GiB %.1fs" % (
    os.path.getsize(p)/2**20, sum(os.path.getsize(os.path.join(OUT,f)) for f in os.listdir(OUT))/2**30,
    time.time()-t0), flush=True)
