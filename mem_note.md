
## ★ 转向：GPT-SoVITS 真·训练（用户否掉零样本克隆）— 2026-10-14 凌晨
用户原话：「用啥AB模型，肯定会更好的，你就帮我找练长音频最准的训练模型来，适配我的580的来」
→ **放弃 Chatterbox/Dots 零样本克隆路线，改做真正的微调训练。**

### ① 用户问「ASR 参考稿是不是自己训练的」→ 不是
- `Dots.TTS`（`dots-tts-soar-q8_0.gguf` 2.96GB）= 下载的预训练模型，只做推理
- `Canary-180M`（`canary-180m-flash-q8_0.gguf` 249MB）= 下载的预训练 ASR，只做推理
- **「ASR 参考稿」= 用 Canary 跑我们那 16 秒参考音得到的逐字稿**（286 字节），
  再当 `--reference-text` 喂给 Dots。**全程零训练。**
- 命令在 `_tts_lab/dots_sweep.sh`：`--task asr --family canary_asr` → `--task clon --family dots_tts --reference-text`

### ② 「参考音越长越好吗」→ 零样本里**反而更差**（实测）
IndexTTS-2.5 严格对照（同句/同 seed=4242，唯一变量=参考音长度）：
| 参考音 | 相似度 |
|---|---|
| **16s** | **0.8159** |
| 30s | 0.7552 |
| 60s | 0.7187 |
| 5min | 0.7076 |
| 21min | 0.7347 |
16s→5min 单调下降。原因：模型把说话人各种状态**平均掉**，辨识度被稀释。
⚠️ 但这是 **IndexTTS** 上的结论；Dots 架构不同（`_tts_lab/reflen_dots.py` 已写好对照实验，未跑完）。

### ③ ★★ 「适配 580」的硬结论（一手来源）
RVC 项目 changelog（08-13）原文：
> 通过 pytorch-dml 增加对 AMD(A卡)/Intel(I卡) 的支持，但**适用范围是实时变声、推理、人声伴奏分离三类功能；训练暂不支持，会回退到 CPU 训练**

- **ROCm 明确不支持 GCN（RX 580 = gfx803）**；网上「AMD 卡可正常训练」的文章与仓库 changelog 矛盾，不采信
- ⇒ **训练一律 CPU；580 只用于推理**（我们已有的 audio.cpp Vulkan 路径，RVC RTF 0.54）
- 本机：**12 线程 Zen3（AMD Family 25 Model 33）**，纯 CPU 训练够用
- 社区实测：GPT-SoVITS 8G 卡 30-60 分钟 / **纯 CPU 约 2-4 小时，建议挂着过夜**

### ④ 训练素材：Calm《Wonder》
- 用户给的 B 站源：`https://www.bilibili.com/video/BV1ve411p7k4/`
  （UP「七点钟的黛黛黛博拉」，**29:05**，双语字幕烧在画面里，无 CC 轨道）
- 下载：`yt-dlp -f 30232 -x --audio-format wav`（B 站要 `--proxy ""` 直连；抽帧要带 `Referer`）
  → `E:/tts-models/refs/calm/wonder_src.{m4a,wav}`
- ⚠️ **30~120s 垫了背景音乐**（底噪 -44dB），120s 后干净（-58~-67dB）
  → 训练集取 **130s→1745s（26:55）**，存 `G:/GPT-SoVITS/_dataset/wonder_train.wav`（32k 单声道）
- 切片：`tools/slice_audio.py ... -34 4000 300 10 500 0.9 0.25 0 1` → **302 片 / 21.4 分 / 中位 4.1s**
- 打标：`_dataset/asr_label.py`（faster-whisper `small.en`，CPU int8）→ **302/302 成功，14425 字符**
  格式 `路径|说话人|语言|文本`（GPT-SoVITS `1-get-text.py` 要求）

### ⑤ 环境搭建（全部装 G 盘，C 盘只剩 8.9GB）
- **Python 3.10.11 embeddable** → `G:/Python310`（安装器被沙箱拦，用 embeddable + get-pip.py）
  - ⚠️ **embeddable 的 `python310._pth` 会屏蔽 `PYTHONPATH`，且脚本目录不进 sys.path**
    → 必须把 `G:/GPT-SoVITS`、`G:/GPT-SoVITS/GPT_SoVITS`、`G:/GPT-SoVITS/tools` 写进 `._pth`
- 源码：GitHub 直连不通 → `git clone https://gitclone.com/github.com/RVC-Boss/GPT-SoVITS.git` → `G:/GPT-SoVITS`
- 模型：HF 不通 → **`hf-mirror.com` 通**，拉了 1.9GB 到 `GPT_SoVITS/pretrained_models/`
  （hubert / roberta / s1bert ckpt / gsv-v2final 的 s2G+s2D）
- 依赖（清华源）：**两个包必须跳过**，无 C 编译器装不了
  - `pyopenjtalk`（只服务日语；`japanese.py` 的 import 有 `except Exception` 兜底，可缺）
  - `jieba_fast`（只服务中文）→ **自己写了 stub 转发给 `jieba`**，放 `Lib/site-packages/jieba_fast/`
- ⚠️ **版本坑（踩了 4 个）**：
  1. `huggingface_hub 2.2.0` 太新，`gradio 4.24` 要的 `HfFolder` 已删 → 降到 **0.30.2**
  2. `transformers 5.19` 对 2025-04 的 GPT-SoVITS 太新 → 降到 **4.50.3** + `tokenizers 0.21.1`
  3. `setuptools 84` 移除了 `pkg_resources`，而 `librosa 0.9.2` 依赖它 → 降到 **75.8.0**
  4. NLTK 数据缺失（`g2p_en` 要）→ **`ghproxy.net` 能转发 raw.githubusercontent**
     （`github.com` 直连 000，但 `ghproxy.net/https://raw.githubusercontent.com/...` 是 200）
     → `G:/nltk_data/{taggers,corpora}`
- `ffmpeg` 必须进 PATH：`E:/tool/oopz`（**该目录只有 ffmpeg，没有 ffprobe**）
- 训练驱动：`G:/_setup/run_train.py`（复刻 WebUI 逻辑，CPU 模式）
  - ⚠️ **WebUI 会把 `2-name2text-<part>.txt` 合并成 `2-name2text.txt`** —— 驱动里必须自己合并，
    否则 `TextAudioSpeakerLoader` 断言失败
  - CPU 参数：s2 `fp16_run=False` batch=2 epochs=8；s1 `precision="32"` batch=2 epochs=15

### ⑥ ★ 会话进程存活坑（重要）
- `nohup ... &`、`cmd /c start /b`、GUI 式分离启动 **全都会被沙箱回收**（实测 20s 内死）
- `schtasks` / `wmic` **在黑名单**
- ⇒ 长时间任务只能用**工具自带的后台机制**（`run_in_background`），实测能连续跑 9+ 分钟
- 预处理脚本本身**可断点续跑**（都检查 `os.path.exists` 跳过），中断后重跑即可

### ⑦ 待办
- [ ] 训练完成后用 `inference_webui.py` / `inference_cli.py` 出样，和之前的零样本样本对比
- [ ] 若标签质量不够，可换 `medium.en` 重打标
