# -*- coding: utf-8 -*-
"""把 2026-11-11 新确立的结论写进 RAG 账本。

用 subprocess 传 list 而不是 shell 命令行：之前用 shell 时
「③」后面的中文被吞掉过（facts.jsonl 里出现半句），因为中文标点在 shell 里有特殊语义风险。
"""
import subprocess
import sys

PY = r'G:/Python310/python.exe'
RAG = r'G:/_setup/rag/rag.py'

ITEMS = [
    dict(
        topic='【定稿】旁白同档位同长度是最优解，不要在档位内再分长短',
        concl='旁白三档（inner 0.51 / bound 1.135 / clause 1.695，skill §18.34 三方盲标 60 条，'
              'Kappa 0.841、全一致 85%）定完后，dur 应**恒等于档位 median**。'
              '回测证据：直接用 median，MAE 0.292s / R² 0.480；再加 R3（句子进度）增益为零'
              '（log(span) 对 log(gap/base) 残差回归 beta=0.204、r²=0.048）；'
              'AUC(bound>inner)=0.840、AUC(clause>bound)=0.738。⇒ 中位即最优估计，抖动只会偏离。'
              '需求 19-0 的「同一句里每个停顿不一样长」依据是「夏尔这个角色的情绪与语言自然度」，'
              '例句 Yes./No./Well 全是对白，**不适用于旁白**。'
              '实测 120 条旁白标注里 34/37 个多边界句出现同档重复值，这是正确的。'
              '曾错两次：①套对白尺度（均值 0.35s=标准 30%）②改七档仍套对白分类（旁白没有 drop/beat）'
              '③在 bound 内分 1.05/1.15/1.25 并用 ±0.03 找空位（把 128.6s 抬到 132.1s，纯噪声）。',
        ev='skill dots-tts-dubbing §18.34；REQUIREMENTS 19-0；_pause_vote/p_lead_v2_b0.jsonl；'
           'apply_pause_shape.py 已加废弃守卫；audit.py narr_tier_median',
        tags='停顿,旁白,三档,抖动,返工,定稿'),
    dict(
        topic='改任何常量前先查历史日志：代码里的旧值可能是一次刻意的取舍',
        concl='本轮实例：账本写「峰值 ≤ −1dBFS」，代码 ch123_clean.py 是 CEIL=0.985（−0.13dBFS），'
              '看起来是漏改。但 2026-10-19 日志显示 0.985 是刻意的：0.891 时 59 条跨度 0.63dB，'
              '0.985 时跨度 1.97dB，且 L083/L087 被压低 1.9dB（两批不是同一组音频，不能推因果）。'
              '正确做法是先量影响面：本批 955 条「峰值 > 0.891」只有 3 条'
              '（c2_0317 −0.1 / c3_0787 −0.7 / c2_0498 −0.8 dBFS，最大回退 0.9dB），'
              '且全在 p95 之外 ⇒ 条间跨度 p95−p5 不变（仍 0.32dB），3 条本身也违反红线。⇒ 才敢改。'
              '规则：grep memory/*.md 里这个值 + 文件名 → 有记录且是取舍就先量影响面；没记录再按账本改。'
              '仓库不是 git repo（fatal: not a git repository），历史只能靠日志查。',
        ev='memory/2026-10-19.md 第 362/494/519 行；DECISIONS.md 同名条；955 条峰值实测',
        tags='流程,常量,返工,峰值,定稿'),
    dict(
        topic='audit.py：把反复栽倒的失效模式变成可自动检查的脚本',
        concl='一天内同类问题栽 4 次后建的静态检查器（G:/_setup/audit.py，13 项，退出码非 0 即有 FAIL）。'
              '覆盖六类失效模式：A 两把尺子（span_physical 判 >96dB 物理不可能 / span_single_source 判是否 import 同一实现）'
              'B 声明与实现脱节（dead_params 用 AST 取真实 dest，避免 --in→a.inp 这类别名假阳性；'
              'no_stretch_segments 用 AST 只认真实调用，避免 docstring 误报；peak_ceil / texts_hardcode / wpm_scale / dialog_cap）'
              'C 陈旧产物（stale_artifacts 比对产物与脚本 mtime）'
              'D 分类错但数值对（narr_tier_median 判 dur 必须等于档位 median；tiers_track 判旁白不许出现 drop/beat；'
              'expr_coverage 判 _punct_expr.json 是否真覆盖本书编号）'
              'E 噪声伪造信号（shape_script_deprecated）。'
              '★ 检查器自己也会假阳性：首轮 4 个 FAIL 里 2 个是正则误报，已改 AST。'
              '看到 FAIL 先核实再改代码，不能照单全改。',
        ev='G:/_setup/audit.py；首轮 PASS 8/FAIL 4 → 校准后 PASS 12/WARN 1/FAIL 1',
        tags='流程,审计,失效模式,工具,定稿'),
]


def main():
    for it in ITEMS:
        cmd = [PY, RAG, 'up',
               '-t', it['topic'],
               '-c', it['concl'],
               '-e', it['ev'],
               '-s', '定稿',
               '--tags', it['tags']]
        r = subprocess.run(cmd, cwd=r'G:/_setup/rag',
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        ok = r.returncode == 0
        print('%s %s' % ('OK ' if ok else 'ERR', it['topic'][:40]))
        if not ok:
            print('   ', (r.stdout or '')[-300:], (r.stderr or '')[-300:])
    r = subprocess.run([PY, RAG, 'index'], cwd=r'G:/_setup/rag',
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    print((r.stdout or '')[-200:])


if __name__ == '__main__':
    sys.exit(main())
