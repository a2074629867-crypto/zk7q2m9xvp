# -*- coding: utf-8 -*-
"""重建 finish_r6.py（原文件被一次失败的 patch 截断成 0 字节）。

改动点相对 finish_r5.py：
  1) docstring / 文件名 / 输出目录 r5 -> r6
  2) MOS 判据：r5 是「不许比旧差 0.15」，r6 改「绝对下限 1.5」+ 新增「声纹 PASS→MANUAL 拒收」
  3) 语速判据：r5 是绝对 90~260，r6 按句长分流（<=9 词用时长比 0.75~1.40）
"""
import io
import os

SRC = "G:/_setup/finish_r5.py"
DST = "G:/_setup/finish_r6.py"

s = open(SRC, encoding="utf-8").read()
orig = s

# ---- 1) docstring
s = s.replace(
    '''"""finish_r5.py \u2014\u2014 第五轮重生成收尾（Charles 紧张 13 + 激动反抗 8，换 48k 新参考）。

与 r3 的差别：多一条「自然度必须不变差」硬闸 \u2014\u2014 换参考的目的是提质量，
不能闸门过了、MOS 掉了也照收。判据：new_mos >= old_mos - 0.15（容 0.15 测量噪声）。''',
    '''"""finish_r6.py \u2014\u2014 第六轮重生成收尾（Thomas 警惕 12 + 激动反抗 13，换 48k 新参考）。

\u2605 与 r5 的**关键差别**：r5 判「MOS 不许变差」，r6 **不许沿用这条**。
   r6 换档的目标维度是**情绪可达 / 声纹身份**，不是音质：
   - Thomas/激动反抗 实测 MOS 3.16 -> 2.11（-1.05），但情绪闸从 ref_fallback(MANUAL)
     变 **PASS**（d=0.6947 >= p25 0.6239）。用 r5 的闸会把这批正解全拒掉。
   \u21d2 r6 的硬闸改成三条：
       1) 削波 < 0.999
       2) 语速：<=9 词用与旧音频的时长比 0.75~1.40；>9 词用绝对 90~260 wpm
          （短句 wpm 量化误差 \u00b135，1 词 \u2248 \u00b150wpm，绝对阈值会误杀「原本就快」的句子）
       3) MOS 绝对下限 >= 1.5（防崩，不比差值）
     另加：闸门判 REGEN 拒收；声纹闸从 PASS 掉到 MANUAL 拒收（身份不能变差）。''')

# ---- 2) 路径与文件名
for a, b in (
    ("_regen_r5.json", "_regen_r6.json"),
    ("_regen_r5_out", "_regen_r6_out"),
    ("out_bak_r5_1112", "out_bak_r6_1113"),
    ("_dlg_plan_r5_cand.jsonl", "_dlg_plan_r6_cand.jsonl"),
    ("_backfill_r5_ok.json", "_backfill_r6_ok.json"),
    ("_backfill_r5_log.json", "_backfill_r6_log.json"),
    ("_norm_r5_log.json", "_norm_r6_log.json"),
    ("finish_r5.py", "finish_r6.py"),
    ("_gate_r5_cand.json", "_gate_r6_cand.json"),
):
    s = s.replace(a, b)

# ---- 3) MOS 硬闸 -> r6 版本
s = s.replace(
    '''        # \u2605 换参考的目的是提质量：闸门过了但 MOS 掉了，说明这个新档对这句不适用
        #   （A/B 是单条证据，不能保证整档都受益）\u21d2 拒收，保留旧音频。
        m_old = (NG.raw(old) or {}).get("nq_mos")
        m_new = (NG.raw(new) or {}).get("nq_mos")
        if m_old is not None and m_new is not None and m_new < m_old - 0.15:
            bad.append("MOS\u964d %.2f->%.2f" % (m_old, m_new))''',
    '''        # \u2605 r6 不比 MOS 差值（见文件头）：只设绝对下限防崩。
        m_old = (NG.raw(old) or {}).get("nq_mos")
        m_new = (NG.raw(new) or {}).get("nq_mos")
        if m_new is not None and m_new < 1.5:
            bad.append("MOS\u5d29 %.2f" % m_new)
        # 身份不许变差：旧条声纹 PASS、新条掉到 MANUAL \u21d2 换档换出了别人。
        # 实测佐证（2026-11-13 01:05）：Thomas_defiant_1 的 5 条渲染，
        # Charles 余弦全部上升（c2_0468 0.447->0.566），cen gap 0.185->0.042。
        go = OLD_GATE.get(i) or {}
        if ((go.get("gates") or {}).get("speaker") == "PASS"
                and (g.get("gates") or {}).get("speaker") == "MANUAL"):
            bad.append("声纹PASS\u2192MANUAL")''')

# ---- 4) 语速闸按句长分流
s = s.replace(
    '''        wn = wpm_of(i, d2)
        if not (WPM_LO <= wn <= WPM_HI):
            bad.append("语速%.0fwpm(\u65b0)" % wn)''',
    '''        # \u2605 2026-11-13 01:10：语速判据按句长分流。
        #   <=9 词的短句上 wpm 量化误差可达 \u00b135（1 词 \u2248 \u00b150wpm），
        #   `c2_0302`（9 词 1.76s=307wpm）与旧音频（1.72s=314wpm）完全一致，
        #   却被绝对阈值 260 拒掉 \u2014\u2014 那是「原本就快」，不是截断。
        wc = len([k for k in (src.get(i) or {}).get("text", "").split()
                  if any(c.isalpha() for c in k)])
        wn = wpm_of(i, d2)
        if wc <= 9:
            if not (0.75 <= d2 / d1 <= 1.40):
                bad.append("短句时长x%.2f" % (d2 / d1))
        elif not (WPM_LO <= wn <= WPM_HI):
            bad.append("语速%.0fwpm(\u65b0)" % wn)''')

# ---- 5) OLD_GATE 注入
s = s.replace(
    '''    gate = {r["id"]: r for r in json.load(open(gate_json, encoding="utf-8"))}''',
    '''    gate = {r["id"]: r for r in json.load(open(gate_json, encoding="utf-8"))}
    global OLD_GATE
    OLD_GATE = {x["id"]: x for x in json.load(open("G:/_setup/_gate_dlg_v20.json", encoding="utf-8"))}''')

s = s.replace("TARGET = -24.0", "OLD_GATE = {}\nTARGET = -24.0", 1)

checks = [
    ("MOS\u5d29", "MOS 兜底"),
    ("声纹PASS", "身份闸"),
    ("短句时长x", "语速分流"),
    ("OLD_GATE", "旧闸注入"),
    ("_regen_r6.json", "清单路径"),
]
bad = [n for k, n in checks if k not in s]
if bad:
    raise SystemExit("缺少: %s" % bad)
if s == orig:
    raise SystemExit("未改动")

with io.open(DST, "w", encoding="utf-8", newline="\n") as f:
    f.write(s)
print("重建 finish_r6.py  %d 字节" % os.path.getsize(DST))
for k, n in checks:
    print("  \u2713 %s" % n)
