# -*- coding: utf-8 -*-
"""可复现性 / 采样噪声基准 —— 决定配对比较到底能不能用。

两个问题必须分开问：
  A. 同一 seed、同参数，跑两次，结果一样吗？      → 不一样则「标签效应」里混了采样噪声
  B. 不同 seed，同一 ref 同一条件，A/V/D 差多少？  → 这是「不可控噪声」的天然尺度，
     任何小于它的标签效应都不能当结论

用法：python repeat_test.py --n 3 --seeds 2051,2052,2053
"""
import argparse, json, os, subprocess, sys, hashlib, time, shutil
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "G:/voice_lib")
import gen_matrix as G          # 复用同一套 ref 映射与命令行构造

TMP = os.path.join(HERE, "tmp", "repeat")


def gen(outw, seed, pid="C_normal", cond="base"):
    """跑一条，落到 outw。与矩阵完全同参数。"""
    fn, _, _ = G.CAST[pid]
    ref = os.path.join(G.REFDIR, fn)
    rtxt = G.ref_text_of(pid)
    # ★ 每次调用用独立子目录：曾经用 dirname(outw) 当工作目录，
    #   结果第 2 次调用 rmtree 把第 1 次的产物一起删了。
    d = outw + "_d"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    o = os.path.join(d, "o.wav")
    cmd = [G.ACPP, "--task", "tts", "--family", "dots_tts", "--model", G.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rtxt,
           "--text", G.build_text(cond), "--out", o,
           "--seed", str(seed),
           "--request-option", "max_tokens=280",
           "--num-inference-steps", "8",
           "--request-option", "use_xvector=on",
           "--session-option", "dots_tts.mem_saver=true"]
    logp = os.path.join(d, "log.txt")
    try:
        with open(logp, "w", encoding="utf-8", errors="replace") as lf:
            subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=300)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/IM", "audiocpp_cli.exe"], capture_output=True)
        time.sleep(15)
        return False
    if os.path.exists(o) and G.dur(o) > 0.5:
        shutil.copy2(o, outw)
        return True
    return False


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--seeds", default="2052,2053,2054")
    ap.add_argument("--pid", default="C_normal")
    args = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)

    import ser as S
    dim = S.VoxDim()
    def sc(p):
        s = dim.score(p)
        return np.array([s["arousal"], s["valence"], s["dominance"]])

    # A. 同 seed 重复 3 次
    A = []
    for i in range(args.n):
        p = os.path.join(TMP, "A%d.wav" % i)
        t0 = time.time()
        ok = gen(p, 2051, args.pid, "base")
        print("A%d: %s %.0fs" % (i + 1, "ok" if ok else "FAIL", time.time() - t0), flush=True)
        if ok:
            A.append(p)
        time.sleep(8)

    print("\n--- A. 同 seed(2051) 同参数 ---")
    for p in A:
        print("  %s md5=%s A=%.4f V=%.4f D=%.4f" % (os.path.basename(p), md5(p)[:12], *sc(p)))
    if len(A) >= 2:
        arr = np.array([sc(p) for p in A])
        print("  组内 SD   : A=%.4f V=%.4f D=%.4f" % tuple(arr.std(0)))
        print("  组内极差  : A=%.4f V=%.4f D=%.4f" % tuple(arr.max(0) - arr.min(0)))
        print("  md5 唯一数: %d/%d  %s" % (len({md5(p) for p in A}), len(A),
              "完全可复现" if len({md5(p) for p in A}) == 1 else "存在非确定性"))

    # B. 不同 seed
    print("\n--- B. 不同 seed ---")
    B = []
    for sd in [int(x) for x in args.seeds.split(",")]:
        p = os.path.join(TMP, "B%d.wav" % sd)
        ok = gen(p, sd, args.pid, "base")
        print("  seed %d: %s" % (sd, "ok" if ok else "FAIL"), flush=True)
        if ok:
            B.append((sd, p))
        time.sleep(8)
    if len(B) >= 2:
        arr = np.array([sc(p) for _, p in B])
        for (sd, _), row in zip(B, arr):
            print("    seed %d  A=%.4f V=%.4f D=%.4f" % (sd, *row))
        print("  跨 seed SD : A=%.4f V=%.4f D=%.4f" % tuple(arr.std(0)))
        print("  跨 seed 极差: A=%.4f V=%.4f D=%.4f" % tuple(arr.max(0) - arr.min(0)))

    json.dump(dict(pid=args.pid,
                   same_seed=[dict(f=os.path.basename(p), md5=md5(p),
                                   A=float(sc(p)[0]), V=float(sc(p)[1]), D=float(sc(p)[2])) for p in A],
                   seeds=[dict(seed=sd, A=float(sc(p)[0]), V=float(sc(p)[1]), D=float(sc(p)[2]))
                          for sd, p in B]),
              open(os.path.join(HERE, "out", "repeat_test.json"), "w", encoding="utf-8"), indent=1)
    print("\n已写 out/repeat_test.json")


if __name__ == "__main__":
    main()
