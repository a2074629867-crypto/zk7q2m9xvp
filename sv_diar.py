"""用 sherpa-onnx + pyannote segmentation + wespeaker resnet34 做说话人分离。

产物：G:/_setup/out_sv/diar.rttm.json  [{start,end,speaker}]
"""
import os, sys, json, time
import numpy as np
import sherpa_onnx as so
import soundfile as sf

SEG = "G:/_setup/models/sv_hub/seg/model.onnx"
EMB = "G:/_setup/models/sv_hub/voxceleb_resnet34_LM.onnx"
WAV = sys.argv[1] if len(sys.argv) > 1 else "G:/_setup/_movie16k.wav"
NCL = int(sys.argv[2]) if len(sys.argv) > 2 else 3
OUT = sys.argv[3] if len(sys.argv) > 3 else "G:/_setup/out_sv/diar.json"

cfg = so.OfflineSpeakerDiarizationConfig(
    segmentation=so.OfflineSpeakerSegmentationModelConfig(
        pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=SEG),
        num_threads=6,
    ),
    embedding=so.SpeakerEmbeddingExtractorConfig(model=EMB, num_threads=6),
    clustering=so.FastClusteringConfig(num_clusters=NCL, threshold=0.5),
    min_duration_on=0.25,
    min_duration_off=0.4,
)
sd = so.OfflineSpeakerDiarization(cfg)
print("model loaded, sr=%d" % sd.sample_rate, flush=True)

x, sr = sf.read(WAV, dtype="float32", always_2d=True)
x = x.mean(1)
print("audio %.1fs sr=%d" % (len(x) / sr, sr), flush=True)
if sr != sd.sample_rate:
    from scipy.signal import resample_poly
    from math import gcd
    g = gcd(int(sr), int(sd.sample_rate))
    x = resample_poly(x, sd.sample_rate // g, sr // g).astype(np.float32)
    print("resampled -> %d" % sd.sample_rate, flush=True)

t = time.time()
res = sd.process(x).sort_by_start_time()
print("diar done in %.1fs" % (time.time() - t), flush=True)

rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "speaker": int(s.speaker)}
        for s in res]
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

import collections
c = collections.Counter(r["speaker"] for r in rows)
tot = collections.defaultdict(float)
for r in rows:
    tot[r["speaker"]] += r["end"] - r["start"]
print("segments", len(rows))
for k in sorted(c):
    print("  spk%d: %d 段, %.1fs" % (k, c[k], tot[k]))
