# -*- coding: utf-8 -*-
"""preflight —— 动手前的强制注入。不是提示词，是管道。

为什么必须存在（2026-11-11 用户原话）：
  「我们可能已经反复踩坑过很多次，栽倒同一个问题很多次很多次了……
    很多都没有按照我的想法来做。」
  「你看看社区的方法能不能通过其他方式把这些记忆固定住，让 Agent 能记得住我们之前的结论。」

社区实证（Nicolas Micaud / Claude Code 文档 / stackness）：
  · agent **会忽略**「去搜索项目记忆」这类指令
  · MEMORY.md 有读取上限，超出部分下次加载直接丢弃
  · 原话：「Prompts are for judgment. Plumbing is for guarantees.」
  ⇒ 所以不能靠「我记得去查」，要靠一个脚本，一跑就把该看的条款打进上下文。

用法（任务开始前第一件事）：
  python preflight.py pause      # 停顿标注/插停顿
  python preflight.py narr       # 旁白韵律/起伏/闸门
  python preflight.py dialog     # 对白情感/声纹/三闸
  python preflight.py gen        # 生成/重生成/seed/标签
  python preflight.py all        # 全打（输出较长）

设计原则：
  1. 只打**相关**条款，避免又一次全量注入把窗口塞满
  2. 每条都带**出处行号**，方便回查原文
  3. 同时打 DECISIONS 的「已否决」—— 这是压缩最常丢、也最容易重犯的部分
"""
import argparse
import os
import re

REQ = r'G:/_setup/REQUIREMENTS.md'
DEC = r'G:/_setup/DECISIONS.md'
SKILL = r'C:/Users/86178/.workbuddy/skills/dots-tts-dubbing/SKILL.md'

# 每个任务关切的关键词。命中即抽该行 + 上下文。
TOPICS = {
    'pause': {
        'req': ['停顿', 'pause', '逗号', '底噪', '19-', '25a', '25b', '19c', '19d', '句号'],
        'dec': ['停顿', 'pause', '档', '抖动', 'wpm', '底噪'],
        'skill': ['18.24', '18.33', '18.34', '停顿', 'inner', 'bound', 'Kappa'],
    },
    'narr': {
        'req': ['起伏', 'span', 'energy', '带', '27.', '28.', '29.', '30.', '31.', '底噪归一'],
        'dec': ['span', '起伏', '带', '口径', 'F0', '硬切'],
        'skill': ['起伏', 'span', '能量带', '18.1', '18.2'],
    },
    'dialog': {
        'req': ['声纹', '情感', '情绪', 'emo', 'F0', '闸'],
        'dec': ['声纹', '情绪', '单模型', '闸'],
        'skill': ['声纹', '情绪', 'Z-norm', '1-NN', 'emotion2vec'],
    },
    'gen': {
        'req': ['生成', 'seed', '标签', 'tempo', '语速', 'rate', '拆句', 'chunk', '口吃'],
        'dec': ['逐句', 'chunk', '标签', 'tempo', '拆句'],
        'skill': ['生成工作流', 'seed', '标签', 'tempo', 'chunk'],
    },
}


def grab(path, kws, max_hits=40, ctx=1):
    """抽命中行 + 上下文，带行号。跳过代码块边框等噪音。"""
    if not os.path.exists(path):
        return ['(缺失: %s)' % path]
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    out, last = [], -99
    for i, ln in enumerate(lines):
        if not any(k.lower() in ln.lower() for k in kws):
            continue
        if i - last <= ctx:
            continue
        last = i
        seg = lines[max(0, i - ctx):i + ctx + 1]
        for j, s in enumerate(seg):
            if s.strip():
                out.append('  L%-5d %s' % (max(0, i - ctx) + j + 1, s[:220]))
        out.append('')
        if len(out) > max_hits * 3:
            out.append('  …（截断，用 grep 看全文）')
            break
    return out or ['  （无命中）']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('task', nargs='?', default='all',
                    choices=['pause', 'narr', 'dialog', 'gen', 'all'])
    a = ap.parse_args()

    tasks = list(TOPICS) if a.task == 'all' else [a.task]

    print('=' * 74)
    print('PREFLIGHT —— 动手前必读。这些是返工过的条款，不是建议。')
    print('=' * 74)

    for t in tasks:
        cfg = TOPICS[t]
        print()
        print('#' * 74)
        print('#  任务类型：%s' % t.upper())
        print('#' * 74)

        print()
        print('【一、用户要求 REQUIREMENTS.md】')
        for s in grab(REQ, cfg['req'], max_hits=25):
            print(s)

        print()
        print('【二、已否决的做法 DECISIONS.md —— 别重犯】')
        for s in grab(DEC, cfg['dec'], max_hits=20):
            print(s)

        print()
        print('【三、踩坑手册 skill dots-tts-dubbing】')
        for s in grab(SKILL, cfg['skill'], max_hits=15):
            print(s)

    print()
    print('=' * 74)
    print('看完再动手。若本任务要新增判据/阈值，先把依据写进 RAG，再写代码。')
    print('=' * 74)


if __name__ == '__main__':
    main()
