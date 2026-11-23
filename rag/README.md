# 项目外部记忆（本地 RAG）

MintReader / TTS 项目的长期记忆层。**离线、零 API、数据不出本机。**

- 索引源：`memory/*.md`（27 份日志）、`G:/_setup/*.md`（50+ 报告）、`emo_bench/*.md`、两个核心 Skill
- 规模：2836 块 / 77 文件 / 库 10.5MB
- 词法：SQLite FTS5 + jieba（多层级 AND 融合）
- 语义：bge-small-zh-v1.5 ONNX 512 维 + 加权 RRF
- 账本：`facts.jsonl`，54 条硬结论，检索时**优先于原文片段**

## 用法

```bash
PY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
cd G:/_setup/rag

"$PY" rag.py search "副词重音 rel_z"      # 检索（账本 + 原文）
"$PY" rag.py get 1650                     # 取某块全文
"$PY" rag.py up -t 主题 -c 结论 -e 证据    # 记一条结论 + 刷新索引
"$PY" rag.py index                        # 增量索引
"$PY" rag.py stats                        # 状态
"$PY" eval_recall.py 5                    # 召回率回归
```

自动化规则见 `~/.workbuddy/skills/project-rag/SKILL.md`。

## 基线

| 口径 | top5 召回 |
|---|---|
| 账本 + 原文（真实使用） | 25/25 = 100% |
| 仅原文片段 | 22/25 = 88% |

改了切块/分词/融合逻辑后必须复跑，低于基线即退步。

## 踩过的坑（别再犯）

1. **中文 bigram 分词是错的** —— 词边界产生"数怎/么从"等零语义 token，IDF 越高越噪声。必须用 jieba。
2. **英文标识符要先整体抽出** —— jieba 会把 `stretch_segments` 拆成 `stretch`+`segments`。
3. **不要跨标题合并短块** —— 多主题混一块会稀释精确匹配信号。
4. **结论文件必须加权** —— 否则长日志靠篇幅把 `MEMORY.md` 的结论挤出前五。
5. **只取"第一个成功的 AND"太脆** —— 砍词顺序一错全丢，要多层级融合。
