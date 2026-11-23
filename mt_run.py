# -*- coding: utf-8 -*-
"""mt_run.py —— 用 baseA 参考批量生成前三章旁白（可断点续跑）。

要点：
- acpp 批量模式一次加载模型跑多条（--batch-text-file + --out-dir），
  每条固定开销约 10s，所以按 25 条一批，崩溃只丢一批
- 已存在的 N####.wav 跳过 ⇒ 随时可以重启
- 只跑旁白，对白已在 mt_plan2.py 里剔除
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = "G:/_setup"
ACPP = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
RAW = os.path.join(ROOT, "_mt_raw")
LOG = os.path.join(ROOT, "_mt_run.log")
BATCH = 25
SEED = 42
MT = 420          # 26 词 ≈ 10s ≈ 232 patch，420 留足余量


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def gen_batch(items, tag):
    """items = [(id, text)]，返回成功条数"""
    tmp = os.path.join(ROOT, "_mt_tmp", tag)
    if os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    txt = os.path.join(tmp, "in.txt")
    with open(txt, "w", encoding="utf-8") as f:
        for _, t in items:
            f.write(t.replace("\n", " ") + "\n")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--batch-text-file", txt, "--out-dir", os.path.join(tmp, "out"),
           "--request-option", "max_tokens=%d" % MT, "--seed", str(SEED),
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    ok = 0
    for k, (uid, _) in enumerate(items, start=1):
        src = os.path.join(tmp, "out", "line_%d.wav" % k)
        dst = os.path.join(RAW, "%s.wav" % uid)
        if os.path.exists(src) and os.path.getsize(src) > 40000:
            shutil.copy2(src, dst)
            ok += 1
    if ok < len(items):
        log("  批次 %s 只成功 %d/%d（rc=%d）" % (tag, ok, len(items), r.returncode))
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        for t in tail:
            log("    " + t[:160])
    return ok


def main():
    os.makedirs(RAW, exist_ok=True)
    plan = json.load(open(os.path.join(ROOT, "mt_plan2.json"), encoding="utf-8"))
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only:
        plan = [p for p in plan if p["ch"] == only]
    todo = [p for p in plan
            if not (os.path.exists(os.path.join(RAW, p["id"] + ".wav"))
                    and os.path.getsize(os.path.join(RAW, p["id"] + ".wav")) > 40000)]
    log("计划 %d 条，待生成 %d 条" % (len(plan), len(todo)))
    t0 = time.time()
    done = 0
    for i in range(0, len(todo), BATCH):
        chunk = [(p["id"], p["text"]) for p in todo[i:i + BATCH]]
        tag = "%s_%s" % (chunk[0][0], chunk[-1][0])
        n = gen_batch(chunk, tag)
        done += n
        el = time.time() - t0
        eta = el / max(done, 1) * (len(todo) - done) / 3600
        log("进度 %d/%d  本批 %d  已用 %.0f 分钟  预计还需 %.1f 小时"
            % (done, len(todo), n, el / 60, eta))
    log("完成：%d 条，用时 %.1f 小时" % (done, (time.time() - t0) / 3600))


if __name__ == "__main__":
    main()
