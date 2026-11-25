# -*- coding: utf-8 -*-
"""噪声闸回环验证：人为造 5 类阳性缺陷，要求全部检出；合格条不得误报。

为什么必须做这一步：2026-11-24 用户质问「这么明显的错误一个都没检测出来」，
根因是 G1 技术闸里**根本没有噪声项**（只测时长/削波/静音占比/硬切/RMS）。
补了判据不等于判据有效 —— 必须注入已知缺陷、量召回。

阳性（每类 2 条，基于 2 条干净底条）：
  P1 noise_floor  叠 55 dB 白噪（底噪 → 约 −45）
  P2 snr_low      叠 25 dB 白噪（SNR → 约 12）
  P3 digital_zero 句中插 50 ms 绝对零
  P4 hard_cut     砍掉尾部静音，满幅截断
  P5 floor_jump   前半加噪后半不加（段间跨度 > 10）
阴性（N1）：未处理的干净条，必须 PASS

用法：G:/Python310/python.exe _dn_selftest.py
"""
import json
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "G:/_setup")
sys.path.insert(0, "G:/_setup/emo_bench")
os.chdir("G:/_setup")
import dialog_gate as D
import _dn_uniform as DU

OUT = "G:/_setup/_dn_test"
SR = 48000


def load(p):
    y, sr = sf.read(p, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    return np.ascontiguousarray(y), sr


def add_noise(y, snr_db):
    """按目标 SNR 叠白噪（相对语音 p95 帧能量）。"""
    rms_v = float(np.sqrt((y ** 2).mean()) + 1e-12)
    rms_n = rms_v / (10 ** (snr_db / 20.0))
    n = np.random.default_rng(0).standard_normal(len(y))
    n = n / (np.sqrt((n ** 2).mean()) + 1e-12) * rms_n
    return (y + n).astype(np.float32)


def main():
    os.makedirs(OUT, exist_ok=True)
    bases = ["c1_0034", "c1_0049"]
    src = "G:/_setup/_audio_ch123/out/%s.wav"

    cases = []
    for b in bases:
        y, sr = load(src % b)
        # P1 底噪高
        cases.append(("P1_noise_floor", b, "noise_floor", add_noise(y, 28.0)))
        # P2 SNR 低
        cases.append(("P2_snr_low", b, "snr_low", add_noise(y, 12.0)))
        # P3 句中数字零
        z = y.copy()
        mid = len(z) // 2
        z[mid:mid + int(0.05 * sr)] = 0.0
        cases.append(("P3_digital_zero", b, "digital_zero", z))
        # P4 硬切：在能量最响处直接截断（真实硬切是「满幅被掐」，不是「去掉尾部静音」）
        c = y.copy()
        hw = int(0.05 * sr)
        nseg = len(c) // hw
        if nseg > 4:
            eng = np.array([np.sqrt((c[i * hw:(i + 1) * hw] ** 2).mean()) for i in range(nseg)])
            # 取后 1/3 段里最响的位置，保证仍在语流中
            lo = nseg // 3
            cut = (lo + int(np.argmax(eng[lo:]))) * hw
            c = c[:cut]
        cases.append(("P4_hard_cut", b, "hard_cut", c))
        # P5 段间底噪跳变
        j = y.copy()
        half = len(j) // 2
        j[half:] = add_noise(j[half:], 28.0)
        cases.append(("P5_floor_jump", b, "floor_jump", j))

    rows = []
    for tag, base, want, yy in cases:
        p = os.path.join(OUT, "%s_%s.wav" % (tag, base))
        sf.write(p, yy, SR, subtype="PCM_24")
        s = D.audio_stats(p)
        v, notes = D.gate_tech(s)
        codes = [n[0] for n in notes]
        hit = want in codes
        rows.append(dict(tag=tag, base=base, want=want, verdict=v, codes=codes, hit=hit))
        print("%-18s %-9s want=%-13s -> %-6s %s  %s" %
              (tag, base, want, v, "HIT " if hit else "MISS", codes))

    # 阴性
    neg = ["c1_0034", "c1_0049", "c2_0264", "c3_0623", "c2_0306"]
    n_rows = []
    for b in neg:
        p = src % b
        s = D.audio_stats(p)
        v, notes = D.gate_tech(s)
        codes = [n[0] for n in notes]
        n_rows.append(dict(id=b, verdict=v, codes=codes))
        print("NEG %-9s floor=%7.1f snr=%5.1f zero=%5.1f -> %-6s %s" %
              (b, s["floor_db"], s["snr_db"], s["zero_ms"], v, codes))

    hit = sum(1 for r in rows if r["hit"])
    fp = sum(1 for r in n_rows if r["verdict"] == "REGEN")
    print("\n召回 %d/%d   阴性误报 %d/%d" % (hit, len(rows), fp, len(n_rows)))
    ok = (hit == len(rows)) and (fp == 0)
    print("结论：%s" % ("PASS" if ok else "FAIL"))
    json.dump(dict(pos=rows, neg=n_rows, recall=(hit, len(rows)),
                   false_pos=(fp, len(n_rows)), pass_=ok),
              open("G:/_setup/_dn_selftest.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
