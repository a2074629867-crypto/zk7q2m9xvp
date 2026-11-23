# MEMORY.md 归档（2026-11-07 精简前的完整版）

> 精简后的 MEMORY.md 只留索引与红线；详细论证 / 阈值 / 踩坑过程保留在此。
> 本文是精简前逐节导出的，保证细节不从 RAG 里消失。

[MEMORY.md] MintReader / TTS
# MintReader / TTS

> **★★★ 外部记忆（先检索，别凭记忆重推）**
> - **RAG**：`G:/_setup/rag/` — `cd G:/_setup/rag && "$PY" rag.py search "关键词"`；写回 `rag.py up -t 主题 -c 结论 -e 证据`。
>   2886 块 / 79 文件 / **80 条硬结论账本**。真实口径 top5 召回 **25/25=100%**。规则见 skill `project-rag`。
>   **账本优先于原文片段**——口语句式（"为什么标签没用"）只有账本兜得住。
> - **踩坑手册**：skill `dots-tts-dubbing`（任何 TTS/配音/音色/语速/声纹任务**先加载**）。
> - **用户要求清单**：`G:/_setup/REQUIREMENTS.md`（29 条，开头就是工作流铁律）。

[MEMORY.md] MintReader / TTS > ★★★ 生成工作流（用户原话「这是我们的工作流你记好了」，顺序不许颠倒）
## ★★★ 生成工作流（用户原话「这是我们的工作流你记好了」，顺序不许颠倒）

```
① 每条文本 → 2 seed 各一遍（**无 pitch/rate 标签**）
② 检测（ASR 吞字 / 声纹 / 电平 / F0 / 韵律 / 关键重音 rel_z）→ 两 take 取最佳
③ 未达标（韵律平 / 重音没读到）→ 再生成 1 seed → 再取最佳
④ 第 3 遍仍不行 → 才允许加 pitch / rate
```
标签是**最后手段不是并行支线**。每级候选落盘（第几遍/哪个 seed/淘汰理由）。不许跳过检测直接重生成。

[MEMORY.md] MintReader / TTS > 环境（硬约束）
## 环境（硬约束）
- RX580 8GB：**训练只能 CPU**；**禁并发 audiocpp**。**Vulkan OOM 重启无效** —— 模型峰值就超 8GB。
  唯一可行 `--threads 2` + `max_tokens≤260` + `--session-option dots_tts.mem_saver=true`（30–90s/条）；`threads=6` 必 OOM，`--backend cpu` 崩。
- **`G:/Python310` 是唯一同时有 onnxruntime + torch 的解释器**（默认 env 缺 torch/parselmouth）。
- PATH 加 `/e/tool/oopz`（ffmpeg）；ASR 用 `asr_venv` + **必须 `HF_ENDPOINT=hf-mirror.com`**。
- audiocpp 的 `--out` 相对路径基于 **ACPP_DIR** 不是 cwd。

[MEMORY.md] MintReader / TTS > 红线速查（返工过的，不许再犯）
## 红线速查（返工过的，不许再犯）

| 项 | 红线 |
|---|---|
| tempo | 硬夹 **[0.70, 1.00]**；原速 ≤255wpm 不动；4% 以内不动原文件 |
| 声纹 | ≥0.65 可接受（带情绪）/ ≥0.70 更好；段间 <0.55 报警 |
| 电平 | 全库 voiced RMS **−24dBFS**，跨度 ≤1dB |
| 拆句 | **不许拆**（N 段=N 次表演，毁整句弧线）；口吃也不许拆 |
| emo 标签 | **短对话句一律不打**（happy→吼、disgusted→砖墙、surprised→311Hz） |
| `stretch_segments` | **禁用**（段长 <0.4s 造伪影，NISQA DIS 4.18→1.81）；只用 `stretch_whole` |
| 结尾 | 不许硬切（dots.tts 尾部 5ms 掉 50dB 是通病） |
| 语速不够 | 到 0.7 还不到目标 ⇒ **只能重生成，不许再拉** |

[MEMORY.md] MintReader / TTS > ★★★ 六类情绪定档（2026-11-07，详见 `emo_bench/REPORT_EMOTION_JUDGE.md` §15）
## ★★★ 六类情绪定档（2026-11-07，详见 `emo_bench/REPORT_EMOTION_JUDGE.md` §15）

口径：同文本 + 同 seed 段 + n≥5 + 配对比较。≥P25 到位 / P10–P25 勉强 / <P10 未达。

| 情绪 | 判据 | 定档 ref | 均值 | 档 |
|---|---|---|---|---|
| 兴奋 | A×V | Expresso happy `004_speaker1_22s_24s` | 0.431 | 到位 |
| 激动反抗 | D | C_angry `c259` | 0.772 | 到位 |
| 委屈 | 1−A | C_soft `c268` | 0.750 | 到位 |
| 警惕 | e2v disgusted | Expresso disgusted `018_speaker1_68s_71s` | 0.432 | 到位 |
| 紧张 | A×(1−D) | Expresso fearful `044_speaker1_235s_238s` | 0.253 | 勉强（**0.25 数学硬顶**） |
| 平静 | V | C_normal `c185` | 0.261 | 未达（**判据退化**） |

- **紧张别再找素材**：生成层 D≈A ⇒ A(1−D)≈A(1−A)≤0.25。6 种 emo 全保持 D>A；`<rate>` 在 tts 任务**实测不生效**。
- **V 单指标判平静是退化的**：兴奋 ref 产物 6/6 过平静线，calm/sleepy 0/10。要看「平(F0跨度)+暖(V)」两维。
- **警惕双峰**（.906/.031/.167/.110/.944）⇒ 2 seed + e2v 取 >0.5，不靠调 ref。
- **ref 层指标不能预测生成结果**：选 ref 必须「是完整可懂的一句」，破碎片段指标再高也没用。
- **n=2 会骗人**：组间差必须大于组内 sd，比 ref/参数时 n≥5。

[MEMORY.md] MintReader / TTS > 对白链路闸门（2026-11-07 新建）
## 对白链路闸门（2026-11-07 新建）
`G:/_setup/dialog_gate.py` —— 技术 / 声纹 / 情绪三闸门，输出 PASS / MANUAL / REGEN 三档。
阈值按 59 条成品实测标定：`role_gap >= 0.4` → PASS（**精度 100%**），`< -0.4` → REGEN，中间 → MANUAL。
实测 Charles 23 条 PASS 20；**Thomas 36 条只 PASS 9（20 条分不开）** ⇒ 短板在模板库不在闸门。
`cut_cues.py` 是参数化切条入口（视频+srt → cue 音频），`srt` 的 `-` 换人判定有坑，见账本。

[MEMORY.md] MintReader / TTS > 其他主题 → 直接查 RAG，不要再往这里堆
## 其他主题 → 直接查 RAG，不要再往这里堆
- **dots.tts 用法/标签语法**（pitch 只能抬寄存器、rate 能定位到词、emo 要 xvector）→ skill `dots-tts-dubbing`
- **声纹链路**（1-NN + Z-norm、四模型全 5/8、情绪音色方差 > 说话人、语义反证）→ `REPORT_SPEAKER_EMOTION_REF.md`
- **测量口径**（rel_z 分母、Prosogram、TTSDS2 四因子、NISQA 归因四步）→ RAG 搜具体名词
- **评测结论**（DNSMOS/SCS 坑、标签净负收益）→ `EVAL_RESEARCH.md`
- **前端** reader/：不主动重建 APK；靠左不断词；进度 `kv:prog:<bookId>`
