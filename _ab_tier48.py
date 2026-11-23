# -*- coding: utf-8 -*-
"""_ab_tier48.py —— 验证两种改法，为 126 条老档重生成定方向。

背景（2026-11-13 20:05 实测）：
  5 个仍用 16k 参考的档，档内 pair-cos 只有 0.34~0.58；换过 48k 的档是 0.68~0.76。
  但进一步查 plan 发现更根本的问题 —— **档位指派错了**：
    Thomas_loud_1     62 条里 58 条是「激动反抗」，而 defiant 档早就有了
    Charles_soft_1    23 条里 12 条是「委屈」，而 wronged 档早就有了
  所以这轮同时验两条路：
    A) 同档换 48k 参考（素材升级）
    B) 换成语义正确的档（档位重指派）

  ★ 第一版有个自造 bug：本地写的 vdb 是 `10 ** (v/20.0) ** 2`，
    Python 解析成 `10 ** ((v/20)**2)`，对 −30dB 的帧算成 +22.5dB（差 52dB），
    归一化把音频压到 −70dBFS，于是所有候选 MOS 都掉到 2.0，得出「48k 参考伤音质」的错误结论。
    **教训：项目已有 `norm_dlg.vdb`，不要手写第二份实现。**（同「分类逻辑只能有一份」）

判据（先定好再看结果）：
  cos_char   与角色 48k 核心质心的 cos，提升 ≥ 0.08 或绝对值 ≥ 0.55
  MOS        不低于基线 − 0.30
  ratio      时长比 ≥ 0.80（变短 = 截断风险）

用法：python _ab_tier48.py [组名...]
"""
import json, os, subprocess, sys
import numpy as np
import soundfile as sf

HERE = "G:/_setup"
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "emo_bench"))

from norm_dlg import vdb  # ★ 用项目唯一实现，不手写

ACPP_DIR = r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
OUT = os.path.join(HERE, "_ab48")
os.makedirs(OUT, exist_ok=True)
TARGET = -24.0

# 组名 -> (测试句, 角色, [参考：cid 或 voice 名], 说明)
PLAN = {
    # A 路：同档换 48k 参考
    "Charles_soft_48k":    ("c2_0291", "Charles", ["c268_p0", "c317_p1", "c173_p0"], "A 同档换48k"),
    "Charles_neutral_48k": ("c3_0812", "Charles", ["c350_p0", "c181_p1", "c255_p0"], "A 同档换48k"),
    "Charles_excited_48k": ("c3_0953", "Charles", ["c305_p0", "c032_p0", "c030_p0"], "A 同档换48k"),
    "Thomas_calm_48k":     ("c2_0210", "Thomas",  ["c099_p1", "c276_p0", "c393_p0"], "A 同档换48k"),
    "Thomas_loud_48k":     ("c2_0292", "Thomas",  ["c285_p0", "c012_p1"], "A 同档换48k"),
    # B 路：档位重指派（用语义正确、且已是 48k 的档）
    "Charles_soft2wronged": ("c2_0291", "Charles", ["Charles_wronged_2", "Charles_wronged_3"], "B 委屈→wronged"),
    "Thomas_loud2defiant":  ("c2_0292", "Thomas",  ["Thomas_defiant_2", "Thomas_defiant_3"], "B 激动反抗→defiant"),
}


def mtok(n):
    return max(120, min(900, int(n * 12 + 120)))


def resolve(ref, lib, meas):
    """参考可以是 _refs_new/cand 里的 cid，也可以是 lib 里的 voice 名。"""
    if ref in meas:
        return os.path.join(HERE, "_refs_new/cand", ref + ".wav"), meas[ref].get("text") or ""
    parts = ref.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        head, n = parts[0], int(parts[1])
        role, _, emo = head.partition("_")
        items = (lib.get(role) or {}).get(emo) or []
        if 1 <= n <= len(items):
            it = items[n - 1]
            p = it.get("path") if isinstance(it, dict) else it
            return p, (it.get("text") or "") if isinstance(it, dict) else ""
    return None, ""


