# -*- coding: utf-8 -*-
"""emo_pilot.py —— 情绪未到位的句子，走 edit 引擎加 <emo> 标签的对照实验。

历史结论（都实测过，写在 DOTS_ANNOTATION_RULES.md / DOTS_MARKUP_RULES.md §9）：
- `<emo>` 是**唯一真正生效的表达标签**：edit 下 angry L2 把中位 F0 从 74 拉到 182Hz（+15.8 半音）
- 必须 `use_xvector=on`，否则声纹 0.95→0.38；开了也只回到 0.765（emo 有音色成本）
- `level` 是死参数（L1/L2/L3 = 181.3/182.3/180.8），永远写 2
- span 8–11 词最自然，<4 词插假声，>12 词音色下滑
- `emo` 与 `rate` 同块 ⇒ rate 兑现 0%
- 效果随 span 词数近似线性（6 词 +3.71 → 11 词 +6.07 半音）

本脚本只做**对照**：同一条源音频、同一 seed，跑两版
  ctl = edit 复刻（无标签）—— 用来剥离「复刻本身」的损伤
  emo = edit 复刻 + <emo type=X level=2>
两版都开 use_xvector=on，唯一变量就是标签。
"""
import json
import os
import re
import subprocess
import sys
import time

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
OUT_DIR = "G:/_setup/_emo_pilot"
LOG = "G:/_setup/_emo_pilot.jsonl"
WAV_A = "G:/_setup/_audio_ch123/out"
WAV_B = "G:/_setup/_regen_r2_out"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
VOICE = "G:/_setup/_emo_refs_all.json"
THREADS = 6
SEED = 42

# 情绪 → 引擎 type。平静**不映射**（calm/neutral 实测都是把声音抬起来，不是更平静）
TYPE = {"紧张": "afraid", "警惕": "disgusted", "委屈": "sad",
        "兴奋": "happy", "激动反抗": "angry"}

# (id, 该条的目标情绪)；情绪取自 _dlg_plan_v2.jsonl，这里只做核对
PILOT = ["c1_0163", "c2_0246", "c2_0302", "c2_0427", "c2_0309", "c3_0838"]

Q = "‘’“”'\""


def words(t):
    return re.findall(r"[A-Za-z']+", t)


def word_spans(t):
    """每个词的字符区间。标签只能落在词的边界上，切在词中就废了。"""
    return [(m.start(), m.end()) for m in re.finditer(r"[A-Za-z']+", t)]


def plain(text):
    """source_text / target_text 必须是**剥标签原文**。

    只去句首/句尾的引号 —— 内部的 ’ 是撇号（it’s / don’t / Here’s），
    一起删掉会变成 its / dont / Heres，模型念错、ASR 也对不上。
    """
    t = text.strip()
    while t and t[0] in "‘’“”\"'":
        t = t[1:]
    while t and t[-1] in "‘’“”\"'":
        t = t[:-1]
    t = t.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", t).strip()


def span_of(t):
    """挑要包的片段，返回**字符区间**。

    ≤12 词：整句包（官方 _phrase 主档 8–11 词）。
    >12 词：取一个 4–12 词的完整从句（不许切断从句）。
    下限 4 词是硬的：1 词会在词后插 0.1s 高频假声，2–3 词像局部音效，官方 0 例。
    """
    ws = word_spans(t)
    if not ws:
        return 0, len(t)
    if len(ws) <= 12:
        return ws[0][0], ws[-1][1]
    best = None
    for m in re.finditer(r"[^.?!,;]+", t):
        a, b = m.start(), m.end()
        inside = [w for w in ws if w[0] >= a and w[1] <= b]
        n = len(inside)
        if 4 <= n <= 12 and (best is None or n > best[2]):
            best = (inside[0][0], inside[-1][1], n)
    if best:
        return best[0], best[1]
    return ws[0][0], ws[10][1]     # 兜底：前 11 词


def tag_it(t, etype):
    a, b = span_of(t)
    return t[:a] + '<emo type="%s" level="2">' % etype + t[a:b] + "</emo>" + t[b:]


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def source_of(i):
    p = os.path.join(WAV_B, i + ".wav")
    return p if os.path.exists(p) else os.path.join(WAV_A, i + ".wav")


def gen(src, plain_text, instruction, out, mt):
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", str(THREADS),
           "--request-option", "template_name=edit",
           "--source-audio", src,
           "--request-option", "source_text=" + plain_text,
           "--request-option", "target_text=" + plain_text,
           "--request-option", "use_xvector=on",
           "--text", instruction, "--seed", str(SEED), "--out", out,
           "--request-option", "max_tokens=%d" % mt,
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ACPP_DIR, timeout=1200)
    txt = (r.stdout or "") + (r.stderr or "")
    dur = None
    for line in txt.splitlines():
        if "audio_duration_ms=" in line:
            try:
                dur = float(line.split("audio_duration_ms=")[1].split()[0]) / 1000.0
            except Exception:
                pass
    ok = os.path.exists(out) and os.path.getsize(out) > 20000
    return ok, dur, time.time() - t0, txt


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            plan[r["id"]] = r
    todo = []
    for i in PILOT:
        p = plan.get(i)
        if not p:
            print("计划里没有", i)
            continue
        et = TYPE.get(p["emo"])
        if not et:
            print("%s 情绪=%s 无对应 type（平静不打），跳过" % (i, p["emo"]))
            continue
        src = source_of(i)
        if not os.path.exists(src):
            print("%s 源音频缺失 %s" % (i, src))
            continue
        todo.append((i, p["emo"], et, src, plain(p["text"])))

    print("待跑 %d 条 × 2 版 = %d 次生成" % (len(todo), len(todo) * 2), flush=True)
    for k, (i, emo, et, src, pt) in enumerate(todo, 1):
        mt = mtok(len(words(pt)))
        for cond, ins in (("ctl", pt), ("emo", tag_it(pt, et))):
            out = os.path.join(OUT_DIR, "%s_%s.wav" % (i, cond))
            if os.path.exists(out) and os.path.getsize(out) > 20000:
                print("[%d/%d] %s %s 已有，跳过" % (k, len(todo), i, cond), flush=True)
                continue
            ok, dur, dt, txt = gen(src, pt, ins, out, mt)
            rec = {"id": i, "emo": emo, "type": et, "cond": cond,
                   "src": os.path.basename(src), "ins": ins, "ok": ok,
                   "dur": dur, "sec": round(dt, 1)}
            with open(LOG, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print("[%d/%d] %s %-3s %s %5ss %5.1fs  %s"
                  % (k, len(todo), i, cond, "OK " if ok else "FAIL",
                     ("%.2f" % dur) if dur else "-", dt, ins[:70]), flush=True)
            if not ok:
                open("G:/_setup/_emo_pilot_fail.txt", "a", encoding="utf-8").write(
                    i + " " + cond + "\n" + txt[-800:] + "\n\n")
    print("完成", flush=True)


if __name__ == "__main__":
    main()
