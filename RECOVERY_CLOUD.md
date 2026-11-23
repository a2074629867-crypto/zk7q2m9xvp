# 云端资产固定与恢复手册（2026-11-10 21:30）

AI Studio 项目无法切换 GPU。**真正瓶颈是文件数，不是体积**：
体积只有 4.2G（上限 100G），但文件数 14696 —— 切环境要同步并索引全部文件，直接卡死。
已两轮瘦身：**11G → 3.8G，14696 文件 → 387 文件**。
**本文件是恢复的唯一依据，改动云端结构前先读它。**

---

## 0. 官方持久化口径（ai.baidu.com/ai-doc/AISTUDIO/5k39vd65f）

| 位置 | 持久化 | 官方原文 |
|---|---|---|
| `/home/aistudio/`（除 `data/`） | ✅ 保留 | 「该目录下除 data 目录外的变更将会持久保存」 |
| `/home/aistudio/data/` | ❌ 还原 | 「Data 目录为非持久化目录，重启之后会被自动恢复」 |
| `/home/aistudio/work/` | ✅ 保留 | Q7：「100G 云端持久化存储空间…写到该目录下的文件将被实时持久化存储」 |
| 其余（`/tmp`、`~` 之外） | ❌ 不保证 | 实测 `/tmp` 会被清空，**连正在运行的进程一起被杀** |

其他硬性条款：
- **Q7：每用户 100G** 持久化空间。当前用 3.8G，远未触顶。
- **Q11：文件过多会让启动变慢** ——「每次启动需要一定的时间加载全部文件，如果文件过多，可能在初始时间文件显示不完整」。
- **Q12：CPU/GPU 同项目共享文件** ——「文件会自动同步。但**如果文件数过多，或体积过大，需要一定的时间来完成同步**」。
- **Q9：最多同时运行 3 个 Notebook 项目**。
- 项目预览页对主文件 `项目ID.ipynb` 有 **10MB** 上限（超了只影响预览，不影响运行）。

⇒ **推论**：切换 GPU = 把 `/home/aistudio` 全量同步到新容器 + 建索引。
14696 个文件时这一步做不完/超时，前端表现为「项目过大」。
体积 3.8G 里 3.25G 是 2 个文件（gguf 2.8G + binary 447M），**大文件不影响文件数**。

---

## 1. 三处备份（互为冗余）

| 位置 | 内容 | 校验 |
|---|---|---|
| 云端 `/home/aistudio/backup/assets_core.tar.gz` | 16M：74 音色 + refs + plan + 脚本 + out | sha256 `9ccb7b44...6cf7` |
| 云端 `/home/aistudio/backup/audiocpp_server.bin.gz` | 128M：编译产物压缩 | 解压后 `0c116153...260e` |
| **本地** `G:/_setup/_cloud_backup/` | 上述两个文件均已下载并校验通过 | 同上 |
| 异地 litterbox（72h 过期） | `https://litter.catbox.moe/xcmli4.gz`（16M）<br>`https://litter.catbox.moe/5jq8jx.gz`（128M） | 同上 |

本地备份是**主备份**，litterbox 只是过渡。72h 后只信本地。

---

## 2. 不可重建 vs 可重建

| 资产 | 体积 | 重建代价 | 处置 |
|---|---|---|---|
| `build_cuda/bin/audiocpp_server` | 446M | **40 分钟编译 + GCC9 补丁** | ⛔ 绝不能丢，已三处备份 |
| `models/DotTTS-Edit-GGUF/dots-tts-edit-q8_0.gguf` | 2.8G | 重下 2.8G（modelscope，慢） | 保留 |
| `voice_lib/`（74 音色 + prompt_text） | 10M | 从 `refs/` + `_emo_refs_cloud.json` 重建 | 已备份 |
| `plan.jsonl`（955 条） | 305K | 本地 `make_plan.py` 可重建 | 已备份 |
| `loops.py` / `qc.py` / `runbook*.py` | 32K | 本地 `cloud/` 有源 | 已备份 |
| `pylib.tar.gz` | 105M | `tar xzf pylib.tar.gz` 即还原（内含 8127 文件） | **已打包**，见 §7 |
| `audio_src.tar.gz` | 116M | `tar xzf audio_src.tar.gz` 即还原（内含 6183 文件） | **已打包**，见 §7 |

**已删除（可重建，不再保留）**：
`build_cuda/{ggml,CMakeFiles,external,generated,libengine_runtime.a}` 2.6G、
`cu12` 1.4G、`external-libraries` 1.4G、`work/tts` 729M、`audio.cpp/.git` 111M、`glibc235` 23M

⚠️ 删 `build_cuda/CMakeFiles` 的代价：**改代码后重编译要重新 configure**（约 40 分钟）。
只跑生成不受影响，binary 是完整的。

---

## 3. 恢复场景

### 场景 A：切换 GPU 后 `/home/aistudio` 完好（预期情况）
```bash
cd /home/aistudio
bash start_gpu.sh                      # 起服务，自带 health 自检
python3 loops.py --plan plan.jsonl --only narr --limit 20
```
无需恢复任何东西。切完先跑 `ls -lh build_cuda/bin/` 确认 binary 在。

### 场景 B：binary 丢了，其余在
```bash
cd /home/aistudio
# 从本地重传（本地 → ntfy → 云端），或直接 litterbox（若未过期）
curl -sL -o /tmp/bin.gz https://litter.catbox.moe/5jq8jx.gz
gunzip -c /tmp/bin.gz > build_cuda/bin/audiocpp_server
chmod +x build_cuda/bin/audiocpp_server
sha256sum build_cuda/bin/audiocpp_server    # 必须是 0c116153...260e
```

