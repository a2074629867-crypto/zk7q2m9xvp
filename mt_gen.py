# -*- coding: utf-8 -*-
"""mt_gen.py —— 多候选生成器（章优先 + 多种子 + 断点续跑 + 看门狗）。

与旧 mt_run.py 的区别：
1. **章优先**：ch1 的两个种子都跑完就能立刻拼装试听，不必等全库
2. **多种子**：同一条生成多个候选（不同 seed），后续 mt_score.py 择优
3. 每个候选落在 `_mt_raw_s<seed>/N####.wav`，互不覆盖
4. **完整性校验**不用文件大小，用「能否解析 + 时长在合理区间」，防止半截文件被当成功

用法：
    python mt_gen.py --ch ch1 --seeds 42,1234          # 只跑第一章两个种子
    python mt_gen.py --ch ch1,ch2,ch3 --seeds 42,1234
    python mt_gen.py --ch ch1 --seeds 42 --plan mt_plan2.json
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import wave

ROOT = "G:/_setup"
# ---- 生成后端（环境变量可覆盖，接云算力就靠这三个）----
# 本机 RX580 8G：只能 vulkan + threads=2（>2 必 OOM，重启无效）。
# 云端 24G 卡：backend=cuda、threads 可开到 8~16、MT 可放大，实测再定。
ACPP = os.environ.get("MT_ACPP") or \
    "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp/audiocpp_cli.exe"
MODEL = os.environ.get("MT_MODEL") or "E:/tts-models/acpp/DotTTS-Edit-GGUF"
BACKEND = os.environ.get("MT_BACKEND") or "vulkan"
THREADS = int(os.environ.get("MT_THREADS") or 2)
REF = "G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
REF_TXT = "called Sirius, is reaching Earth after traveling at 186,000 miles per second."
LOG = os.path.join(ROOT, "_mt_gen.log")
BATCH = 25
MT = int(os.environ.get("MT_MAXTOK") or 420)
TIMEOUT = 3600          # 单批上限 1 小时，卡死就杀掉重排
# 采样步数：edit 非蒸馏模型默认 10 步。实测 8 步与默认几乎一致
# （F0 79.5→79.6 / 重心 1855→1835 / 声纹 0.943），纯生成环节 76s→48s。
# ⚠️ 4 步会崩（F0 79.5→269.7），mf 检查点才能用 4 步。
STEPS = 8


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def valid(path, text):
    """能解析 + 时长合理 ⇒ 才算生成成功（防半截文件）。"""
    if not os.path.exists(path) or os.path.getsize(path) < 30000:
        return False
    try:
        w = wave.open(path)
        n, sr = w.getnframes(), w.getframerate()
        w.close()
    except Exception:
        return False
    if sr <= 0:
        return False
    dur = n / float(sr)
    words = max(1, len(text.split()))
    return 0.25 <= dur <= words * 1.4 + 4.0


def gen_batch(items, tag, outdir, seed):
    """items = [(id, text, rate)]；rate<1 时给正文加 `<rate, factor=x>` 前缀。"""
    tmp = os.path.join(ROOT, "_mt_tmp", tag)
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    txt = os.path.join(tmp, "in.txt")
    with open(txt, "w", encoding="utf-8") as f:
        for _, t, r in items:
            line = t.replace("\n", " ")
            if r and r < 0.999:
                line = "<rate, factor=%.3f>%s" % (r, line)
            f.write(line + "\n")
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", BACKEND, "--threads", str(THREADS),
           "--voice-ref", REF, "--reference-text", REF_TXT,
           "--batch-text-file", txt, "--out-dir", os.path.join(tmp, "out"),
           "--request-option", "max_tokens=%d" % MT, "--seed", str(seed),
           "--num-inference-steps", str(STEPS)]
    # mem_saver 是 8G 显存的救命开关（本机必开），大显存上关掉更快。
    # MT_MEMSAVER=0 关；默认开，保持本机行为不变。
    if os.environ.get("MT_MEMSAVER", "1") not in ("0", "off", "false"):
        cmd += ["--session-option", "dots_tts.mem_saver=true"]
    cmd += ["--metrics"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT)
        rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        rc, out = -9, "TIMEOUT %ds" % TIMEOUT
        log("  !! 批次超时，已杀掉：%s" % tag)
    ok = 0
    for k, item in enumerate(items, start=1):
        uid, text = item[0], item[1]
        src = os.path.join(tmp, "out", "line_%d.wav" % k)
        dst = os.path.join(outdir, "%s.wav" % uid)
        if valid(src, text):
            shutil.copy2(src, dst)
            ok += 1
    if ok < len(items):
        log("  批次 %s 成功 %d/%d（rc=%d）" % (tag, ok, len(items), rc))
        for t in out.strip().splitlines()[-3:]:
            log("    " + t[:160])
    shutil.rmtree(tmp, ignore_errors=True)
    return ok


def main():
    global STEPS
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--seeds", default="42")
    ap.add_argument("--plan", default="mt_plan2.json")
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--steps", type=int, default=STEPS,
                    help="--num-inference-steps，edit 模型默认 10；8 近无损，4 会崩")
    ap.add_argument("--ids", default=None, help="只跑指定 id（逗号分隔），用于补生成")
    ap.add_argument("--outdir", default=None, help="候选目录（默认 _mt_raw_s<seed>）")
    ap.add_argument("--rate-file", default=None,
                    help="逐条语速因子 json（默认 _mt_rate_<ch>.json，有就用）")
    a = ap.parse_args()

    STEPS = a.steps
    log("采样步数 = %d" % STEPS)

    chs = [c.strip() for c in a.ch.split(",") if c.strip()]
    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]
    only = set(x.strip() for x in a.ids.split(",") if x.strip()) if a.ids else None
    plan = json.load(open(os.path.join(ROOT, a.plan), encoding="utf-8"))
    t_all = time.time()

    for ch in chs:
        units = [p for p in plan if p["ch"] == ch and (only is None or p["id"] in only)]
        if not units:
            log("!! %s 无单元" % ch)
            continue
        rf = a.rate_file or os.path.join(ROOT, "_mt_rate_%s.json" % ch)
        rate = {}
        if os.path.exists(rf):
            rate = json.load(open(rf, encoding="utf-8"))
            log("== %s 载入语速因子 %s：%d 条，其中打标记 %d 条"
                % (ch, os.path.basename(rf), len(rate),
                   sum(1 for v in rate.values() if v < 0.999)))
        for seed in seeds:
            outdir = os.path.join(ROOT, a.outdir or ("_mt_raw_s%d" % seed))
            os.makedirs(outdir, exist_ok=True)
            todo = [p for p in units
                    if not valid(os.path.join(outdir, p["id"] + ".wav"), p["text"])]
            log("=== %s / seed %d：%d 条，缺 %d 条" % (ch, seed, len(units), len(todo)))
            if not todo:
                continue
            t0 = time.time()
            done = 0
            for attempt in range(3):          # 批次失败/超时会留下空洞，最多补 3 轮
                if attempt:
                    todo = [p for p in units
                            if not valid(os.path.join(outdir, p["id"] + ".wav"), p["text"])]
                    if not todo:
                        break
                    log("  %s / seed %d 第 %d 轮补生成：%d 条"
                        % (ch, seed, attempt + 1, len(todo)))
                for i in range(0, len(todo), a.batch):
                    chunk = [(p["id"], p["text"], rate.get(p["id"], 1.0))
                             for p in todo[i:i + a.batch]]
                    tag = "s%d_%s_%s" % (seed, chunk[0][0], chunk[-1][0])
                    done += gen_batch(chunk, tag, outdir, seed)
                    el = time.time() - t0
                    left = len(units) - len([p for p in units
                                             if valid(os.path.join(outdir, p["id"] + ".wav"),
                                                      p["text"])])
                    eta = el / max(done, 1) * left / 3600
                    log("  %s 已完成 %d  待补 %d  %.1f 小时  预计还需 %.2f 小时"
                        % (ch, len(units) - left, left, el / 3600, eta))
            left = [p["id"] for p in units
                    if not valid(os.path.join(outdir, p["id"] + ".wav"), p["text"])]
            log("=== %s / seed %d 结束：成功 %d/%d，缺 %d 条，用时 %.2f 小时"
                % (ch, seed, len(units) - len(left), len(units), len(left),
                   (time.time() - t0) / 3600))
            if left:
                log("  仍缺：%s" % ",".join(left[:30]))
    log("全部完成，总用时 %.2f 小时" % ((time.time() - t_all) / 3600))


if __name__ == "__main__":
    main()