def main():
    from _mut_all import M
    from _utt_verify import utt_emb
    import _nat_guard as NG

    only = set(sys.argv[1:])
    meas = {r["cid"]: r for r in json.load(open(os.path.join(HERE, "_refs_new/meas.json"), encoding="utf-8"))}
    lib = json.load(open(os.path.join(HERE, "_emo_refs_all.json"), encoding="utf-8"))
    plan = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(HERE, "_dlg_plan_v2.jsonl"), encoding="utf-8") if l.strip()}

    z = np.load(os.path.join(HERE, "_refs_new/thin_emb.npz"), allow_pickle=True)
    cids_all, vecs = z["cids"].tolist(), z["vecs"]
    idx = {c: k for k, c in enumerate(cids_all)}

    def cent_of(role):
        cs = [r["cid"] for r in meas.values() if r.get("role") == role and r["cid"] in idx]
        V = np.stack([vecs[idx[c]] for c in cs])
        V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
        c0 = V.mean(0); c0 /= np.linalg.norm(c0)
        core = V[V @ c0 >= 0.5]
        c = core.mean(0)
        return c / (np.linalg.norm(c) + 1e-9)

    CEN = {r: cent_of(r) for r in ("Charles", "Thomas")}
    mp = M("r34")

    def emb(p):
        v = np.asarray(utt_emb(mp, p), dtype=np.float32).ravel()
        return v / (np.linalg.norm(v) + 1e-9)

    rows = []
    for gname, (tid, role, refs, note) in PLAN.items():
        if only and gname not in only:
            continue
        text = plan[tid].get("text_src") or plan[tid]["text"]
        print("\n===== %s｜%s｜试句 %s（%d 词，现 %s）====="
              % (gname, note, tid, len(text.split()), plan[tid]["voice"]), flush=True)

        base = os.path.join(HERE, "_audio_ch123/out", tid + ".wav")
        y0, sr0 = sf.read(base, dtype="float32")
        if y0.ndim > 1:
            y0 = y0.mean(1)
        cos0 = float(emb(base) @ CEN[role])
        mos0 = float(NG.raw(base).get("nq_mos") or 0)
        print("  基线 cos_char %.3f  MOS %.2f  %.2fs  rms %.1f"
              % (cos0, mos0, len(y0) / sr0, vdb(y0, sr0)), flush=True)

        cands = []
        for ref in refs:
            rp, rtext = resolve(ref, lib, meas)
            if not rp or not os.path.exists(rp):
                print("  %-22s 参考缺失" % ref, flush=True); continue
            raw_p = os.path.join(OUT, "%s_%s_%s.raw.wav" % (gname, tid, ref.replace("/", "_")))
            out = os.path.join(OUT, "%s_%s_%s.wav" % (gname, tid, ref.replace("/", "_")))
            if not (os.path.exists(raw_p) and os.path.getsize(raw_p) > 50000):
                cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
                       "--backend", "vulkan", "--threads", "6",
                       "--voice-ref", rp, "--reference-text", rtext or "",
                       "--text", text, "--seed", "42", "--out", raw_p,
                       "--request-option", "max_tokens=%d" % mtok(len(text.split())),
                       "--session-option", "dots_tts.mem_saver=true"]
                subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=ACPP_DIR, timeout=1800)
            if not (os.path.exists(raw_p) and os.path.getsize(raw_p) > 50000):
                print("  %-22s 生成失败" % ref, flush=True); continue
            y, sr = sf.read(raw_p, dtype="float32")
            if y.ndim > 1:
                y = y.mean(1)
            r0 = vdb(y, sr)
            y = y * (10 ** ((TARGET - r0) / 20.0))     # 归一到 -24dBFS 再评
            sf.write(out, y.astype(np.float32), sr, subtype="PCM_16")
            cands.append(dict(ref=ref, dur=len(y) / sr,
                              cos_char=float(emb(out) @ CEN[role]),
                              cos_ref=float(emb(out) @ emb(rp)),
                              mos=float(NG.raw(out).get("nq_mos") or 0),
                              rms=vdb(y, sr), path=out, raw=raw_p))
            c = cands[-1]
            c["ratio"] = c["dur"] / (len(y0) / sr0)
            c["pass"] = ((c["cos_char"] - cos0 >= 0.08) or c["cos_char"] >= 0.55) \
                and c["mos"] >= mos0 - 0.30 and c["ratio"] >= 0.80
            print("  %-22s cos_char %.3f (%+.3f)  cos_ref %.3f  MOS %.2f (%+.2f)  "
                  "%.2fs x%.2f  rms %.1f  %s"
                  % (c["ref"], c["cos_char"], c["cos_char"] - cos0, c["cos_ref"],
                     c["mos"], c["mos"] - mos0, c["dur"], c["ratio"], c["rms"],
                     "PASS" if c["pass"] else "未过"), flush=True)

        good = [c for c in cands if c["pass"]]
        best = max(good, key=lambda x: (x["cos_char"], x["mos"])) if good else None
        print("  → %s" % ("✅ " + best["ref"] if best else "❌ 全部未过"), flush=True)
        rows.append(dict(group=gname, id=tid, note=note,
                         base=dict(cos_char=cos0, mos=mos0, dur=len(y0) / sr0),
                         cands=[{k: v for k, v in c.items() if k not in ("path", "raw")} for c in cands],
                         best=best["ref"] if best else None))

    json.dump(rows, open(os.path.join(HERE, "_ab48_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n===== 汇总 =====")
    for r in rows:
        print("  %-22s 基线 cos %.3f MOS %.2f  →  %s" % (
            r["group"], r["base"]["cos_char"], r["base"]["mos"], r["best"] or "无"))


if __name__ == "__main__":
    main()
