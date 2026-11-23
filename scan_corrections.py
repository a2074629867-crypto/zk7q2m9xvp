# -*- coding: utf-8 -*-
"""扫所有 md / 日志，抽出「改口记录」—— 哪些结论被后来的实测推翻或修正过。

为什么需要（用户 2026-11-11 指出）：
  「有些经验没记到 RAG；有些记进 RAG 的是错的（早期版本），后来在 md 文档/日志里
    已经修正，但修正没回写 RAG。结果 RAG 里留错的，正确的只在 md 里。」

所以真值源不是 RAG，是 **md 文档 + 日志的时间线**。本脚本把时间线里的
「改口现场」全部抽出来，形成人工裁决清单。

扫的目录：
  G:/_setup/*.md            （61 个报告/规则文档）
  .workbuddy/memory/*.md    （31 天日志，按日期排序 = 天然时间线）

抽的词：作废 / 推翻 / 撤回 / 纠正 / 改为 / 应为 / 算错 / 不入 / 回滚 / 之前说错 …
排除：目录、纯列表项（避免噪音）

用法：
  python scan_corrections.py              # 按时间轴打印
  python scan_corrections.py --topic 停顿  # 只看某主题
  python scan_corrections.py --out x.md   # 存文件
"""
import argparse
import glob
import os
import re

SETUP = r'G:/_setup'
MEM = r'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/.workbuddy/memory'

# 「改口」信号词。宁可多抓，后面人工筛。
SIG = ['作废', '推翻', '撤回', '纠正', '改口', '算错', '算反', '之前说错', '我说错',
       '改为', '应为', '不是这样', '重来', '回滚', '推翻之前', '错误结论',
       '错在', '实际是', '其实不', '并不成立', '不成立', '别再用', '不要再用']

# 噪音：纯导航行、目录、代码块边框
NOISE = re.compile(r'^\s*[-*|#>`]{0,3}\s*\[?[^\w\u4e00-\u9fff]*$')


def files():
    out = []
    for p in glob.glob(os.path.join(SETUP, '*.md')):
        out.append((os.path.basename(p), p, 'doc'))
    for p in sorted(glob.glob(os.path.join(MEM, '20*.md'))):
        out.append((os.path.basename(p), p, 'log'))
    return out


def scan(path, want=None):
    hits = []
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except Exception:
        return hits
    for i, ln in enumerate(lines):
        s = ln.strip()
        if len(s) < 8 or len(s) > 400:
            continue
        if NOISE.match(s):
            continue
        if not any(k in s for k in SIG):
            continue
        if want and want not in s and want not in '\n'.join(lines[max(0, i - 3):i + 3]):
            continue
        hits.append((i + 1, s))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--topic', default='')
    ap.add_argument('--out', default='')
    ap.add_argument('--max-per-file', type=int, default=8)
    a = ap.parse_args()

    # 排序：doc 在前；log 按文件名（= 日期）升序 → 时间线
    fl = files()
    docs = [f for f in fl if f[2] == 'doc']
    logs = sorted([f for f in fl if f[2] == 'log'], key=lambda x: x[0])

    buf = []
    total = 0
    for group, name in ((docs, '规则/报告文档'), (logs, '日志（时间线升序）')):
        buf.append('')
        buf.append('#' * 70)
        buf.append('# ' + name)
        buf.append('#' * 70)
        for fn, p, kind in group:
            h = scan(p, a.topic or None)
            if not h:
                continue
            total += len(h)
            buf.append('')
            buf.append('## %s  (%d 处)' % (fn, len(h)))
            for ln, s in h[:a.max_per_file]:
                buf.append('  L%-5d %s' % (ln, s[:230]))
            if len(h) > a.max_per_file:
                buf.append('  …还有 %d 处' % (len(h) - a.max_per_file))

    txt = '\n'.join(buf)
    print(txt)
    print()
    print('=' * 70)
    print('合计 %d 处改口记录' % total)
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(txt)
        print('已写入', a.out)


if __name__ == '__main__':
    main()
