# -*- coding: utf-8 -*-
"""重生成 v2：按四方定档后的音色档，重跑被剔除的对白。

输入
----
_gate_dlg_v2.json 里 verdict==REGEN 的 77 条（`_regen_dlg.json` 已整理）
_castle_en_ch123_plan_v2.jsonl 给出每条该用的 voice 名

voice 名怎么解析成参考音频
--------------------------
`<Role>_<emo>_<n>` → `_emo_refs_all.json[Role][emo][n-1]`，条目里自带 `path` 和 `text`
（`text` 是那段参考录音的转写，audiocpp 的 --reference-text 必须和参考音频对得上）。
实证：`Joseph_normal_1` ↔ 库内 Joseph/normal 第 1 条 `Joseph_normal_c1016.wav`，
与 gate 输出里 `spk.ref` 完全一致。

为什么串行
----------
本机是 Vulkan 后端，单实例峰值提交内存 8.9GB（冒烟测试实测 rtf 18.2）。
并跑两路以上会互相抢显存/内存，反而更慢且更容易崩。所以一次一条，可断点续跑：
输出文件已存在且 >50KB 就跳过，中断后重跑同一条命令即可继续。
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
PLAN = "G:/_setup/_castle_en_ch123_plan_v2.jsonl"
REGEN = "G:/_setup/_regen_dlg.json"
OUT_DIR = "G:/_setup/_regen_out"
LOG = "G:/_setup/_regen_v2.jsonl"

WPM_AT_1 = 158.0
TOK_PER_SEC = 12.7
RATE = 0.80


def mtok(words, safety=1.08):
    dur = words / WPM_AT_1 * 60.0 / RATE
    return int(-(-dur * TOK_PER_SEC * safety // 10) * 10)


def resolve(voice):
    """'Thomas_calm_1' -> (path, ref_text)；解析不了返回 (None, None)。"""
    parts = voice.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None, None
    role_emo, n = parts[0], int(parts[1])
    lib = json.load(open(LIB, encoding="utf-8"))
    for role in lib:
        if not role_emo.startswith(role + "_"):
            continue
        emo = role_emo[len(role) + 1:]
        items = lib[role].get(emo) or []
        if 1 <= n <= len(items):
            it = items[n - 1]
            p = it["path"] if isinstance(it, dict) else it
            t = it.get("text") if isinstance(it, dict) else ""
            return p, t
    return None, None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(PLAN, encoding="utf-8")}
    todo = json.load(open(REGEN, encoding="utf-8"))
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if lim:
        todo = todo[:lim]
    print("待重生成 %d 条" % len(todo), flush=True)

    done = 0
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
            ref, rtext = resolve(p["voice"])
            if not ref or not os.path.exists(ref):
                print("[%d/%d] %s 参考解析失败 %s" % (k, len(todo), i, p["voice"]), flush=True)
                continue
            text = p.get("text_src") or p["text"]
            words = len(text.split())
            mt = max(120, mtok(words))
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
            log.write(json.dumps({"id": i, "voice": p["voice"], "ref": os.path.basename(ref),
                                  "ok": ok, "dur": dur, "sec": round(dt, 1),
                                  "size": os.path.getsize(out) if os.path.exists(out) else 0,
                                  "mt": mt}, ensure_ascii=False) + "\n")
            log.flush()
            if ok:
                done += 1
            print("[%d/%d] %s %-20s %s %5ss %.1fs" % (
                k, len(todo), i, p["voice"], "OK" if ok else "FAIL", dur, dt), flush=True)

    print("完成 %d/%d → %s" % (done, len(todo), OUT_DIR), flush=True)


if __name__ == "__main__":
    main()
