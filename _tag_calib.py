# -*- coding: utf-8 -*-
"""_tag_calib.py —— 标签映射标定：我们的中文情绪该映射到 dots 的哪个 type

背景
  2026-11-14 23:1x 实测（`_emo_tag_probe.py`）：tts 任务下 inline emo 标签**生效**，
  但幅度只有 edit 的 1/6（+2.5 vs +15.6 半音），声纹 0.865（不毁音色），
  level 2/3 是死参数（L2 +2.5 / L3 +1.4，不单调）。

用户要的是「检测到情绪不到位 → 自动加标签 → 再生成」的闭环。
但第一步必须知道：我们的 6 个中文情绪，各该映射到 dots 的哪个 type。

dots 只支持 8 种：afraid angry calm disgusted happy melancholic sad surprised
我们的词表：平静 紧张 警惕 激动反抗 委屈 兴奋

候选映射（待实测，不猜）
  紧张     -> afraid / surprised / sad
  激动反抗 -> angry / disgusted
  兴奋     -> happy / surprised
  警惕     -> afraid / angry / disgusted
  委屈     -> sad / melancholic
  平静     -> calm（判据退化，只作对照）

判据：用**生产同一套**情绪分（vox 维度 / e2v disgusted），看哪个标签让该情绪的
`value` 提升最大。不看 F0 —— F0 变了不等于情绪到位（用户要的是情绪维度）。

用法：G:/Python310/python.exe _tag_calib.py [--dry]
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
PLAN = "G:/_setup/_dlg_plan_v2.jsonl"
OUT = "G:/_setup/_tag_calib"
SEED = 42

# 标定样本：每种情绪挑最长的一条（长句情绪信号才稳）
CASES = [
    # (sid, 中文情绪, [(tag, dots_type, level), ...])
    ("c1_0015", "紧张", [("afraid2", "afraid", 2), ("surprised2", "surprised", 2), ("sad2", "sad", 2)]),
    ("c2_0299", "紧张", [("afraid2", "afraid", 2), ("surprised2", "surprised", 2)]),
    ("c2_0371", "激动反抗", [("angry2", "angry", 2), ("disgusted2", "disgusted", 2)]),
    ("c2_0264", "兴奋", [("happy2", "happy", 2), ("surprised2", "surprised", 2)]),
    ("c2_0487", "警惕", [("afraid2", "afraid", 2), ("angry2", "angry", 2)]),
]


def load():
    lib = json.load(open(LIB, encoding="utf-8"))
    plan = {}
    for l in open(PLAN, encoding="utf-8"):
        r = json.loads(l)
        plan[r["id"]] = r
    return lib, plan


def resolve(lib, voice):
    head, n = voice.rsplit("_", 1)
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    it = items[int(n) - 1]
    if isinstance(it, dict):
        return it.get("path"), it.get("text") or ""
    return it, ""


def gen(text, ref, rtext, out, seed=SEED):
    mt = max(200, int(len(text.split()) * 26) + 200)
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--voice-ref", ref, "--reference-text", rtext or "",
           "--text", text, "--seed", str(seed), "--out", out,
           "--request-option", "max_tokens=%d" % mt,
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ACPP_DIR, timeout=900)
    dt = time.time() - t0
    ok = os.path.exists(out) and os.path.getsize(out) > 40000
    return ok, dt, (r.stdout + r.stderr)[-300:] if not ok else ""


def main():
    dry = "--dry" in sys.argv
    lib, plan = load()
    os.makedirs(OUT, exist_ok=True)

    jobs = []
    for sid, emo, variants in CASES:
        r = plan[sid]
        ref, rtext = resolve(lib, r["voice"])
        base = "_audio_ch123/out/%s.wav" % sid
        jobs.append((sid, emo, "base", r["text"], ref, rtext, base, True))
        for tag, typ, lv in variants:
            t = '<emo type="%s" level="%d">%s</emo>' % (typ, lv, r["text"])
            jobs.append((sid, emo, tag, t, ref, rtext,
                         os.path.join(OUT, "%s__%s.wav" % (sid, tag)), False))

    print("标定任务 %d 个（其中需生成 %d 个）" % (len(jobs), sum(1 for j in jobs if not j[7])))
    if dry:
        for j in jobs:
            print("  %-9s %-6s %-12s %s" % (j[0], j[1], j[2], "复用现役" if j[7] else "生成"))
        return

    rows = []
    for sid, emo, tag, text, ref, rtext, out, reuse in jobs:
        if reuse:
            ok = os.path.exists(out)
            dt = 0.0
        elif os.path.exists(out) and os.path.getsize(out) > 40000:
            ok, dt = True, 0.0
        else:
            ok, dt, err = gen(text, ref, rtext, out)
            print("  [%s %s] %s %.1fs %s" % (sid, tag, "OK" if ok else "FAIL", dt, err), flush=True)
            time.sleep(1)
        if ok:
            rows.append(dict(sid=sid, emo=emo, tag=tag, path=out))
        else:
            print("  [%s %s] 失败，跳过" % (sid, tag), flush=True)

    # 用生产同一套判据打分
    print("\n=== 情绪分（生产判据）===")
    sys.path.insert(0, "G:/_setup")
    # ★ vox_feat / ser 都在 emo_bench 子目录，只加 G:/_setup 会 ModuleNotFoundError
    #   （本轮实测踩中：11 个候选全生成完了，打分阶段才炸）。
    if "G:/_setup/emo_bench" not in sys.path:
        sys.path.insert(0, "G:/_setup/emo_bench")
    os.environ.setdefault("PYTHONPATH", "G:/_setup;G:/_setup/emo_bench")
    import dialog_gate as DG
    import verdict as V      # ★ 生产用的就是 verdict，不是 vox_feat（凭记忆写错过一次）
    import ser as S

    # ★ dialog_gate 里的 vox / e2v 是在 main() 里初始化的全局，import 时是 None。
    #   这里必须自己建，否则 V.vox_feat(None, key) 会让整批判 0
    #   —— 与 11-14「vox_feat 签名错导致整批判 0」同型的坑。
    vox = S.VoxDim()
    e2v = None
    res = {}
    for r in rows:
        sc = None
        try:
            if V.PRIMARY[r["emo"]][0] == "vox":
                sc = vox.score(r["path"]) or {}
                val = V.vox_feat(sc, V.PRIMARY[r["emo"]][1])
            else:
                if e2v is None:
                    e2v = S.E2V("G:/_setup/models/ms/iic/emotion2vec_plus_large")
                sc = e2v.score(r["path"]) or {}
                val = float(sc.get("厌恶/disgusted", 0.0))
        except Exception as e:
            print("  打分失败 %s %s: %s" % (r["sid"], r["tag"], e))
            continue
        r["val"] = round(float(val), 4)
        r["A"] = round(sc.get("arousal", 0), 3) if sc else None
        r["V"] = round(sc.get("valence", 0), 3) if sc else None
        res.setdefault((r["sid"], r["emo"]), []).append(r)

    for (sid, emo), rs in res.items():
        base = next((x for x in rs if x["tag"] == "base"), None)
        print("\n%s  %s  （信号 %s）" % (sid, emo, V.PRIMARY[emo][1]))
        print("  %-14s %8s %8s %8s %s" % ("变体", "value", "Δ", "A", "V"))
        for x in rs:
            d = ""
            if base and base.get("val") is not None:
                d = "%+.4f" % (x["val"] - base["val"])
            print("  %-14s %8.4f %8s %8s %8s" % (x["tag"], x["val"], d, x["A"], x["V"]))

    json.dump([{k: v for k, v in r.items() if k != "path"} for r in rows],
              open("G:/_setup/_tag_calib.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写出 _tag_calib.json")


if __name__ == "__main__":
    main()
