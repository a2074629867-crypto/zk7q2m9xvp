import sys, time
sys.path.insert(0, "G:/_venvs/dmlsite")
import numpy as np
import onnxruntime as ort

M = "G:/_setup/models/EmphaClass_onnx/emphaclass_en.onnx"
rng = np.random.RandomState(0)
x = (rng.randn(1, 16000*5) * 0.05).astype(np.float32)

so = ort.SessionOptions(); so.log_severity_level = 3
so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

t0 = time.time(); sd = ort.InferenceSession(M, so, providers=["DmlExecutionProvider"])
print("DML load %.1fs" % (time.time()-t0), flush=True)
t0 = time.time(); yd = sd.run(None, {"input_values": x})[0]; td = time.time()-t0
print("DML 5s: %.2fs" % td, flush=True)
del sd

t0 = time.time(); sc = ort.InferenceSession(M, so, providers=["CPUExecutionProvider"])
print("CPU load %.1fs" % (time.time()-t0), flush=True)
t0 = time.time(); yc = sc.run(None, {"input_values": x})[0]; tc = time.time()-t0
print("CPU 5s: %.2fs" % tc, flush=True)

d = np.abs(yd-yc)
corr = np.corrcoef(yd.ravel(), yc.ravel())[0,1]
print("parity: maxabs=%.3e meandiff=%.3e corr=%.6f" % (d.max(), d.mean(), corr), flush=True)
print("speedup DML vs CPU = %.1fx" % (tc/td), flush=True)