### 场景 C：整个 `/home/aistudio` 被清空
按顺序：
1. **拿回核心资产**
   ```bash
   curl -sL -o /tmp/core.tgz https://litter.catbox.moe/xcmli4.gz
   tar xzf /tmp/core.tgz -C /home/aistudio
   ```
   若 litterbox 已过期 → 从本地 `G:/_setup/_cloud_backup/assets_core.tar.gz` 经 ntfy 分卷传（4M/块，ntfy 单文件上限 15M 且**免费带宽会耗尽**，此时改用 litterbox 或 filebin 新 bin）。

2. **拿回 binary**（同场景 B）

3. **重下模型**（2.8G，modelscope 镜像）
   ```bash
   mkdir -p /home/aistudio/models/DotTTS-Edit-GGUF
   cd /home/aistudio/models/DotTTS-Edit-GGUF
   curl -L -o dots-tts-edit-q8_0.gguf \
     https://modelscope.cn/models/HereIsMark/audio.cpp-gguf/resolve/master/dots-tts-edit-q8_0.gguf
   # 期望 sha256 见 G:/_setup/cloud/setup_native.sh 里的 SHA 变量
   ```

4. **重装 pylib**（仅当要跑 ASR / 声纹 / parselmouth 时才需要）
   ```bash
   # 优先：解压已有的包（秒级，不耗流量）
   cd /home/aistudio && tar xzf pylib.tar.gz
   # 或用系统 numpy 直接跑（loops.py / qc.py 只需要 numpy 1.26，系统自带）
   ```
   真要重装时：
   ```bash
   export PIP_USER=0
   pip install --target /home/aistudio/pylib \
     numpy onnxruntime praat-parselmouth soundfile scipy \
     -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```
   ⚠️ 包名是 **`praat-parselmouth`**，不是 `parselmouth`（后者是冒名包，拉 googleads 依赖）。

5. **需要改代码才重编译**（40 分钟，见 §4）

---

## 4. 重编译（只在需要改代码时）

```bash
cd /home/aistudio/audio.cpp
# ⛔ 必打补丁：GCC 9 没有 std::chars_format（GCC 11+ 才有）
#    src/framework/debug/trace.cpp 里用 #if defined(__GNUC__) && (__GNUC__ >= 11) 包住那段
bash scripts/build_linux.sh --backend cuda --cuda-arch 70 \
  --model-set custom --models dots_tts --target audiocpp_server \
  -j 2 --build-dir /home/aistudio/build_cuda
```
续编不要重跑 `build_linux.sh`（会重新 configure），直接
`cd build_cuda && make -j2 audiocpp_server`。

**CPU 实例上跑 CUDA 版需要 stub**（GPU 实例不需要）：
```bash
mkdir -p ~/stub
ln -sf /usr/local/cuda/lib64/stubs/libcuda.so ~/stub/libcuda.so.1
export LD_LIBRARY_PATH=~/stub:/usr/local/cuda/lib64:$LD_LIBRARY_PATH
```

---

## 5. 通道

`G:/_setup/rcc.py` —— ntfy 信令 + 云端 `w11.py` 常驻执行器。
- 云端执行器若挂了：`cd /home/aistudio && (setsid nohup python3 w11.py >w11.log 2>&1 </dev/null &)`
- **ntfy 免费带宽会耗尽**（返回 413 `attachment too large, or bandwidth limit reached`），
  大文件改用 litterbox（1GB / 72h）。
- 写 `.sh` 上传前必须确认是 **LF 换行**，CRLF 会让 bash 报 `$'\r': command not found`。

---

## 6. 当前云端构成（3.8G / 387 文件）

```
2.8G  models/                       gguf 模型（2 文件）
447M  build_cuda/bin/audiocpp_server
143M  backup/                       上一轮备份（6 文件）
116M  audio_src.tar.gz              源码打包（原 6183 文件）
105M  pylib.tar.gz                  依赖打包（原 8127 文件）
10M   voice_lib/                    74 音色 + prompt_text（75 文件）
9.2M  refs/                         参考音原始件（70 文件）
308K  plan.jsonl                    955 条计划
396K  out/                          已生成音频
      loops.py qc.py runbook*.py start_gpu.sh server_gpu.json
```

文件数分布：`voice_lib` 75 / `refs` 70 / 根目录散文件 53 / `cc` 9 / `backup` 6 /
`build_cuda` 5 / `models` 2 / `out` 1 = **387**。

---

## 7. 为什么要打包（这是能切 GPU 的关键）

第一轮只降体积（11G→4.1G），文件数仍 **14696**，切 GPU 依然失败。
两个目录占了 97% 的文件数，且都是**纯代码、可重建**：

| 目录 | 文件数 | 体积 | 打包后 | 怎么恢复 |
|---|---|---|---|---|
| `pylib/` | 8127 | 360M | `pylib.tar.gz` 105M | `tar xzf pylib.tar.gz` |
| `audio.cpp/` | 6183 | 254M | `audio_src.tar.gz` 116M | `tar xzf audio_src.tar.gz` |

打包后文件数 **14696 → 387**（降 97.4%），体积 4249M → 3854M。

**注意**：
- `loops.py` / `qc.py` 只依赖 `numpy`，系统自带 1.26.4 够用 ⇒ **不打包也能直接跑**。
- 要跑 ASR / 声纹 / parselmouth 时才需要解压 `pylib.tar.gz`。
- 要改 C++ 代码重编译时才需要解压 `audio_src.tar.gz`（而且还得重新 configure，见 §4）。
- 打包/解包都在 2 核上约 1–2 分钟。
