# -*- coding: utf-8 -*-
"""_edit_probe.py —— 验证「edit 任务 + emo 标签 + use_xvector」能否在本地跑通

背景
  `_tag_calib.py` 实测（2026-11-14 23:4x）：**tts 任务下 emo 标签对 vox 判据基本无效**
  （紧张 afraid −0.023、兴奋 happy −0.029，反而变差），因为 tts 的 voice-ref 锁死了
  音高/节奏基线，标签只能微调表层。

  `DOTS_MARKUP_RULES.md` 第九节（2026-10-18）：**edit 任务下 emo 极强**
  （angry 让 F0 +15.6 半音），但默认毁音色（0.38），必须 `use_xvector=on` 才救回 0.765。
  用户原话「EDIT 引擎它是支持加标签的」指的正是这条。

  但那次实验走的是**云端协议**（`cloud/loops.py`）。本地 CLI 有 `--source-audio`，
  从未验证过 edit 能否本地跑。本脚本补这个空白。

对照（同一句 c2_0371，现役 = Thomas_calm_1，emo=激动反抗，判据 signal=d dominance）
  A_cur    现役音频（基线）
  B_edit   source_audio=现役 + emo disgusted L2（标定里 tts 下最有效的标签）
  C_edit_x 同 B + use_xvector=on
  D_edit_angry  source_audio=现役 + emo angry L2 + use_xvector=on

判据：dominance 是否上升 + 声纹是否 ≥0.65 + 时长是否守住（tempo ≥0.70）

用法：G:/Python310/python.exe _edit_probe.py
"""
import json
import os
import subprocess
import sys
import time

import numpy as np

# ★ verdict / ser / vox 都在 emo_bench 子目录；必须在**文件顶部**加路径，
#   放在 score() 里 import 之后就晚了（本轮实测踩中：ModuleNotFoundError: verdict）。
sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
sys.path.insert(0, "G:/voice_lib")

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
LIB = "G:/_setup/_emo_refs_all.json"
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
OUT = "G:/_setup/_edit_probe"
SID = "c2_0371"
SEED = 42


def resolve(lib, voice):
    head, n = voice.rsplit("_", 1)
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    it = items[int(n) - 1]
    if isinstance(it, dict):
        return it.get("path"), it.get("text") or ""
    return it, ""


def variants(text):
    return [
        ("B_edit_disgusted", '<emo type="disgusted" level="2">%s</emo>' % text, {}),
        ("C_edit_disg_xv", '<emo type="disgusted" level="2">%s</emo>' % text,
         {"use_xvector": "on"}),
        ("D_edit_angry_xv", '<emo type="angry" level="2">%s</emo>' % text,
         {"use_xvector": "on"}),
        ("E_edit_plain_xv", text, {"use_xvector": "on"}),
    ]


def run_edit(text, src, ref, rtext, out, extra):
    mt = max(200, int(len(text.split()) * 26) + 400)
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--source-audio", src,
           "--voice-ref", ref, "--reference-text", rtext or "",
           "--text", text, "--seed", str(SEED), "--out", out,
           "--request-option", "max_tokens=%d" % mt,
           "--request-option", "template_name=edit",
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    for k, v in extra.items():
        cmd += ["--request-option", "%s=%s" % (k, v)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ACPP_DIR, timeout=900)
    dt = time.time() - t0
    ok = os.path.exists(out) and os.path.getsize(out) > 40000
    return ok, dt, (r.stdout + r.stderr)[-400:] if not ok else ""


def score(p):
    import soundfile as sf
    import verdict as V
    import ser as S
    from _mut_all import M
    import _utt_verify as U
    if "G:/_setup/emo_bench" not in sys.path:
        sys.path.insert(0, "G:/_setup/emo_bench")
    sc = S.VoxDim().score(p) or {}
    return dict(dur=round(sf.info(p).duration, 2),
                A=round(sc.get("arousal", 0), 3),
                V=round(sc.get("valence", 0), 3),
                D=round(sc.get("dominance", 0), 3),
                d_signal=round(float(V.vox_feat(sc, "d")), 4),
                emb=U.utt_emb(M("r34"), p))


def main():
    plan = {json.loads(l)["id"]: json.loads(l) for l in open(PLAN, encoding="utf-8")}
    lib = json.load(open(LIB, encoding="utf-8"))
    r = plan[SID]
    ref, rtext = resolve(lib, r["voice"])
    src = "G:/_setup/_audio_ch123/out/%s.wav" % SID
    os.makedirs(OUT, exist_ok=True)
    print("源 %s (%.2fs)  参考 %s" % (src, __import__("soundfile").info(src).duration, ref))

    rows = []
    base = score(src)
    base["tag"] = "A_cur"
    rows.append(base)

    for tag, text, extra in variants(r["text"]):
        p = os.path.join(OUT, "%s.wav" % tag)
        if os.path.exists(p) and os.path.getsize(p) > 40000:
            print("[skip] %s" % tag, flush=True)
        else:
            ok, dt, err = run_edit(text, src, ref, rtext, p, extra)
            print("[%s] %s %.1fs %s" % (tag, "OK" if ok else "FAIL", dt, err), flush=True)
            time.sleep(1)
        if os.path.exists(p) and os.path.getsize(p) > 40000:
            s = score(p)
            s["tag"] = tag
            rows.append(s)

    print()
    print("%-18s %7s %8s %7s %7s %7s %8s %8s" %
          ("变体", "dur", "d_signal", "A", "V", "D", "声纹", "tempo"))
    b = rows[0]
    for x in rows:
        cos = float(np.dot(x["emb"], b["emb"]) /
                    (np.linalg.norm(x["emb"]) * np.linalg.norm(b["emb"]) + 1e-9))
        tp = b["dur"] / x["dur"] if x["dur"] else 0
        print("%-18s %7.2f %8.4f %7.3f %7.3f %7.3f %8.3f %8.2f" %
              (x["tag"], x["dur"], x["d_signal"], x["A"], x["V"], x["D"], cos, tp))

    json.dump([{k: v for k, v in x.items() if k != "emb"} for x in rows],
              open("G:/_setup/_edit_probe.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出 _edit_probe.json")


if __name__ == "__main__":
    main()
