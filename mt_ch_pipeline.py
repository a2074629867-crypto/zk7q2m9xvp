# -*- coding: utf-8 -*-
"""章级流水线：裁边 → **RDR 闸门** → 拼接插停顿。

顺序不许改。RDR 必须在任何停顿处理之前跑：
我们的单元内部有模型念标点自带的停顿（180 个里 139 个），
一旦再往上叠我们自己插的停顿，含停顿口径（RDR 原文的 B）就彻底失效，
只剩 voiced 口径可读。

每一步都可单独跳过（产物存在即复用），失败默认中止。

用法：
  # 完整跑一章
  G:/Python310/python.exe mt_ch_pipeline.py --ch ch1 \\
      --raw _mt_final_raw_ch1 --trim _mt_final_raw_trim \\
      --para _ch1_unit_para.json --out-wav _chap_ch1_v5.wav

  # 只跑闸门
  G:/Python310/python.exe mt_ch_pipeline.py --ch ch1 --only gate

参数缺省值与 v4b 一致（--gap-para 1.55 / clause 1.05 / bound 0.85 / none 0.30，
--norm-target -25.1）。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(cmd, tag):
    print("\n[%s] %s" % (tag, " ".join(cmd[1:])))
    r = subprocess.run(cmd, cwd=HERE)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", default="ch1")
    ap.add_argument("--raw", default="_mt_final_raw_ch1", help="TTS 原始单元目录")
    ap.add_argument("--trim", default="_mt_final_raw_trim", help="裁边后单元目录")
    ap.add_argument("--para", default="_ch1_unit_para.json", help="单元→段落映射")
    ap.add_argument("--out-wav", default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--head-pad", default="0.05")
    ap.add_argument("--tail-pad", default="0.20")
    ap.add_argument("--gap-para", default="1.55")
    ap.add_argument("--gap-clause", default="1.05")
    ap.add_argument("--gap-bound", default="0.85")
    ap.add_argument("--gap-none", default="0.30")
    ap.add_argument("--norm-target", default="-25.1")
    ap.add_argument("--max-rdr", default="0.15")
    ap.add_argument("--allow-fail", action="store_true",
                    help="闸门 FAIL 也继续拼接（默认中止）")
    ap.add_argument("--only", choices=["trim", "gate", "join"], default=None)
    ap.add_argument("--force", action="store_true", help="忽略已有产物，强制重跑")
    a = ap.parse_args()

    steps = ["trim", "gate", "join"] if not a.only else [a.only]
    out_wav = a.out_wav or ("_chap_%s_v5.wav" % a.ch)
    json_out = a.json_out or ("_chap_%s_v5.json" % a.ch)

    # ---- 1 裁边
    if "trim" in steps:
        n = len([f for f in os.listdir(a.trim) if f.endswith(".wav")]) \
            if os.path.isdir(a.trim) else 0
        if n > 0 and not a.force:
            print("\n[trim] 复用 %s（%d 个单元）" % (a.trim, n))
        else:
            if run([PY, "mt_trim_head.py", "--in", a.raw, "--out", a.trim,
                    "--head-pad", a.head_pad, "--tail-pad", a.tail_pad,
                    "--json", "_trim_%s.json" % a.ch], "trim") != 0:
                print("✗ 裁边失败")
                return 1

    # ---- 2 RDR 闸门（必须在插停顿之前）
    if "gate" in steps:
        rc = run([PY, "mt_rdr_gate.py", "--ch", a.ch, "--units", a.trim,
                  "--para", a.para, "--max-rdr", a.max_rdr,
                  "--out", "_rdr_gate_%s.json" % a.ch], "gate")
        if rc == 2:
            print("✗ 闸门缺输入（多半是没做单元→段落对齐）")
            return 2
        if rc == 1 and not a.allow_fail:
            print("✗ 闸门 FAIL，已中止。要强行继续加 --allow-fail。")
            return 1
        if rc == 1:
            print("⚠ 闸门 FAIL，按 --allow-fail 继续。")

    # ---- 3 拼接插停顿
    if "join" in steps:
        if run([PY, "mt_chapter_join.py", "--dir", a.trim, "--ch", a.ch,
                "--out", out_wav, "--norm-target", a.norm_target,
                "--norm-max-gain", "6", "--norm-max-cut", "3", "--no-bed",
                "--gap-para", a.gap_para, "--gap-clause", a.gap_clause,
                "--gap-bound", a.gap_bound, "--gap-none", a.gap_none,
                "--para-map", a.para, "--json", json_out], "join") != 0:
            print("✗ 拼接失败")
            return 1

    print("\n✓ %s 完成：%s" % (a.ch, out_wav if "join" in steps else "(未拼接)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
