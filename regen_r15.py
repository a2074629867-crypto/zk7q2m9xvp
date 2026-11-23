# -*- coding: utf-8 -*-
"""regen_r15.py —— 本地 GPU 重生成（三路音色突变 18 条，多候选）

输入 `_spec_r15.json`（_build_spec_r15.py 生成）
输出 `_cand_r15/cand/<id>__<voice>__s<seed>.wav`（交给 _cloud_pick.py 同口径择优）
日志 `_regen_r15.jsonl`（可断点续跑：候选文件已存在且 >50KB 就跳过）

残片检测沿用 regen_r11（DECISIONS 2026-11-13 20:45）：
  生成时长 < 0.6 × 现役音频时长 ⇒ 判残片，删掉换下一个 seed。

用法：
  G:/Python310/python.exe regen_r15.py            # 全跑
  G:/Python310/python.exe regen_r15.py 6          # 只跑前 6 个候选（试跑）
"""
import json
import os
import subprocess
import sys
import time

import soundfile as sf

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = "G:/_setup/_emo_refs_all.json"
SPEC = os.environ.get("SPEC_R15", "G:/_setup/_spec_r15.json")
CAND = "G:/_setup/_cand_r15/cand"
LOG = "G:/_setup/_regen_r15.jsonl"
AUD = "G:/_setup/_audio_ch123/out"


def mtok(words):
    return max(120, min(900, int(words * 12 + 120)))


def resolve(lib, voice):
    """`Thomas_wary_2` -> (_emo_refs_all.json[Thomas][wary][1] 的 path, text)"""
    parts = voice.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None, None
    head, n = parts[0], int(parts[1])
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    if 1 <= n <= len(items):
        it = items[n - 1]
        if isinstance(it, dict):
            return it.get("path"), it.get("text") or ""
        return it, ""
    return None, None


def jobs(spec):
    """展开成 (id, voice, seed) 序列：原档 seeds + 备选档 alt_seeds"""
    out = []
    for it in spec["items"]:
        cur = it["cur"]
        for v in it["voices"]:
            seeds = it["seeds"] if v == cur else it.get("alt_seeds") or [42]
            for s in seeds:
                out.append((it["id"], v, s))
    return out


def main():
    os.makedirs(CAND, exist_ok=True)
    lib = json.load(open(LIB, encoding="utf-8"))
    spec = json.load(open(SPEC, encoding="utf-8"))
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open("G:/_setup/_dlg_plan_v2.jsonl", encoding="utf-8") if l.strip()}
    todo = jobs(spec)
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if lim:
        todo = todo[:lim]
    print("候选 %d 个（%d 条）" % (len(todo), len(set(j[0] for j in todo))), flush=True)

    done = skip = fail = 0
    t_start = time.time()
    with open(LOG, "a", encoding="utf-8", newline="\n") as log:
        for k, (i, voice, seed) in enumerate(todo, 1):
            p0 = plan.get(i)
            if not p0:
                print("[%d/%d] %s 计划里没有，跳过" % (k, len(todo), i), flush=True)
                continue
            out = os.path.join(CAND, "%s__%s__s%d.wav" % (i, voice, seed))
            if os.path.exists(out) and os.path.getsize(out) > 50000:
                skip += 1
                continue
            ref, rtext = resolve(lib, voice)
            if not ref or not os.path.exists(ref):
                print("[%d/%d] %s 参考解析失败 %s (%s)"
                      % (k, len(todo), i, voice, ref), flush=True)
                fail += 1
                continue
            text = p0.get("text_src") or p0["text"]
            mt = mtok(len(text.split()))
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", "6",
                   "--voice-ref", ref, "--reference-text", rtext or "",
                   "--text", text, "--seed", str(seed), "--out", out,
                   "--request-option", "max_tokens=%d" % mt,
                   "--session-option", "dots_tts.mem_saver=true", "--metrics"]
            base = os.path.join(AUD, i + ".wav")
            d_old = sf.info(base).duration if os.path.exists(base) else 0.0
            t0 = time.time()
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   cwd=ACPP_DIR, timeout=900)
                outtxt = (r.stdout or "") + (r.stderr or "")
                rc = r.returncode
            except subprocess.TimeoutExpired:
                print("[%d/%d] %s %s s%d 超时" % (k, len(todo), i, voice, seed), flush=True)
                fail += 1
                continue
            dt = time.time() - t0
            dur = None
            for line in outtxt.splitlines():
                if "audio_duration_ms=" in line:
                    try:
                        dur = float(line.split("=")[1]) / 1000.0
                    except Exception:
                        pass
            ok = os.path.exists(out) and os.path.getsize(out) > 50000
            if ok and d_old and dur and dur < 0.6 * d_old:
                ok = False
                print("[%d/%d] %s %s s%d 残片 %.2fs < 0.6×%.2fs，丢弃"
                      % (k, len(todo), i, voice, seed, dur, d_old), flush=True)
                try:
                    os.remove(out)
                except Exception:
                    pass
            log.write(json.dumps(dict(id=i, voice=voice, seed=seed, ok=ok, rc=rc,
                                      dur=dur, sec=round(dt, 1),
                                      size=os.path.getsize(out) if os.path.exists(out) else 0),
                                 ensure_ascii=False) + "\n")
            log.flush()
            if ok:
                done += 1
            else:
                fail += 1
                tail = outtxt.strip().splitlines()[-1:] or [""]
                print("  !! %s %s s%d rc=%s %s" % (i, voice, seed, rc, tail[0][:100]),
                      flush=True)
            el = time.time() - t_start
            eta = el / k * (len(todo) - k) / 60.0
            print("[%d/%d] %-9s %-20s s%-3d %s %5.2fs %.1fs  已用%.0fmin 剩≈%.0fmin"
                  % (k, len(todo), i, voice, seed, "OK" if ok else "FAIL",
                     dur or 0, dt, el / 60, eta), flush=True)

    print("\n生成 %d / 跳过 %d / 失败 %d / 共 %d  用时 %.1f min"
          % (done, skip, fail, len(todo), (time.time() - t_start) / 60), flush=True)


if __name__ == "__main__":
    main()
