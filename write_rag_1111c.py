# -*- coding: utf-8 -*-
"""把 2026-11-11 下午的对白回环结论写进 RAG。用 Python 传参，避开 shell 吞中文标点。"""
import subprocess
import sys

PY = r"G:/Python310/python.exe"
RAG = r"G:/_setup/rag/rag.py"

FACTS = [
    dict(
        topic="【定稿】ref_emo 必须取生成时的 voice 档，不能取声纹 1-NN 的最近档",
        conclusion=(
            "dialog_gate 的 gate_emotion(ref_emo=...) 原先取 spk['emo']，那是**按音色相似度**"
            "找出的最近模板档，与「这条音频实际用哪个参考生成」是两件事。实测反例（都标注激动反抗）："
            "c2_0320 的 1-NN 判成 excited、c2_0467 判成 wary、c3_0628 判成 wronged，"
            "全部误报 ref_fallback，一次 95 条。正确口径：取 plan 的 voice 字段"
            "（Thomas_loud_1 → loud），那才是生成时实际用的档。已加 one(..., voice=) + _voice_emo()；"
            "plan 的 voice 由 _castle_en_ch123_plan.jsonl 补齐，回填过的条目改用 _regen_dlg.json 的 voice_next。"
            "改后 ref_fallback 95 → 78，且 78 条全部是真不匹配（档不在该情绪允许集），0 条判据误报。"
        ),
        evidence="dialog_gate.py:_voice_emo / one()；_gate_dlg_v4.json vs 修复后 _t_v5_20.json；"
                 "_dlg_plan_v2.jsonl 新增 voice 字段",
        tags="对白,声纹,ref_fallback,判据,定稿",
    ),
    dict(
        topic="【定稿】回环验收要比 REGEN 条数，不能比 PASS 条数",
        conclusion=(
            "同一份 dialog_gate.py、同一份 plan，v3 判 70 PASS、v4 判 66 PASS —— 差别不在音频，"
            "而在 v3 那份 JSON 是旧判据的产物（10:19 改过代码；v3 记录里 ref_fallback 出现 0 次，"
            "现代码必出）。同类坑还有 --limit 原先只对 --dir 生效，--plan ... --limit 20 实际跑了全量 239 条"
            "并覆盖快照文件（已修）。⇒ 回环验收必须同代码 + 同 plan，并比 **REGEN 条数**："
            "v3→v4 回填 49 条后 REGEN 77 → 7，这是硬指标；PASS 70→66 是被判据变化污染的数字，不能当改善或恶化。"
        ),
        evidence="_gate_dlg_v3.json（ref_fallback 0 次）vs _gate_dlg_v4.json（95 次）；"
                 "_backfill_log.json；dialog_gate.py 的 limit 修复",
        tags="对白,验收,指标,回环,定稿",
    ),
    dict(
        topic="【定稿】候选回填必须加物理硬闸：时长比 0.65~1.55 + 无削波",
        conclusion=(
            "77 条重生成候选过 dialog_gate：27 PASS / 42 MANUAL / 8 REGEN、0 条变差，"
            "但其中 9 条时长是原件的 0.52~5.54 倍也被判 PASS —— dialog_gate 没有时长合理性检查。"
            "回填前必须加物理硬闸：时长比 0.65~1.55（后期 tempo 只能降速到 0.70，最多压 1.43 倍；"
            "短于 0.65 无法用加速补救）+ 峰值 < 0.999（削波不可逆）。加上后 77 → 49 条可回填，30 条打回。"
            "另一条：参考库缺档（Charles 缺 nervous/panic 13 条、Thomas 缺 wary 12 条、Thomas 缺 excited 5 条、"
            "Helena 缺 calm 1 条、Thomas 缺 nervous 1 条、Charles 缺 wary 1 条）共 33 条改不了，"
            "只能补参考音频，不能算进 PASS 分母，也不能调阈值糊过去。"
        ),
        evidence="_gate_dlg_cand.json 与 _backfill_ok.json/_backfill_log.json；_regen_r2.json（45 条可修）；"
                 "_emo_refs_all.json 覆盖表",
        tags="对白,回填,硬闸,参考库,定稿",
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
