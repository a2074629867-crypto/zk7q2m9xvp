# -*- coding: utf-8 -*-
"""情绪标签有效性矩阵：8 个角色音色档 × 情绪条件，同文本同 seed 严格对照。

设计（对应用户要求）：
  - 两个主角各 4 档真人原声切片（cast.json 的 C/E emotions），"不同情绪用不同 REF"
  - 但生产主音色是 C_normal / E_calm ⇒ 同一套情绪标签也要在**主音色**上测一遍
    （这是「还是主音色为主」的对照）
  - 条件：base(无标签) + 5 个 emo 标签，同一 ref 下只差标签 ⇒ 归因干净

产物：out/gen/<pid>__<cond>__s<seed>.wav + index.jsonl
"""
import argparse, json, os, shutil, subprocess, sys, time, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ACPP = ("C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/"
        "reader/_tts_lab/acpp/audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REFDIR = "G:/_setup/cloud/ref"
OUT = os.path.join(HERE, "out", "gen")
TMP = os.path.join(HERE, "tmp")
LOG = os.path.join(HERE, "log", "gen.log")

TEXT = "I don't think anyone else knows about that door."

# 角色音色档 → (ref 文件, ref 转写, 人类语义)
CAST = {
    "C_normal":  ("1_charles_normal.wav",  "normal",  "平常"),
    "C_soft":    ("2_charles_soft.wav",    "soft",    "轻声示弱"),
    "C_excited": ("3_charles_excited_v2.wav", "excited", "激动叫喊"),
    "C_angry":   ("4_charles_angry_v2.wav", "angry",   "发怒"),
    "E_calm":    ("6_hooper_calm.wav",     "calm",    "冷静压迫"),
    "E_loud":    ("5_hooper_loud.wav",     "loud",    "大声炫耀"),
    "E_scold":   ("6b_hooper_scold.wav",   "scold",   "斥骂"),
    "E_begging": ("7_hooper_begging.wav",  "begging", "求饶示弱"),
}

CONDS = {
    "base":      None,
    "happy":     "happy",
    "sad":       "sad",
    "angry":     "angry",
    "afraid":    "afraid",
    "calm":      "calm",
}


def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def dur(p):
    try:
        w = wave.open(p)
        return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def ref_text_of(pid):
    """从 cast.json 取与该 ref 音频严格对应的转写。"""
    d = json.load(open(os.path.join(REFDIR, "cast.json"), encoding="utf-8"))
    fn, key, _ = CAST[pid]
    for ck in ("C", "E"):
        c = d.get(ck) or {}
        if c.get("ref", "").endswith(fn):
            return c["ref_text"]
        for e, v in (c.get("emotions") or {}).items():
            if v.get("ref", "").endswith(fn):
                return v["ref_text"]
    raise KeyError("no ref_text for " + fn)


def build_text(cond):
    t = CONDS[cond]
    if t is None:
        return TEXT
    return '<emo type="%s" level="2">%s</emo>' % (t, TEXT)


def run_one(pid, cond, seed, xvec="on"):
    os.makedirs(OUT, exist_ok=True)
    tag = "%s__%s__s%d" % (pid, cond, seed)
    dst = os.path.join(OUT, tag + ".wav")
    if os.path.exists(dst) and dur(dst) > 0.5:
        return dst, "skip"
    fn, _, _ = CAST[pid]
    ref = os.path.join(REFDIR, fn)
    rtxt = ref_text_of(pid)
    ins = build_text(cond)
    tmp = os.path.join(TMP, tag)
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    outw = os.path.join(tmp, "o.wav")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rtxt,
           "--text", ins, "--out", outw,
           "--seed", str(seed),
           "--request-option", "max_tokens=280",
           "--num-inference-steps", "8",
           "--request-option", "use_xvector=" + xvec,
           "--session-option", "dots_tts.mem_saver=true"]
    t0 = time.time()
    # ★ 不能 capture_output：audiocpp 在 Windows 上会留一个持有 stdout 句柄的
    #   孙进程（Vulkan 驱动），父进程退出后 read() 等不到 EOF ⇒ python 永久挂住。
    #   改成重定向到文件，句柄由 OS 管理，进程一死就返回。
    logp = os.path.join(TMP, tag + ".txt")
    rc, out = -9, "TIMEOUT"
    for attempt in (1, 2, 3):
        try:
            with open(logp, "w", encoding="utf-8", errors="replace") as lf:
                r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                   timeout=200)
            rc = r.returncode
            out = open(logp, encoding="utf-8", errors="replace").read()
        except subprocess.TimeoutExpired:
            rc, out = -9, "TIMEOUT"
            subprocess.run(["taskkill", "/F", "/IM", "audiocpp_cli.exe"],
                           capture_output=True)
            time.sleep(15)
        if os.path.exists(outw) and dur(outw) > 0.5:
            break
        # Vulkan 初始化期死锁是概率性的：重启进程常常能过，值得再试一次
        log("  retry %s (attempt %d rc=%d)" % (tag, attempt, rc))
    el = time.time() - t0
    ok = os.path.exists(outw) and dur(outw) > 0.5
    if ok:
        shutil.copy2(outw, dst)
        shutil.rmtree(tmp, ignore_errors=True)
        log("  ok %-30s %.2fs  %3.0fs" % (tag, dur(dst), el))
        return dst, "ok"
    log("  FAIL %-28s rc=%d %.0fs" % (tag, rc, el))
    for ln in out.strip().splitlines()[-4:]:
        log("      " + ln[:160])
    shutil.rmtree(tmp, ignore_errors=True)
    return None, "fail"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pids", default=",".join(CAST))
    ap.add_argument("--conds", default=",".join(CONDS))
    ap.add_argument("--seeds", default="2051")
    ap.add_argument("--xvec", default="on")
    args = ap.parse_args()

    pids = [p for p in args.pids.split(",") if p]
    conds = [c for c in args.conds.split(",") if c]
    seeds = [int(s) for s in args.seeds.split(",") if s]

    idx = os.path.join(HERE, "out", "gen_index.jsonl")
    done = set()
    if os.path.exists(idx):
        for ln in open(idx, encoding="utf-8"):
            try:
                d = json.loads(ln)
                done.add((d["pid"], d["cond"], d["seed"]))
            except Exception:
                pass
    log("=== 矩阵开始：%d 组合，已存在 %d ===" % (len(pids) * len(conds) * len(seeds), len(done)))
    t0 = time.time()
    n_ok = n_fail = n_try = 0
    with open(idx, "a", encoding="utf-8") as fh:
        for pid in pids:
            for cond in conds:
                for sd in seeds:
                    if (pid, cond, sd) in done:
                        continue
                    p, st = run_one(pid, cond, sd, args.xvec)
                    time.sleep(8)   # Vulkan 显存回收：驱动在进程退出后要几秒才还显存，不留间隔下一轮必 OOM
                    n_try += 1
                    # ★ 02:16 那次整机重启的教训：AMD 驱动会累计泄漏显存，
                    #   单项间隔不够用。每 12 条强制歇 60s 让驱动彻底归还。
                    if n_try % 12 == 0:
                        log("  -- 显存冷却 60s（已跑 %d 条）--" % n_try)
                        time.sleep(60)
                    if st == "ok":
                        n_ok += 1
                        fh.write(json.dumps(dict(pid=pid, cond=cond, seed=sd,
                                                 path=p, ref=CAST[pid][0],
                                                 text=TEXT, dur=round(dur(p), 2)),
                                            ensure_ascii=False) + "\n")
                        fh.flush()
                    elif st == "fail":
                        n_fail += 1
    log("=== 完成 ok=%d fail=%d 用时 %.0f min ===" % (n_ok, n_fail, (time.time() - t0) / 60))


if __name__ == "__main__":
    main()
