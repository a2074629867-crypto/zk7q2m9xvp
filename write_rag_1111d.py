# -*- coding: utf-8 -*-
"""把 2026-11-11 下午的对白回环结论写进 RAG。用 Python 传参，避开 shell 吞中文标点。"""
import subprocess
import sys

PY = r"G:/Python310/python.exe"
RAG = r"G:/_setup/rag/rag.py"

FACTS = [
    dict(
        topic="【定稿】按函数名判断功能必翻车：rms_voiced_db 做的是算术平均不是 RMS",
        conclusion=(
            "2026-11-11 为了统一「clean 归一到 −24」与「闸门测出 −27.7」的口径，把 narr_gate_phys.voiced_db "
            "改成直接调 ch123_rebuild.rms_voiced_db，结果 716 条全部 FIX、跨度从 0.32dB 变成 4.0dB。"
            "读实现才发现：`db, _ = L._env_db(); v = db[db > p90−32]; return float(np.mean(v))` —— "
            "**算术平均 dB，不是均方根**。实测 c1_0001 算术 −30.17 / 能量 −24.11，差 6.06dB。"
            "需求 23 的「voiced RMS −24dBFS」按物理定义只能指能量平均（RMS = 均方根）；"
            "716 条实测能量平均中位 −24.2、跨度 0.32dB，正是按这个口径归一的。"
            "⇒ 已回滚并在 docstring 记档。规则：复用任何「看起来是同一功能」的函数前，先读实现。"
        ),
        evidence="ch123_rebuild.py:11-18 rms_voiced_db；narr_gate_phys.py voiced_db；"
                 "c1_0001 实测 −30.17 vs −24.11；DECISIONS 同名条",
        tags="电平,voiced,度量,返工,教训,定稿",
    ),
    dict(
        topic="【定稿】结尾无衰减判据：单帧过线不算有声，要连续 3 帧（60ms）",
        conclusion=(
            "tail（末段有声时长）原判据是「最后一帧 db > −45dBFS」，而 −45 正是底噪抖动区，"
            "随机一帧越过就把 tail 算成 0.00~0.05s ⇒ 误报「结尾无衰减」19 条。"
            "实测它们末 100ms 全在 −42~−60dB 平滑过渡，没有 5ms 掉 50dB 的硬切（需求 20 防的是那个）。"
            "改成「连续 3 帧（60ms）都过线」才算语音终点 —— 60ms 是一个音素的最短尺度。"
            "**改判据必须做区分力验证**：把正常音频硬切 200ms 后 tail=0.040 仍判 FIX，原始 0.180 判 PASS。"
            "改完 19 → 2（剩的 2 条 tail 0.04/0.05 是真硬切）。"
        ),
        evidence="narr_gate_phys.py tail 计算段；_narr_phys.json FIX 清单前后对比；DECISIONS 同名条",
        tags="旁白,结尾,判据,假阳性,定稿",
    ),
    dict(
        topic="【定稿】wpm 判语速必须按词数分层，统一 band 对 1-3 词必然误报",
        conclusion=(
            "旁白 716 条按词数分档的 wpm 中位：1 词 **71** / 2-3 词 129 / 4-7 词 167 / 8-15 词 170 / >15 词 176。"
            "每条都带首尾静音，词数越少静音占比越高 ⇒ 用统一的 110 下限，1-3 词必然报「语速慢」"
            "（c2_0412 \"Silence.\" 1 词 1.07s = 81wpm、c3_0736 \"Inventive.\" = 61wpm，都不是缺陷）。"
            "改成只对 ≥4 词判档、短条只报数值：WATCH 8 → 4（剩下的 4 条是 ≥4 词的真慢，61~110wpm）。"
        ),
        evidence="narr_gate_phys.py 语速判据；_narr_phys.json 按词数分档统计",
        tags="旁白,语速,wpm,口径,定稿",
    ),
]


def main():
    for f in FACTS:
        cmd = [PY, RAG, "up", "-t", f["topic"], "-c", f["conclusion"],
               "-e", f["evidence"], "-s", "定稿", "--tags", f["tags"]]
        r = subprocess.run(cmd, cwd=r"G:/_setup/rag", capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        print(("OK  " if r.returncode == 0 else "FAIL") + "  " + f["topic"][:44])
        if r.returncode != 0:
            print("   ", (r.stdout or "")[-200:], (r.stderr or "")[-200:])
    r = subprocess.run([PY, RAG, "index"], cwd=r"G:/_setup/rag",
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((r.stdout or "").strip()[-160:])


if __name__ == "__main__":
    main()
