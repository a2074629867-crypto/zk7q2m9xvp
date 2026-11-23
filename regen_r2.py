# -*- coding: utf-8 -*-
"""regen_r2.py —— 对白第二轮重生成（按 voice 口径判出的 ref_fallback 里可修的那批）。

与 regen_v2.py 的区别：voice 由 `_regen_r2.json` 直接给（库里确认存在的档），
不再走「按 emo 就近映射」那套 —— 那套会给出库里根本没有的档（Thomas 没有 wary），
生成出来照样 ref_fallback。

输入 `_regen_r2.json`：[{id, role, emo, voice}]
输出 `_regen_r2_out/<id>.wav`，日志 `_regen_r2.jsonl`（可断点续跑）。
"""
import json
import os
import subprocess
import sys
import time

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = "G:/_setup/_emo_refs_all.json"
PLAN = "G:/_setup/_castle_en_ch123_plan.jsonl"
REGEN = "G:/_setup/_regen_r2.json"
OUT_DIR = "G:/_setup/_regen_r2_out"
LOG = "G:/_setup/_regen_r2.jsonl"


def mtok(words):
    # 与 regen_v2 一致：词数 → max_tokens
    return max(120, min(900, int(words * 12 + 120)))


def resolve(lib, voice):
    """`Thomas_loud_1` -> (_emo_refs_all.json[Thomas][loud][0] 的 path, text)"""
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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    lib = json.load(open(LIB, encoding="utf-8"))
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(PLAN, encoding="utf-8") if l.strip()}
    todo = json.load(open(REGEN, encoding="utf-8"))
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if lim:
        todo = todo[:lim]
    print("待重生成 %d 条" % len(todo), flush=True)

    done = 0
    fail = 0
    with open(LOG, "a", encoding="utf-8", newline="\n") as log:
        for k, it in enumerate(todo, 1):
            i = it["id"]
            p = plan.get(i)
            if not p:
                print("[%d/%d] %s 计划里没有，跳过" % (k, len(todo), i), flush=True)
                continue
            out = os.path.join(OUT_DIR, i + ".wav")
            if os.path.exists(out) and os.path.getsize(out) > 50000:
                print("[%d/%d] %s 已有，跳过" % (k, len(todo), i), flush=True)
                done += 1
                continue
            ref, rtext = resolve(lib, it["voice"])
            if not ref or not os.path.exists(ref):
                print("[%d/%d] %s 参考解析失败 %s (%s)"
                      % (k, len(todo), i, it["voice"], ref), flush=True)
                fail += 1
                continue
            text = p.get("text_src") or p["text"]
            mt = mtok(len(text.split()))
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", "6",
                   "--voice-ref", ref, "--reference-text", rtext or "",
                   "--text", text, "--seed", "42", "--out", out,
                   "--request-option", "max_tokens=%d" % mt,
                   "--session-option", "dots_tts.mem_saver=true", "--metrics"]
            t0 = time.time()
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   cwd=ACPP_DIR, timeout=900)
                outtxt = (r.stdout or "") + (r.stderr or "")
            except subprocess.TimeoutExpired:
                print("[%d/%d] %s 超时" % (k, len(todo), i), flush=True)
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
            log.write(json.dumps({"id": i, "voice": it["voice"], "emo": it["emo"],
                                  "ref": os.path.basename(ref), "ok": ok, "dur": dur,
                                  "sec": round(dt, 1),
                                  "size": os.path.getsize(out) if os.path.exists(out) else 0,
                                  "mt": mt}, ensure_ascii=False) + "\n")
            log.flush()
            if ok:
                done += 1
            else:
                fail += 1
            print("[%d/%d] %s %-20s %s %5ss %.1fs"
                  % (k, len(todo), i, it["voice"], "OK" if ok else "FAIL", dur, dt), flush=True)

    print("\n完成 %d / 失败 %d / 共 %d" % (done, fail, len(todo)), flush=True)


if __name__ == "__main__":
    main()
