# -*- coding: utf-8 -*-
"""sync_boot —— 把「当前状态」自动刷进常驻记忆文件（SessionStart hook 的等价物）。

## 为什么必须这么做

社区最好用的机制是 `SessionStart` hook：**每次会话开始 + 每次上下文压缩之后**都重新注入
一段上下文（"the only mechanism that automatically re-injects context when compaction drops it"）。

2026-11-11 17:57 起，本机**已有真 SessionStart hook**（当时三次核实的是「没有」；
后来实测 settings.json 支持 hooks 键，已配上）：
`hooks.SessionStart` → `~/.workbuddy/hooks/session-context.sh`，
matcher `startup|resume|compact|clear`，输出直进上下文。
⇒ 本文件现在是**第二层保险**（hook 被关 / 换环境 / 被绕过时仍生效），不是唯一手段。

所以只剩两个真正每次都会进 context 的位置：
  1. `~/.workbuddy/MEMORY.md`        用户级，上限 4000 字符
  2. 项目 `.workbuddy/memory/MEMORY.md` 项目级，上限 3000 字符

⇒ **把状态直接做进这两个文件**，压缩后注入的就自带最新状态，不需要「我记得去跑 resume.py」。
这是把「prompt 靠自觉」换成「文件本身承载」，也就是社区说的 plumbing。

## 机制

MEMORY.md 里留一段标记区：

    <!-- AUTO:BOOT 由 sync_boot.py 生成，勿手改 -->
    ...
    <!-- /AUTO:BOOT -->

本脚本每次读 STATE.md + audit.py，重算这段并原地替换。手写部分一律不动。

## 什么时候跑

- `resume.py` 开场自动调
- **每改完 STATE.md 就跑一次**（改 STATE 不刷新 = 下次压缩注入旧状态）

用法：
  G:/Python310/python.exe sync_boot.py          # 刷新
  G:/Python310/python.exe sync_boot.py --check  # 只检查是否过期
"""
import argparse
import io
import os
import re
import subprocess
import sys

SETUP = r'G:/_setup'
# 2026-11-13 16:4x：AUTO:BOOT 段改写到 F:/Charles（全项目工作区）。
# 原值 = C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/.workbuddy/memory/MEMORY.md
# 原因：那个目录 11-13 收窄成「只做旁白」，而本段内容是全项目进度（含对白/标注层），
# 写进去会把对白链路重新灌进旁白会话（用户 11-13 报障的根因之一）。
MEM_PROJ = r'F:/Charles/.workbuddy/memory/MEMORY.md'
STATE = os.path.join(SETUP, 'STATE.md')

BEGIN = '<!-- AUTO:BOOT 由 sync_boot.py 生成，勿手改 -->'
END = '<!-- /AUTO:BOOT -->'

CAP = 3000          # 项目级 MEMORY.md 字符上限


def read(p):
    try:
        return io.open(p, encoding='utf-8').read()
    except Exception:
        return ''


def audit_fails():
    """跑 audit.py，只取 FAIL/ERROR 行。它自己会跑 15 项检查，~1 秒。"""
    try:
        r = subprocess.run([sys.executable, os.path.join(SETUP, 'audit.py')],
                           cwd=SETUP, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=120)
        bad = [ln.strip() for ln in (r.stdout or '').splitlines()
               if ln.startswith('✗') or ln.startswith('E ')]
        return bad
    except Exception:
        return []


def clean(s):
    """去掉 markdown 标记 —— 摘要区是给模型读的，粗体和反引号只会占字符。"""
    s = s.replace('**', '').replace('`', '').replace('~~', '')
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)     # 链接留文字
    return s.strip()


def parse_state(text):
    """从 STATE.md 抽两样：下一步第一条未完成 / 最近完成。找不到就返回 None，不猜。"""
    first_open = None
    done = []
    grp = ''
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith('**') and s.endswith('**') and len(s) < 40:
            grp = clean(s).split('（')[0][:8]        # 只留「判据层」这种短名
            continue
        m = re.match(r'^(\d+)\.\s*(☐|◐|✅)\s*(.{0,110})', s)
        if not m:
            continue
        txt = clean(m.group(3))
        if m.group(2) in ('☐', '◐') and first_open is None:
            first_open = (grp, m.group(1), m.group(2), txt)
        elif m.group(2) == '✅':
            done.append(txt)
    return first_open, done[-3:]


def build_block(state_text):
    first_open, done = parse_state(state_text)
    out = [BEGIN, '> 本段由 `sync_boot.py` 从 STATE.md + audit.py 自动生成，别手改。',
           '> 压缩后它会跟着 MEMORY.md 一起注入 —— 这是本环境里唯一能替代 SessionStart hook 的办法。']
    if first_open:
        grp, no, mark, txt = first_open
        # 只保留第一句，避免把整段解释塞进来
        txt = re.split(r'[，。；：]', txt)[0][:70]
        out.append('')
        out.append('**下一步（第 %s 项%s%s）**：%s' % (no, mark, ('／' + grp) if grp else '', txt))
    for d in done:
        out.append('- 刚完成：' + re.split(r'[，。]', d)[0][:60])
    fails = audit_fails()
    if fails:
        out.append('')
        out.append('**audit 未通过（先修再动手）**：')
        for f in fails[:4]:
            out.append('  ' + f.lstrip('✗ ').strip()[:100])
    out.append(END)
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只检查，不写')
    a = ap.parse_args()

    mem = read(MEM_PROJ)
    if not mem:
        print('读不到 %s' % MEM_PROJ)
        return 1
    state = read(STATE)
    if not state:
        print('读不到 STATE.md')
        return 1

    block = build_block(state)
    if BEGIN in mem and END in mem:
        new = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END), block, mem, flags=re.S)
    else:
        # 首次：插在第一个 `## ` 之前（即紧跟在标题/引言之后）
        m = re.search(r'^## ', mem, re.M)
        pos = m.start() if m else len(mem)
        new = mem[:pos] + block + '\n\n' + mem[pos:]

    n = len(new)
    stale = (block not in mem)
    if a.check:
        print('AUTO:BOOT 段%s；MEMORY.md %d/%d 字符'
              % ('已过期（需 sync）' if stale else '是最新的', n, CAP))
        return 0 if not stale else 2

    if n > CAP:
        print('★ 写入后 %d 字符 > 上限 %d，会被截断 —— 先精简 MEMORY.md 手写部分' % (n, CAP))
        return 1

    io.open(MEM_PROJ, 'w', encoding='utf-8').write(new)
    print('已刷新 AUTO:BOOT（MEMORY.md %d/%d 字符）' % (n, CAP))
    print(block)
    return 0


if __name__ == '__main__':
    sys.exit(main())
