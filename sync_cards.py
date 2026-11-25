# -*- coding: utf-8 -*-
"""sync_cards —— 把 G:/_setup 的正文卡压成工作区根的「注入卡」。

## 为什么需要这个

SessionStart hook（`~/.workbuddy/hooks/session-context.sh`）只读**工作区根**的
`HANDOFF.md` / `STATE.md` / `DECISIONS.md`。而本项目正文全在 `G:/_setup`，
工作区根一张卡也没有 ⇒ hook 每次只能注入 MEMORY.md 前 40 行，
**「现在在哪」和「哪些路已走死」这两样照样丢**。

（MEMORY.md 里的 AUTO:BOOT 段只解决「下一步」一句，不解决否决清单与交付物台账。）

## 本脚本干什么

只生成两张**派生卡**，不复制正文，只「摘要 + 指针」：

| 根文件 | 来源 | 内容 |
|---|---|---|
| `STATE.md` | `G:/_setup/STATE.md` | 更新时间 / 项目 / 交付物 / 待办状态计数 + 未完成项 / 下一步顺序 / 标注进度 |
| `DECISIONS.md` | `G:/_setup/DECISIONS.md` | 全部 `## ` 标题（hook 只取标题，正文按需 Read） |

`HANDOFF.md` 与 `CODEBUDDY.md` 是**判断不是派生**（下一步第一件事、红线、边界），
手写维护，本脚本不碰。

## 何时跑

- `resume.py` 开场自动调（已接入）
- 每次手改 `G:/_setup/STATE.md` 或 `DECISIONS.md` 之后跑一次

用法：
  G:/Python310/python.exe G:/_setup/sync_cards.py           # 生成/刷新
  G:/Python310/python.exe G:/_setup/sync_cards.py --check   # 只看是否过期
"""
import argparse
import io
import os
import re
import sys
import datetime

SETUP = r'G:/_setup'
# 2026-11-13 01:5x：卡片落盘从 `C:/Users/86178/WorkBuddy/2026-10-05-00-50-22` 迁到主工作区
# `F:/Charles`。旧目录不再写入（用户明确要求：那里 Handoff 已被多个项目混用）。
PROJ = r'F:/Charles'

STATE_SRC = os.path.join(SETUP, 'STATE.md')
DECI_SRC = os.path.join(SETUP, 'DECISIONS.md')
CARD_STATE = os.path.join(PROJ, 'STATE.md')
CARD_DECI = os.path.join(PROJ, 'DECISIONS.md')

MAX_PENDING = 6      # 未完成待办最多列几条
MAX_TODO_CHARS = 78  # 每条截断长度


def read(p):
    try:
        return io.open(p, encoding='utf-8', errors='replace').read()
    except Exception:
        return ''


def write(p, s):
    io.open(p, 'w', encoding='utf-8', newline='\n').write(s)


def grab(pattern, text, default=''):
    m = re.search(pattern, text, re.M)
    return m.group(1).strip() if m else default


def section(text, head):
    """取 `head` 标题之后、下一个同级或更高级标题之前的内容行。"""
    lines = text.splitlines()
    out, on = [], False
    level = len(head) - len(head.lstrip('#'))
    for ln in lines:
        s = ln.strip()
        if not on:
            if s.startswith(head):
                on = True
            continue
        if s.startswith('#') and (len(s) - len(s.lstrip('#'))) <= level:
            break
        out.append(ln)
    return out


def parse_todos(text):
    """抽待办清单：1. ✅ ... / 12b. ☐ ..."""
    items = []
    for ln in text.splitlines():
        m = re.match(r'^\s*(\d+[a-z]?)\.\s*(✅|◐|☐)\s*(.+)$', ln.strip())
        if m:
            items.append((m.group(1), m.group(2), m.group(3).strip()))
    return items


def clip(s, n=MAX_TODO_CHARS):
    s = s.replace('**', '').replace('`', '')
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) <= n else s[:n - 1] + '…'


