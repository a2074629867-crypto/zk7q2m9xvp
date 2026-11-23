#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""召回率测试：给定问题 + 必须命中的特征串，检查 top-k 是否召回。

两种口径：
  默认      = 真实使用口径（账本 + 原文片段），账本结论含特征串也算命中
  --chunks  = 只看原文片段层（关掉账本），用来评估索引本身

判据是"特征串出现在返回内容里"，与文件路径无关。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# (查询, [任一命中即算对的特征串], 说明)
CASES = [
    ("tempo 最低能拉到多少",            ["0.70", "0.7 倍"],            "语速硬限制"),
    ("为什么 emo 标签没有用",           ["85.06", "净负收益"],          "标签负收益"),
    ("Vulkan 显存不足怎么解决",         ["mem_saver", "threads 2"],     "GPU OOM"),
    ("副词重音的 rel_z 阈值是多少",     ["REL_Z_OK", "+1.47", "1.6"],   "重音判据"),
    ("情绪判据表的 AUC 是多少",         ["0.898", "0.886"],             "情绪判据"),
    ("Charles 的音色从哪里来的",        ["castle_fr_ref"],              "角色音色"),
    ("停顿应该停多久",                  ["0.43", "n=33"],               "停顿标定"),
    ("电平怎么统一",                    ["-24", "−24"],                 "电平"),
    ("极短句生成失败怎么办",            ["I don't know", "In a flat"],  "极短句"),
    ("为什么禁用 stretch_segments",     ["NISQA", "4.18"],              "分段拉伸"),
    ("底噪要铺到多少",                  ["-58", "−58"],                 "底噪"),
    ("为什么不能拆句",                  ["159", "304"],                 "拆句毁弧线"),
    ("声纹模型哪个最准",                ["5/8"],                        "声纹模型"),
    ("兴奋情绪怎么救回来",              ["Expresso"],                   "兴奋救回"),
    ("起伏闸门怎么判太平",              ["FIX_LOW", "p05"],             "起伏闸门"),
    ("Z-norm 为什么要做",               ["Z-norm", "z-norm", "znorm"],  "1-NN 归一"),
    ("底噪归一化为什么必须做",          ["-56", "−56"],                 "底噪归一"),
    ("音节数怎么算",                    ["cmudict"],                    "cmudict"),
    ("问号停顿多长",                    ["0.24"],                       "问号脏值"),
    ("交叉验证的零分布对照是什么",      ["零分布"],                     "方法论"),
    ("哪种音色适合演委屈",              ["C_soft", "1-A", "0.779"],     "委屈判据"),
    ("标签是第一步还是最后一步",        ["最后手段", "第 3 遍"],        "工作流顺序"),
    ("做拉伸会不会毁音色",              ["0.85", "0.763"],              "拉伸边界"),
    ("底噪为什么不能用数字零",          ["-199", "−199"],               "静音段"),
    ("怎么防止段落变人",                ["0.55", "换人"],               "段间声纹"),
]


def run(q, k, facts):
    cmd = [PY, os.path.join(HERE, "rag.py"), "search", q, "-k", str(k), "--json"]
    if not facts:
        cmd.append("--no-facts")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=HERE)
    if r.returncode != 0:
        return [], [], r.stderr
    data = json.loads(r.stdout)
    return data.get("facts", []), data.get("chunks", []), ""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    k = int(args[0]) if args else 5
    use_facts = "--chunks" not in sys.argv
    ok = 0
    fails = []
    for i, (q, needles, note) in enumerate(CASES, 1):
        fs, chunks, err = run(q, k, use_facts)
        if err:
            print(f"{i:2d}. x {note}: 检索报错 {err[:70]}")
            fails.append(note)
            continue
        src, rank = None, None
        for pos, r in enumerate(fs):
            if any(n in r["conclusion"] for n in needles):
                src, rank = "账本", pos + 1
                break
        if not src:
            for pos, ch in enumerate(chunks[:k]):
                if any(n in ch["text"] for n in needles):
                    src, rank = "片段", pos + 1
                    break
        if src:
            ok += 1
            print(f"{i:2d}. ok {note:14s} {src}@{rank}  「{q}」")
        else:
            got = os.path.basename(chunks[0]["path"]) if chunks else "-"
            print(f"{i:2d}. -- {note:14s} 未命中  「{q}」(top1={got})")
            fails.append(note)
    mode = "账本+片段" if use_facts else "仅片段"
    print(f"\n召回率[{mode}] top{k}: {ok}/{len(CASES)} = {ok/len(CASES)*100:.0f}%")
    if fails:
        print("未命中：" + ", ".join(fails))


if __name__ == "__main__":
    main()
