# V100 云端部署实况（2026-11-10 02:30–04:00）

## 一、结论先行

**前三章没有跑出来。** 卡在最后一公里：`audiocpp_server` 能启动，但缺 `--config` 配置文件；
而 code-server 的终端输入在 03:40 后间歇失效（Enter 键不生效），无法继续配置。

**但环境已经搭好并持久化**，下次开机可以直接接着跑，不需要重新下载任何东西。

---

## 二、这台机器的真实参数（实测，不是截图里的）

| 项 | 截图显示 | 实测 |
|---|---|---|
| GPU | V100 16G | **Tesla V100-SXM2-32GB，compute_cap 7.0** |
| CPU | 2 核 | `nproc`=64（宿主），**cgroup quota 200000/100000 = 2 核** |
| RAM | 16GB | `memory.max` = 17179869184 = **16GB** |
| 磁盘 | 100GB | overlay 4.0T，**可用 420GB** |
| 系统 | — | **Ubuntu 20.04.6，GLIBC 2.31** |
| CUDA | — | nvcc 11.8.89，**驱动 525.125.06** |
| Python | — | conda `python35-paddle120-env`，**无 torch** |

**关键结论：CPU 确实只有 2 核**（截图没说错），源码编译不可行。

---

## 三、踩到的硬坑：预编译包全部 GLIBC 不兼容

GitHub release `0xShug0/audio.cpp` v0.9.4（2026-11-05）有 Linux CUDA 包，但：

| 包 | 大小 | 要求 GLIBC | 在 2.31 上 |
|---|---|---|---|
| `bin-ubuntu-x64-cuda12.8-colab` | 219MB | **2.35** | ✗ |
| `bin-ubuntu-x64-cpu-portable` | 66MB | **2.43** | ✗ |
| `cudart-ubuntu-x64-cuda12.8` | 751MB | 未测 | — |

原因：GitHub Actions 的 `ubuntu-latest` 现在是 24.04，编出来的二进制要 GLIBC 2.39+。

---

## 四、绕过去的方法（已验证可行）

不需要 root、不重启实例，用**用户态新 glibc 启动器 + pip 版 CUDA 12 库**：

```
~/glibc235/root/          # libc6_2.35-0ubuntu3.8 解包
~/glibc235/ossl3/         # libssl3 3.0.2-0ubuntu1.30 解包（提供 libssl.so.3 / libcrypto.so.3）
~/cu12/                   # pip install --target 装的 nvidia-cublas-cu12 / cuda-runtime-cu12 / cufft-cu12
~/work/tts/audiocpp_server   # 286MB，v0.9.4 cuda12.8-colab
~/models/DotTTS-Edit-GGUF/dots-tts-edit-q8_0.gguf   # 1.14GB，ModelScope
```

启动方式（已写成 `~/work/run_tts.sh`）：

```bash
GL=$HOME/glibc235/root/lib/x86_64-linux-gnu
LP=$HOME/cu12/nvidia/cublas/lib:$HOME/cu12/nvidia/cuda_runtime/lib:$HOME/cu12/nvidia/cufft/lib:$HOME/glibc235/ossl3/usr/lib/x86_64-linux-gnu:$GL
$GL/ld-linux-x86-64.so.2 --library-path "$LP" $HOME/work/tts/audiocpp_server "$@"
```

**已验证**：这样启动后能正常打印 `--help`（列出 `--list-devices` / `--busy-timeout-ms` /
`--max-loaded-models` 等参数），说明 GLIBC、CUDA、OpenSSL 三层都过了。

---

## 五、卡在哪（下次从这里继续）

```
audiocpp_server failed: missing required --config argument (or use --ui for the native webui)
```

两条路，下次二选一：

1. **`--ui`**：起内置 web 界面，浏览器直接操作。最快。
2. **`--config`**：官方有 `server-config-examples.zip`（14.8KB），
   地址 `https://github.com/0xShug0/audio.cpp/releases/download/v0.9.4/server-config-examples.zip`
   这次下载下来的不是 zip（可能被重定向成 HTML），需要加 `-H "Accept: application/zip"` 或换镜像重下。

另外 `~/work/tts/model_specs/` 里已有全套模型规格 json，包括 `dots_tts.json`，
`--config` 也可能直接吃这个。

---

## 六、通道：本机 ↔ 云端

建成了 `G:/_setup/rcc.py`（Remote Cloud Command），本机推命令、云端执行、本机取结果，
**全程不需要截图**：

```bash
cd /g/_setup
/g/Python310/python.exe rcc.py "nvidia-smi"          # 推命令并等结果
/g/Python310/python.exe rcc.py --timeout 600 -f x.sh  # 推脚本
```

云端 watcher 在 `/tmp/cc/w2.sh`（8 秒轮询 filebin）。

⚠ **坑**：filebin 匿名请求有速率限制。第一版 watcher 3 秒轮询，跑了约 10 轮后被限流，
通道整体失效（返回 404 / 错误页）。改成 8 秒后恢复。**下次不要低于 8 秒**。

⚠ **坑**：code-server 的 xterm 终端在长文本输入后，Enter 键会间歇失效
（`cua_keypress Enter` 和 `Ctrl+M` 都试过，无效）。可靠的做法是用 notebook 单元格
（真实 `<textarea>`，可以用 DOM 精确输入）+ Shift+Enter。

---

## 七、没做完的部分

| 项 | 状态 |
|---|---|
| 环境下载与组装 | ✅ 完成并持久化 |
| audiocpp_server 启动 | ✅ 能跑（help 正常） |
| 加载模型 + 起服务 | ❌ 缺 --config |
| 生成音频（哪怕 1 条） | ❌ 未验证 |
| 前三章 784 条 | ❌ 未开始 |
| 时间 | 02:30 开始，04:00 停止，未超用户 1.5 小时保留线 |

## 八、下次的最短路径

1. 开机 → `~/work/run_tts.sh --ui`（或补 `--config`）
2. 起服务后先跑 1 条验证出声
3. 再上批量（`cloud/jobs.json` 784 条，V100 上按 3~6 秒/条估 40~78 分钟）
4. 线程数从 `-j2` 起步，边跑边看 `nvidia-smi` 显存和 `free -g`