def build_state_card(state_text):
    upd = grab(r'^>\s*更新时间[:：]\s*(.+)$', state_text, '(未标注)')
    proj = grab(r'^##\s*项目[:：]\s*(.+)$', state_text, '(未找到 `## 项目：` 行)')

    deliv = [ln.strip() for ln in section(state_text, '### 交付物') if ln.strip()]
    deliv = deliv[:4]

    todos = parse_todos(state_text)
    done = [t for t in todos if t[1] == '✅']
    pending = [t for t in todos if t[1] in ('◐', '☐')]

    nxt = ''
    for ln in section(state_text, '### 下一步'):
        if ln.strip() and not ln.strip().startswith('#'):
            nxt = ln.strip()
            break

    pause = ''
    for ln in state_text.splitlines():
        if '停顿：' in ln and ('⏳' in ln or '/' in ln):
            pause = clip(ln.strip().lstrip('-').strip(), 100)
            break

    L = ['<!-- AUTO:STATE 由 sync_cards.py 从 G:/_setup/STATE.md 生成，勿手改 -->',
         '# STATE 摘要（正文 %d 行：`G:/_setup/STATE.md`）' % len(state_text.splitlines()),
         '',
         '> ⚠ **本卡可能滞后：现状以 `F:/Charles/HANDOFF.md` 为准。**',
        '> 源更新时间：**%s**' % upd,
         '> 卡片生成：%s ｜ 这份只放「现在在哪」，细节一律 Read 正文，别在卡片上推演。' %
         datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
         '',
         '## 项目',
         proj,
         '']
    if deliv:
        L.append('## 交付物（台账原文）')
        L.extend(deliv)
        L.append('')
    if todos:
        L.append('## 待办（共 %d 项：✅%d / ◐%d / ☐%d，按危害排序）'
                 % (len(todos), len(done),
                    len([t for t in pending if t[1] == '◐']),
                    len([t for t in pending if t[1] == '☐'])))
        L.append('未完成的（做完一项请改 `G:/_setup/STATE.md` 再跑本脚本，别只改对话）：')
        for no, mark, txt in pending[:MAX_PENDING]:
            L.append('- %s %s %s' % (no, mark, clip(txt)))
        rest = len(pending) - MAX_PENDING
        if rest > 0:
            L.append('- … 另 %d 项见正文待办清单' % rest)
        L.append('')
    if nxt:
        L.append('## 下一步顺序')
        L.append(nxt[:200])
        L.append('')
    if pause:
        L.append('## 标注进度')
        L.append(pause)
        L.append('')
    L.append('<!-- /AUTO:STATE -->')
    return '\n'.join(L) + '\n'


def build_deci_card(deci_text):
    heads = [ln[3:].strip() for ln in deci_text.splitlines() if ln.startswith('## ')]
    L = ['<!-- AUTO:DECISIONS 由 sync_cards.py 从 G:/_setup/DECISIONS.md 生成，勿手改 -->',
         '<!-- 本文件只放标题。hook 只取 `## ` 标题注入，正文（%d 行）按需 Read。 -->'
         % len(deci_text.splitlines()),
         '# 已否决 / 已判定走不通的做法（%d 条，按时间倒序在原文件）' % len(heads),
         '> 压缩后这份清单会随 hook 自动进上下文。**不许在已被否决的方案上重新推演。**',
         '> 需要理由与证据：`G:/_setup/DECISIONS.md` 对应小节。',
         '']
    for h in heads:
        L.append('## ' + h)
    return '\n'.join(L) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只检查是否过期')
    a = ap.parse_args()

    if not os.path.isdir(PROJ):
        print('工作区不存在：%s' % PROJ)
        return 1

    state_text = read(STATE_SRC)
    deci_text = read(DECI_SRC)
    if not state_text or not deci_text:
        print('源文件缺失：STATE=%d字节 DECISIONS=%d字节' % (len(state_text), len(deci_text)))
        return 1

    cards = [(CARD_STATE, build_state_card(state_text)),
             (CARD_DECI, build_deci_card(deci_text))]

    stale = []
    for path, body in cards:
        old = read(path)
        # 去掉「卡片生成」时间行再比，避免每次都判过期
        norm = lambda s: re.sub(r'> 卡片生成：[^\n]*', '', s)
        if norm(old) != norm(body):
            stale.append(os.path.basename(path))

    if a.check:
        print('卡片%s：%s' % ('已过期（需 sync）' if stale else '是最新的',
                            ', '.join(stale) if stale else '全部最新'))
        return 0 if not stale else 2

    for path, body in cards:
        write(path, body)
        print('写入 %s（%d 行）' % (path, body.count('\n')))
    print('源：STATE %d 行 / DECISIONS %d 行'
          % (len(state_text.splitlines()), len(deci_text.splitlines())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
