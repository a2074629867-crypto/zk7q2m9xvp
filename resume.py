# -*- coding: utf-8 -*-
"""项目连续性入口 —— 每次会话开场跑一次，把「现在的状态」强行塞进上下文。

为什么要这个脚本（社区实证，不是我想的）：
  · Claude Code 的 MEMORY.md 有读取上限，**超出部分下次加载直接丢掉** —— 这就是
    「一压缩就全忘」的机制原因，不是模型不努力。
  · 让 agent「自己去搜项目记忆」**不管用**。Nicolas Micaud 实测 agent 会忽略这条指令，
    所以他的 server 改成主动跑搜索、把结果注入到 agent 开始之前。
    原话：「Prompts are for judgment. Plumbing is for guarantees.」
  ⇒ 所以连续性不能靠「记得去读」，要靠这个脚本一跑就把关键状态打出来。

四类必须活在上下文之外的东西（stackness / Claude Code 文档）：
  1. Rules      → MEMORY.md（精简，只放铁律）
  2. Plan       → STATE.md（现在在哪、下一步）
  3. Decisions  → DECISIONS.md（**否决了什么 + 为什么**，这是压缩最常丢的）
  4. Plumbing   → 本脚本（不依赖模型自觉）

用法：
  python resume.py            # 默认：STATE 全文 + DECISIONS 索引 + 最近日志
  python resume.py --full     # 连 DECISIONS 全文一起打
  python resume.py --quiet    # 只打 STATE（给管道用）
"""
import argparse
import glob
import os
import sys

SETUP = r'G:/_setup'
MEM = r'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/.workbuddy/memory'


def head(path, n=None):
    if not os.path.exists(path):
        return '(缺失: %s)' % path
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    return '\n'.join(lines[:n] if n else lines)


def decisions_index(path):
    """只取 ## 标题 + 首行，让我知道有哪些结论，正文按需读。"""
    if not os.path.exists(path):
        return '(缺失: %s)' % path
    out = []
    for ln in open(path, encoding='utf-8', errors='replace').read().splitlines():
        if ln.startswith('## '):
            out.append('  ' + ln[3:])
    return '\n'.join(out)


def latest_log():
    files = sorted(glob.glob(os.path.join(MEM, '20*.md')))
    if not files:
        return '(无日志)'
    p = files[-1]
    lines = open(p, encoding='utf-8', errors='replace').read().splitlines()
    tail = [l for l in lines if l.strip()][-18:]
    return '【%s 尾部】\n' % os.path.basename(p) + '\n'.join(tail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    print('=' * 70)
    print('项目连续性注入 —— %s' % os.path.basename(os.getcwd()))
    print('=' * 70)
    print()
    print('【1. 当前状态 STATE.md】')
    print(head(os.path.join(SETUP, 'STATE.md')))
    print()

    if a.quiet:
        return

    print('【2. 已否决的做法 DECISIONS.md —— 别重复踩】')
    print(decisions_index(os.path.join(SETUP, 'DECISIONS.md')))
    if a.full:
        print()
        print(head(os.path.join(SETUP, 'DECISIONS.md')))
    else:
        print('  （正文用 --full 或直接 Read DECISIONS.md）')
    print()

    print('【3. 最近工作日志】')
    print(latest_log())
    print()

    print('【4. 细节查 RAG，别凭记忆重推】')
    print('  cd G:/_setup/rag && G:/Python310/python.exe rag.py search "关键词"')
    print('  写回：rag.py up -t 主题 -c 结论 -e 证据')
    print()

    # ★ 第 5 段：自动跑失效模式检查。
    #   为什么必须挂在这里而不是「记得去跑」：社区实证 agent 会忽略「去搜索记忆」类指令
    #   （「Prompts are for judgment. Plumbing is for guarantees.」）。
    #   audit.py 抓的是今天一天栽 4 次的那几类：两把尺子 / 声明与实现脱节 /
    #   陈旧产物 / 分类错但数值对 / 用噪声伪造信号。
    # ★ 第 5 段：先刷新 AUTO:BOOT，再跑失效模式检查。
    #   为什么要刷新：本机已在 2026-11-11 17:57 配上真 SessionStart hook
    #   （settings.json 的 hooks.SessionStart → ~/.workbuddy/hooks/session-context.sh），
    #   下面是第二层保险：hook 被关掉或被新环境绕过时，注入的 MEMORY 仍带最新状态。
    #   （原注释写的「本环境没有 hook」已于 2026-11-11 19:3x 核实无效，已改。）
    #   所以把「现在在哪 / 下一步 / 未修的坑」直接做进
    #   项目 MEMORY.md 的 AUTO 段 —— 压缩后注入的就自带最新状态，
    #   不依赖「我记得去跑 resume.py」。
    #   社区原话：「Prompts are for judgment. Plumbing is for guarantees.」
    print('【5. 刷新 AUTO:BOOT（把状态写进常驻记忆）】')
    try:
        import subprocess
        r0 = subprocess.run([sys.executable, os.path.join(SETUP, 'sync_boot.py')],
                            cwd=SETUP, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=120)
        line = (r0.stdout or '').strip().splitlines()
        print('  ' + (line[0] if line else '(无输出)'))
    except Exception as e:
        print('  [warn] sync_boot 跑不了：%s' % e)
    print()

    # ★ 第 5b 段：刷新「工作区根」的注入卡。
    #   为什么要：SessionStart hook 只读工作区根的 HANDOFF/STATE/DECISIONS，
    #   而本项目正文全在 G:/_setup。不刷这两张卡，hook 每次只能注入 MEMORY.md，
    #   「现在在哪」和「否决清单」照样丢。
    print('【5b. 刷新工作区根的注入卡 STATE.md / DECISIONS.md】')
    try:
        import subprocess
        r0b = subprocess.run([sys.executable, os.path.join(SETUP, 'sync_cards.py')],
                             cwd=SETUP, capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=60)
        for ln in (r0b.stdout or '').strip().splitlines()[:2]:
            print('  ' + ln)
    except Exception as e:
        print('  [warn] sync_cards 跑不了：%s' % e)
    print()

    print('【6. 失效模式检查 audit.py（自动跑，别跳过）】')
    try:
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(SETUP, 'audit.py')],
                           cwd=SETUP, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=120)
        out = (r.stdout or '').strip().splitlines()
        # 只打结论行与失败行，全文用 audit.py 单独看
        for ln in out:
            if ln.startswith('✗') or ln.startswith('!') or ln.startswith('ERROR'):
                print('  ' + ln)
        summary = [ln for ln in out if ln.startswith('PASS ')]
        print('  ' + (summary[-1] if summary else '（检查器无输出）'))
        if r.returncode != 0:
            print('  ⇒ 有 FAIL，先修完再动手。全文：python G:/_setup/audit.py')
    except Exception as e:
        print('  [warn] audit.py 跑不了：%s' % e)
    print()


if __name__ == '__main__':
    main()
