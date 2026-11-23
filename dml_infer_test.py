import os, sys, time
sys.path.insert(0, "G:/_venvs/dmlsite")
import numpy as np
import onnxruntime as ort

M = "G:/_setup/models/EmphaClass_onnx/emphaclass_en.onnx"
print("ORT", ort.__version__, ort.__file__)
print("providers", ort.get_available_providers())

so = ort.SessionOptions()
so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
so.log_severity_level = 3
t0 = time.time()
sess = ort.InferenceSession(M, so, providers=["DmlExecutionProvider"])
print("session loaded %.1fs, ep=%s" % (time.time()-t0, sess.get_providers()[0]), flush=True)
print("inputs", [(i.name, i.shape, i.type) for i in sess.get_inputs()])
print("outputs", [(o.name, o.shape, o.type) for o in sess.get_outputs()])

for sec in (5, 30):
    x = (np.random.randn(1, 16000*sec) * 0.05).astype(np.float32)
    t0 = time.time()
    out = sess.run(None, {"input_values": x})[0]
    dt = time.time() - t0
    p = 1/(1+np.exp(-out))
    print("[%ds audio] frames=%d  %.2fs  RTF=%.3f  emph_frame_ratio=%.3f" % (
        sec, out.shape[1], dt, dt/sec, float((p > 0.5).mean())), flush=True)
