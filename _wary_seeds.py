# -*- coding: utf-8 -*-
"""_wary_seeds.py —— 警惕「未达」条目继续加 seed（BIMODAL 规则）。

依据（2026-11-13 01:30 实测）：
  Thomas_wary_1 参考自身 e2v disgusted = 0.9989  ⇒ 判据可达，不是坏尺子
  seed 7 产出过 0.9996 ⇒ 双峰真实存在，只是命中率低
  故对 still-未达 的条目再加 seed，取 disgusted 最高者，同分比 MOS。

不写 OUT（避免与后续过闸抢文件）；只把候选落到 _wary_s{seed}/ 并输出 _wary_seeds_log.json。
用法：python _wary_seeds.py 11 23
"""
import json, os, subprocess, sys
sys.path.insert(0, "G:/_setup"); sys.path.insert(0, "G:/_setup/emo_bench")

ACPP_DIR = r"C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
HERE = "G:/_setup"
P25 = 0.0052
TARGETS = ["c2_0210", "c2_0274", "c2_0324", "c2_0365", "c3_0637", "c3_0875"]


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def resolve(lib, voice):
    parts = voice.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None, None
    head, n = parts[0], int(parts[1])
    role, _, emo = head.partition("_")
    items = (lib.get(role) or {}).get(emo) or []
    if 1 <= n <= len(items):
        it = items[n - 1]
        return (it.get("path"), it.get("text") or "") if isinstance(it, dict) else (it, "")
    return None, None


def main():
    seeds = [str(s) for s in sys.argv[1:]] or ["11", "23"]
    lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}
    todo = {t["id"]: t for t in json.load(open(os.path.join(HERE, "_regen_r6.json"), encoding="utf-8"))}
    print("加 seed %s，目标 %d 条" % (seeds, len(TARGETS)), flush=True)

    for k, i in enumerate(TARGETS, 1):
        t = todo[i]
        ref, rtext = resolve(lib, t["voice"])
        text = plan[i].get("text_src") or plan[i]["text"]
        for s in seeds:
            d = os.path.join(HERE, "_wary_s" + s)
            os.makedirs(d, exist_ok=True)
            out = os.path.join(d, "%s_s%s.wav" % (i, s))
            if os.path.exists(out) and os.path.getsize(out) > 50000:
                print("[%d/%d] %s s%s 已存在，跳过" % (k, len(TARGETS), i, s), flush=True)
                continue
            cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                   "--backend", "vulkan", "--threads", "6",
                   "--voice-ref", ref, "--reference-text", rtext or "",
                   "--text", text, "--seed", s, "--out", out,
                   "--request-option", "max_tokens=%d" % mtok(len(text.split())),
                   "--session-option", "dots_tts.mem_saver=true", "--metrics"]
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ACPP_DIR, timeout=1800)
            ok = os.path.exists(out) and os.path.getsize(out) > 50000
            print("[%d/%d] %s s%s %s" % (k, len(TARGETS), i, s, "OK" if ok else "失败"), flush=True)

    # 统一评判：当前 OUT vs 各 seed 候选
    import ser as S
    import _nat_guard as NG
    e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))

    def probe(p):
        sc = e2v.score(p) or {}
        return float(sc.get("厌恶/disgusted", 0.0)), float(NG.raw(p).get("nq_mos") or 0), sc.get("_top")

    rows = []
    for i in TARGETS:
        cur = os.path.join(HERE, "_regen_r6_out", i + ".wav")
        cands = [(i, cur, "cur")] if (os.path.exists(cur) and os.path.getsize(cur) > 50000) else []
        for s in ["7"] + seeds:
            p = os.path.join(HERE, "_wary_s" + s, "%s_s%s.wav" % (i, s))
            if os.path.exists(p) and os.path.getsize(p) > 50000:
                cands.append((i, p, "s" + s))
        best = None
        for iid, p, tag in cands:
            d, m, top = probe(p)
            if best is None or (d, m) > (best["d"], best["m"]):
                best = dict(id=iid, tag=tag, d=round(d, 4), m=round(m, 2), top=top, path=p)
        # 平手时优先 cur（不改动）
        for iid, p, tag in cands:
            d, m, top = probe(p)
            if tag == "cur" and abs(d - best["d"]) < 1e-9 and abs(m - best["m"]) < 1e-9:
                best.update(tag="cur", d=round(d, 4), m=round(m, 2), top=top, path=p)
        best["pass"] = best["d"] >= P25
        rows.append(best)
        print("%-8s 胜 %-4s disgusted %.4f MOS %.2f top %s %s"
              % (i, best["tag"], best["d"], best["m"], best["top"],
                 "PASS" if best["pass"] else "未达"), flush=True)

    json.dump(rows, open(os.path.join(HERE, "_wary_seeds_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n达标 %d / %d" % (sum(1 for r in rows if r["pass"]), len(rows)), flush=True)


if __name__ == "__main__":
    main()
