#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用任意 ref 生成，验证「换高 V ref 能否把效价带上去」。

与 gen_matrix.run_one 同样的调用参数，只是 ref / ref-text / 文本都可指定。
"""
import argparse, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_matrix as G

OUTDIR = os.path.join(HERE, "out", "refprobe")
os.makedirs(OUTDIR, exist_ok=True)
TMP = os.path.join(HERE, "tmp", "refprobe")
os.makedirs(TMP, exist_ok=True)


def dur(p):
    import soundfile as sf
    try:
        return sf.info(p).duration
    except Exception:
        return 0.0


def gen(ref, ref_text, text, seed, tag, xvec="on"):
    dst = os.path.join(OUTDIR, tag + ".wav")
    if os.path.exists(dst) and dur(dst) > 0.5:
        return dst, "skip"
    tmp = os.path.join(TMP, tag)
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    outw = os.path.join(tmp, "o.wav")
    cmd = [G.ACPP, "--task", "tts", "--family", "dots_tts", "--model", G.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", ref_text,
           "--text", text, "--out", outw,
           "--seed", str(seed),
           "--request-option", "max_tokens=280",
           "--num-inference-steps", "8",
           "--request-option", "use_xvector=" + xvec,
           "--session-option", "dots_tts.mem_saver=true"]
    logp = os.path.join(TMP, tag + ".txt")
    for attempt in (1, 2, 3):
        try:
            with open(logp, "w", encoding="utf-8", errors="replace") as lf:
                r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=200)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = -9
            subprocess.run(["taskkill", "/F", "/IM", "audiocpp_cli.exe"], capture_output=True)
            time.sleep(15)
        if os.path.exists(outw) and dur(outw) > 0.5:
            break
        print("  retry %s (attempt %d rc=%d)" % (tag, attempt, rc), flush=True)
    ok = os.path.exists(outw) and dur(outw) > 0.5
    if ok:
        shutil.copy2(outw, dst)
        shutil.rmtree(tmp, ignore_errors=True)
        print("  ok %-42s %.2fs" % (tag, dur(dst)), flush=True)
        return dst, "ok"
    print("  FAIL %s" % tag, flush=True)
    return None, "fail"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="json 文件：[{ref,ref_text,text,cond,seed}]")
    a = ap.parse_args()
    specs = json.load(open(a.spec, encoding="utf-8"))
    log = []
    for i, s in enumerate(specs):
        cond = s.get("cond")
        txt = s.get("text") or G.TEXT
        t = txt if cond in (None, "base") else '<emo type="%s" level="2">%s</emo>' % (cond, txt)
        tag = "%s__%s__s%d" % (s["name"], cond or "base", s["seed"])
        p, st = gen(s["ref"], s["ref_text"], t, s["seed"], tag, s.get("xvec", "on"))
        if st == "ok":
            log.append({"path": p, "name": s["name"], "cond": cond or "base",
                        "seed": s["seed"], "ref": s["ref"], "dur": round(dur(p), 2)})
        time.sleep(8)
    with open(os.path.join(OUTDIR, "_index.jsonl"), "a", encoding="utf-8") as f:
        for x in log:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("done %d/%d" % (len(log), len(specs)))


if __name__ == "__main__":
    main()
