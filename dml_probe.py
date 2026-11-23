"""探针：本机 RX580 能不能走 DirectML（D3D12）跑大矩阵 —— 判断「不用 CPU」这条路通不通。
只测两件事：① DmlExecutionProvider 能不能创建 ② 同样的 MatMul 链，DML vs CPU 的每秒 FLOPs。
"""
import time
import sys; sys.path.insert(0,"G:/_venvs/dmlsite")
import numpy as np
import onnx
import onnxruntime as ort
from onnx import helper, TensorProto

T, H = 1500, 1280      # 30s 音频 @50Hz 帧率 × XLS-R-1B hidden
BLOCKS = 12            # 12 个 MatMul 块（真实模型 48 层，这里只取比例）

def build(n_blocks):
    nodes, inits = [], []
    nodes.append(helper.make_node("MatMul", ["x", "W0"], ["h0"]))
    inits.append(helper.make_tensor("W0", TensorProto.FLOAT, [H, H],
                                    np.random.randn(H, H).astype(np.float32) * 0.02))
    prev = "h0"
    for i in range(1, n_blocks):
        w, out = f"W{i}", f"h{i}"
        inits.append(helper.make_tensor(w, TensorProto.FLOAT, [H, H],
                                        np.random.randn(H, H).astype(np.float32) * 0.02))
        nodes.append(helper.make_node("MatMul", [prev, w], [out]))
        prev = out
    g = helper.make_graph(nodes, "mm_chain",
                          [helper.make_tensor_value_info("x", TensorProto.FLOAT, [T, H])],
                          [helper.make_tensor_value_info(prev, TensorProto.FLOAT, [T, H])], inits)
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 17)])
    m.ir_version = 9
    return m

print("ORT", ort.__version__)
print("providers:", ort.get_available_providers())
model = build(BLOCKS)
flops = 2.0 * T * H * H * BLOCKS

for prov in ["DmlExecutionProvider", "CPUExecutionProvider"]:
    if prov not in ort.get_available_providers():
        print(f"[SKIP] {prov} 不在可用列表")
        continue
    try:
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess = ort.InferenceSession(model.SerializeToString(), so, providers=[prov])
        used = sess.get_providers()[0]
        x = np.random.randn(T, H).astype(np.float32)
        sess.run(None, {"x": x})            # warmup
        t0 = time.perf_counter()
        n = 3
        for _ in range(n):
            sess.run(None, {"x": x})
        dt = (time.perf_counter() - t0) / n
        print(f"[OK] {used}: {dt*1000:.0f} ms/forward, {flops/dt/1e9:.0f} GFLOP/s")
    except Exception as e:
        print(f"[FAIL] {prov}: {type(e).__name__}: {str(e)[:300]}")
