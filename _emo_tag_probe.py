# -*- coding: utf-8 -*-
"""_emo_tag_probe.py —— 受控实验：tts 任务下 emo inline 标签到底生不生效

背景（2026-10-18 实测，DOTS_MARKUP_RULES.md 第九节）：
  - emo 标签极强（angry 让 F0 +15.6 半音），但那次是 **edit 任务**
  - level 1/2/3 实测完全一样（181.3/182.3/180.8）⇒ 死参数
  - 默认 emo 毁音色（声纹 0.38），必须 use_xvector=on 才救回 0.765
  - 我们生产链走 **tts 任务**，且协议里既没有 emo 标签也没有 use_xvector

本实验补这个空白。同一文本 / 同一参考 / 同一 seed，只改标签：

  A_base        纯文本（基线）
  B_angry2      <emo type="angry" level="2">全句</emo>
  C_angry3      <emo type="angry" level="3">全句</emo>      ← 测 level 是否死参数
  D_multi       句内两半不同情绪（前 afraid / 后 angry）    ← 测句内切分是否可行
  E_angry2_xv   同 B + use_xvector=on                      ← 测音色代价

用法：G:/Python310/python.exe _emo_tag_probe.py
"""
import json
import os
import subprocess
import time

import numpy as np
import soundfile as sf

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = "G:/_setup/_emo_refs_all.json"
OUT = "G:/_setup/_emo_probe"
SID = "c1_0049"
VOICE = "Joseph_nervous_1"
SEED = 42

# 原句（保留原始引号与标点，不拆句 —— 标签包在文本内部，仍是一次生成）
TEXT = ("But then, said, \u2018No. No, you had really much better be playing cricket "
        "in the sun, Edmund, something of that sort. You have been shown everything "
        "there is in the Red Room.\u2019")

# 句内两半：按语法成分切（官方 _multi 要求 span 落在从句/短语边界）
HEAD = "But then, said,"
MID = ("\u2018No. No, you had really much better be playing cricket in the sun, "
       "Edmund, something of that sort.")
TAIL = "You have been shown everything there is in the Red Room.\u2019"


def variant_texts():
    return [
        ("A_base", TEXT, None),
        ("B_angry2", '<emo type="angry" level="2">%s</emo>' % TEXT, None),
        ("C_angry3", '<emo type="angry" level="3">%s</emo>' % TEXT, None),
        ("D_multi",
         '<emo type="afraid" level="2">%s</emo> %s <emo type="angry" level="2">%s</emo>'
         % (HEAD, MID, TAIL), None),
        ("E_angry2_xv", '<emo type="angry" level="2">%s</emo>' % TEXT, "use_xvector=on"),
    ]


def resolve(lib, voice):
    head, n = voice.rsplit("_", 1)
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    it = items[int(n) - 1]
    if isinstance(it, dict):
        return it.get("path"), it.get("text") or ""
    return it, ""


def feats(p):
    """整条谱指纹（与 _dlg_fp.py 同口径）"""
    import sys
    sys.path.insert(0, "G:/_setup")
    import mt_seg_drift as D
    a, sr = D.read_wav(p)
    S = D.series(a, sr)
    f0 = S["f_p"]; f0 = f0[f0 > 0]
    cen = S["cen"]; cen = cen[cen > 0]
    hh = S["h_h"]; hh = hh[hh > -100]
    return dict(dur=len(a) / sr,
                f0=float(np.median(f0)) if len(f0) else 0.0,
                cen=float(np.median(cen)) if len(cen) else 0.0,
                hnr=float(np.median(hh)) if len(hh) else 0.0,
                n_f0=len(f0))


def emb(p, model="r34"):
    """r34 声纹（复用 _utt_verify.utt_emb，与 _utt_emb/r34.npz 同口径）"""
    import sys
    sys.path.insert(0, "G:/_setup")
    try:
        from _mut_all import M
        import _utt_verify as U
        if not hasattr(emb, "_m"):
            emb._m = M(model)
        return U.utt_emb(emb._m, p)
    except Exception as e:
        print("    声纹失败 %s: %s" % (os.path.basename(p), e), flush=True)
        return None


def cos(a, b):
    if a is None or b is None:
        return None
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def main():
    os.makedirs(OUT, exist_ok=True)
    lib = json.load(open(LIB, encoding="utf-8"))
    ref, rtext = resolve(lib, VOICE)
    print("参考 %s -> %s" % (VOICE, ref), flush=True)
    print("文本 %d 词" % len(TEXT.split()), flush=True)

    rows = []
    for tag, text, xv in variant_texts():
        p = os.path.join(OUT, "%s.wav" % tag)
        if os.path.exists(p) and os.path.getsize(p) > 50000:
            print("[skip] %s 已存在" % tag, flush=True)
        else:
            mt = max(200, int(len(text.split()) * 26) + 200)
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", "6",
                   "--voice-ref", ref, "--reference-text", rtext or "",
                   "--text", text, "--seed", str(SEED), "--out", p,
                   "--request-option", "max_tokens=%d" % mt,
                   "--session-option", "dots_tts.mem_saver=true", "--metrics"]
            if xv:
                cmd[cmd.index("--out"):cmd.index("--out")] = ["--request-option", xv]
            t0 = time.time()
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               cwd=ACPP_DIR, timeout=900)
            dt = time.time() - t0
            ok = os.path.exists(p) and os.path.getsize(p) > 40000
            print("[%s] %s %.1fs %s" % (tag, "OK" if ok else "FAIL", dt,
                                        "" if ok else (r.stdout + r.stderr)[-200:]), flush=True)
        if os.path.exists(p) and os.path.getsize(p) > 40000:
            f = feats(p)
            f["tag"] = tag
            f["emb"] = emb(p)
            rows.append(f)
        time.sleep(2)

    print()
    print("%-13s %7s %8s %8s %7s %7s %s" %
          ("变体", "dur", "F0中位", "cen", "HNR", "ΔF0", "声纹vs基线"))
    base = next((r for r in rows if r["tag"] == "A_base"), None)
    out = []
    for r in rows:
        d = ""
        c = ""
        if base:
            if base["f0"] > 0 and r["f0"] > 0:
                d = "%+.1f" % (12 * np.log2(r["f0"] / base["f0"]))
            c = cos(r["emb"], base["emb"])
            c = "%.3f" % c if c is not None else "-"
        print("%-13s %7.2f %8.1f %8.0f %7.1f %7s %s" %
              (r["tag"], r["dur"], r["f0"], r["cen"], r["hnr"], d, c), flush=True)
        out.append(dict(tag=r["tag"], dur=round(r["dur"], 2), f0=round(r["f0"], 1),
                        cen=round(r["cen"]), hnr=round(r["hnr"], 1),
                        d_f0_st=(round(12 * np.log2(r["f0"] / base["f0"]), 2)
                                 if base and base["f0"] and r["f0"] else None),
                        cos_base=(round(cos(r["emb"], base["emb"]), 4)
                                  if base and r["emb"] is not None else None)))
    json.dump(out, open("G:/_setup/_emo_probe.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出 _emo_probe.json")


if __name__ == "__main__":
    main()
