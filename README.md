# MintReader 配音工程（The Castle of the King）

英语阅读器的 TTS 配音生产线：955 条音频 = 旁白 716 + 对白 239。
本仓库只放**能复现结论的代码、判据和台账**，音频与模型不进（见文末）。

## 一分钟看懂

```
台词台账 → 参考音频 → 生成 → 七闸判据 → 择优 → 归一化回填 → 试听页
_dlg_plan_v2.jsonl  _ref9/   _regen9.py  dialog_gate.py  _merge9.py  _deliver.py  _build_*_page.py
                                           _align_gate.py（吞字/覆盖率）
```

## 核心脚本（按链路顺序）

| 环节 | 脚本 | 说明 |
|---|---|---|
| 台账 | `_dlg_plan_v2.jsonl` | 239 条对白：id / who / emo / voice / text / path |
| 参考拼接 | `_build_ref9.py` | 按角色×情绪拼 ≥9s 参考，产物 `_ref9/<Who>_<emo>.wav`，索引 `_ref9/_index_srt.json` |
| 参考体检 | `_ref_text_audit.py` | **必跑**。faster-whisper 逐组核对「音频里到底说了什么」，与标注文本的覆盖率 <0.75 判不可用 |
| 单条生成 | `_regen9.py` | `--ids c1_0002 --seeds 42 --out <dir>`；`--ref` / `--ref-text` / `--no-ref-text` / `--strip-end-punct` |
| 批量生成 | `_campaign9.py` | 413 任务（emo + role 双版） |
| 极短句 | `_regen_short.py` | 1~2 个词必须用载体短语：生成 `"<目标> That's all."` 再按 forced_align 切点 |
| 七闸判据 | `dialog_gate.py` | 声学 / 声纹 / 情绪 / 句内一致 / 档内一致 / 自然度 / 音色归属。需 `PYTHONPATH="G:/_setup;G:/_setup/emo_bench"` |
| 短句判据 | `_short_gate.py` | 声纹/情绪不可测时改判内容/电平/静音/自然度 |
| 吞字检测 | `_align_gate.py` | wav2vec2-960h 贪心解码 + forced_align，**无语言模型**（带 LM 的 ASR 会把吞掉的音补回来） |
| 择优 | `_merge9.py` / `_pick52.py` | 三选一必须含 live 作守门员，新候选要严格好 0.05 才替换 |
| 回填 | `_deliver.py` | `norm24()` 把 voiced RMS 归一到 −24±0.1 dBFS |
| 后处理 | `_post_fix.py` | **先剪后填**：剪掉句内 ≥0.65s 停顿到 0.38s，再把全零段填自身底噪 |
| 链路自检 | `_selftest.py` | 11 项：指标基座 / 吞字召回+误报 / 回环覆盖率 / 重生成+不回写+归一化 / 模板覆盖 / 不劣化 / 情绪识别 |
| 试听页 | `_build_listen_page.py` 等 | 数据驱动 HTML，可 A/B/C/D 并排试听 |

## 常用命令

```bash
# 链路自检（11 项，约 3 分钟）
G:/Python310/python.exe -u _selftest.py --reuse

# 单条重生成
G:/Python310/python.exe -u _regen9.py --ids c1_0002 --seeds 42 --out G:/_setup/_regen/xxx

# 吞字/覆盖率检测（整个目录）
G:/Python310/python.exe -u _align_gate.py --dir _sweep/xxx --plan-text --out _align_xxx.json

# 情绪与声纹闸（单条）
PYTHONPATH="G:/_setup;G:/_setup/emo_bench" G:/Python310/python.exe -u dialog_gate.py \
  --wav _audio_ch123/out/c2_0246.wav --who Charles --emo 紧张 \
  --lib G:/_setup/_emo_refs_v2.json --bg-map "@G:/_setup/_bg_map_v2.json" --out _g.json
```

## 铁律（每条都返工过，改代码前先看 `DECISIONS.md`）

- tempo 硬夹 **0.70~1.00**；声纹 **≥0.65**；voiced RMS **−24 dBFS 且跨度 ≤1dB**；不许拆句、不许吞字
- 参考音频的 **reference-text 必须与音频内容一致**。文本比音频长 → 多出的词会渗到正文开头（lead）；文本比音频短 → 反过来吞字。不确定就不传（`--no-ref-text`）
- **参考电平对齐原参考自己**，不要按成品的 −24 dBFS 拉（会削顶，模型直接暴走）
- 段间不能填数字零（`np.zeros`），要填 −72 dBFS 极低噪声，否则 DiT cache 分配失败
- 连续量不许直接投票，必须先分档；三路标注不许取平均
- 短句（≤3 词）保留句号 `‘No.’` 会产出 0.16s 空文件，必须去掉句末标点 + 载体短语
- 候选音频跑闸**不能读缓存**，不在 `_audio_ch123/out` 下就现测；回填后必须刷 `_nat_*.json`

## 当前状态（2026-11-24）

| | 数字 |
|---|---|
| 旁白 716 | PASS 712（99.4%，已验收，别动） |
| 对白 239 | v50 闸门：PASS 150 / MANUAL 81 / REGEN 8（切默认库前需按新库重标情绪阈值） |
| 已知缺陷 | 67 条参考的 ref_text 与音频错配（Joseph 53 / Charles_angry 12 / Thomas 2），待批量重生成 |
| 极短句 | 7 条已用载体方案重做回填，7 条待试听，`c1_0034`（Thomas_begging 参考是字幕组水印）待换参考 |

## 没进仓库的东西

`.gitignore` 是**白名单**：默认全忽略，只放行 `*.py` / `*.md` / `*.jsonl` / 少量小 json。

| 排除项 | 原因 |
|---|---|
| `_audio_ch123/` 等全部音频、`films/` 电影切片 | 561MB+，且电影音轨有版权 |
| `models/`（24GB）、`datasets/`（17GB） | 模型与语料，走本地 |
| `asr_venv/`、`wpt_venv/`、`__pycache__` | 环境与缓存 |
| 575 个 `_*/` 实验产物目录 | 中间结果，脚本可重建 |
| `*.html` 试听页 | 内嵌 base64 音频，单文件可达 8MB |
| `.secrets/` | 网关 key（`_llm_key.py` 读环境变量或该文件） |

新增脚本放根目录即可自动被跟踪；新增子模块要在 `.gitignore` 的「自研子模块」段加白。

## 本机环境

- 解释器只用 `G:/Python310/python.exe`（唯一同时有 onnxruntime + torch + parselmouth）
- RX580 8GB：Vulkan 必须 `--threads 2` + `mem_saver=true`，否则 OOM
- 不往 C 盘写任何东西
