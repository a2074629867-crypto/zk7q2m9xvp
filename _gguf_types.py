# -*- coding: utf-8 -*-
"""解析 GGUF 头部，统计每个模块前缀的张量精度分布。

GGUF 布局：magic(4) version(u32) n_tensors(u64) n_kv(u64) kvs... tensor_infos...
tensor_info: name(str) n_dims(u32) dims(u64*n) type(u32) offset(u64)
"""
import struct, sys, collections

GGML = {0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1",
        8: "Q8_0", 9: "Q8_1", 10: "Q2_K", 11: "Q3_K", 12: "Q4_K", 13: "Q5_K",
        14: "Q6_K", 15: "Q8_K", 16: "IQ2_XXS", 17: "IQ2_XS", 18: "IQ3_XXS",
        19: "IQ1_S", 20: "IQ4_NL", 21: "IQ3_S", 22: "IQ2_S", 23: "IQ4_XS",
        24: "I8", 25: "I16", 26: "I32", 27: "I64", 28: "F64", 29: "IQ1_M",
        30: "BF16"}

def rd(f, fmt):
    return struct.unpack("<" + fmt, f.read(struct.calcsize("<" + fmt)))[0]

def rd_str(f):
    n = rd(f, "Q")
    return f.read(n).decode("utf-8", "replace")

def read_kv(f):
    key = rd_str(f)
    t = rd(f, "I")
    # 值类型：0..7 标量, 8 str, 9 array
    if t == 8:
        val = rd_str(f)
    elif t == 9:
        et = rd(f, "I"); n = rd(f, "Q")
        for _ in range(n):
            _skip_val(f, et)
        val = "<array %d>" % n
    else:
        _skip_val(f, t)
        val = None
    return key, val

def _skip_val(f, t):
    sz = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
    if t == 8:
        rd_str(f)
    elif t == 9:
        et = rd(f, "I"); n = rd(f, "Q")
        for _ in range(n):
            _skip_val(f, et)
    elif t in sz:
        f.read(sz[t])
    else:
        raise ValueError("unknown kv type %d" % t)

def parse(path):
    with open(path, "rb") as f:
        magic = f.read(4)
        assert magic == b"GGUF", magic
        ver = rd(f, "I")
        nt = rd(f, "Q")
        nkv = rd(f, "Q")
        arch = None
        for _ in range(nkv):
            k, v = read_kv(f)
            if k in ("general.architecture", "general.name") and v:
                arch = v if arch is None else arch
        rows = []
        for _ in range(nt):
            name = rd_str(f)
            nd = rd(f, "I")
            dims = [rd(f, "Q") for _ in range(nd)]
            t = rd(f, "I")
            off = rd(f, "Q")
            rows.append((name, dims, t, off))
    return ver, arch, rows

for path in sys.argv[1:]:
    ver, arch, rows = parse(path)
    print("=" * 78)
    print("%s\n  version %d  arch %s  tensors %d" % (path.split("/")[-1], ver, arch, len(rows)))
    # 按前缀（去掉最后一段）分组
    g = collections.defaultdict(lambda: collections.Counter())
    bytes_by_type = collections.Counter()
    for name, dims, t, off in rows:
        parts = name.split(".")
        pre = ".".join(parts[:2]) if len(parts) > 2 else parts[0]
        g[pre][GGML.get(t, str(t))] += 1
    for pre in sorted(g):
        c = g[pre]
        print("  %-34s %s" % (pre, dict(c)))
    tot = collections.Counter()
    for name, dims, t, off in rows:
        tot[GGML.get(t, str(t))] += 1
    print("  --- 合计 ---")
    for k, v in tot.most_common():
        print("    %-8s %4d 个张量" % (k, v))
