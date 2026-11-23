# -*- coding: utf-8 -*-
"""集中式路径与运行时配置（本机 Windows / 云上 Linux 共用一套代码）。

为什么要这个文件
----------------
2026-11-24 之前，`_regen9.py` / `_regen_short.py` / `_campaign9.py` 里写死了
`C:\\Users\\...\\acpp`、`E:/tts-models/...`、`"--backend", "vulkan"`、`mem_saver=true`。
这些是 **RX580 8G 显存 + Vulkan 后端** 的将就参数，换到云 GPU（T4 16G / CUDA）上
必须整体换掉，否则要么跑不动要么白白慢几倍。

设计原则
--------
1. **本机行为一个字节都不许变**：所有 Windows 默认值与改动前完全一致
   （acpp 在 C 盘旧会话目录、模型在 E:/tts-models、backend=vulkan、threads=2、mem_saver 开）。
2. 云上只需要导出几个环境变量，**不改代码**：
       export MR_ROOT=/root/mintreader
       export ACPP_BACKEND=cuda
       export ACPP_THREADS=8
       export ACPP_MEM_SAVER=0
3. 所有路径都先看环境变量，再看平台默认值；有 `MR_ROOT` 时相对资源一律挂在它下面。

新增路径请加在这里，不要在业务脚本里再写死盘符。
"""
import os

IS_WIN = os.name == "nt"
_HERE = os.path.dirname(os.path.abspath(__file__))


def _e(key, default):
    """读环境变量；空字符串视为未设置（避免 export X= 把默认值冲掉）。"""
    v = os.environ.get(key)
    return v if v else default


def _flag(key, default):
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "y")


# ---------------------------------------------------------------- 工作区
# 本机 G:/_setup；云上把仓库 clone 到哪就是哪
ROOT = _e("MR_ROOT", "G:/_setup" if IS_WIN else _HERE)

# ---------------------------------------------------------------- audio.cpp 运行时
# 本机：旧会话目录里的 Windows 预编译包（build: msvc, backends: cpu,vulkan）
# 云上：deploy_cloud.sh 编译/下载到 $ROOT/_acpp
ACPP_DIR = _e(
    "ACPP_DIR",
    r"C:\Users\86178\WorkBuddy\2026-10-05-00-50-22\reader\_tts_lab\acpp"
    if IS_WIN else os.path.join(ROOT, "_acpp"),
)
ACPP = _e("ACPP_BIN", os.path.join(ACPP_DIR, "audiocpp_cli.exe" if IS_WIN else "audiocpp_cli"))

# 后端：本机 Vulkan（RX580 唯一可用）；云上 NVIDIA 走 cuda，AMD 走 hip，无卡走 cpu
ACPP_BACKEND = _e("ACPP_BACKEND", "vulkan" if IS_WIN else "cuda")

# 显存不够时才开 mem_saver：本机 8G 必须开；云上 T4 16G 开着会明显变慢
ACPP_MEM_SAVER = _flag("ACPP_MEM_SAVER", IS_WIN)

# 线程：本机 RX580 超过 2 就 OOM；云上按核数走
ACPP_THREADS = int(_e("ACPP_THREADS", "2" if IS_WIN else str(os.cpu_count() or 4)))

# ---------------------------------------------------------------- 模型
# DotTTS-Edit q8_0 GGUF（2.8GB，来自 HF: HereIsMark/audio.cpp-gguf）
MODEL = _e(
    "DOTS_MODEL",
    "E:/tts-models/acpp/DotTTS-Edit-GGUF" if IS_WIN
    else os.path.join(ROOT, "models_tts", "DotTTS-Edit-GGUF"),
)

# 情绪闸：emotion2vec_plus_large（1.9GB，ModelScope iic/emotion2vec_plus_large）
EMO2VEC = _e("EMO2VEC_MODEL", os.path.join(ROOT, "models", "ms", "iic", "emotion2vec_plus_large"))

# 声纹闸：microsoft/wavlm-base-plus-sv（772MB, HF）；作为 HF cache 根目录使用
SV_HOME = _e("SV_HOME", os.path.join(ROOT, "models", "sv"))

# 真正在用声纹嵌入：wespeaker ResNet ONNX（r34 26MB / r293 110MB），非 wavlm
SV_ONNX_DIR = _e("SV_ONNX_DIR", os.path.join(ROOT, "models", "sv_hub"))

# 判据用的统计基线
REF_STATS = _e("REF_STATS", os.path.join(ROOT, "emo_bench", "out", "ref_stats.json"))
BG_Z = _e("BG_Z", os.path.join(ROOT, "out_sv", "cues_znorm2.json"))
BG_MAP = _e("BG_MAP", os.path.join(ROOT, "_bg_map_v2.json"))
# 默认模板库**保持 _emo_refs.json 不变**：v2 库整库重判 PASS 128→150，但分域后 Z-norm 的
# μ/σ 变了，--z-target-min 还没按新库重标，直接换默认会误伤 18 条边际条目（见 DECISIONS 00:40）。
EMO_LIB = _e("EMO_LIB", os.path.join(ROOT, "_emo_refs.json"))
EMO_LIB_V2 = _e("EMO_LIB_V2", os.path.join(ROOT, "_emo_refs_v2.json"))

# ---------------------------------------------------------------- 给命令行用
def acpp_base_args(threads=None):
    """audio.cpp 每次调用都要带的后端参数。"""
    return ["--backend", ACPP_BACKEND, "--threads", str(threads or ACPP_THREADS)]


def mem_saver_args():
    return ["--session-option", "dots_tts.mem_saver=true"] if ACPP_MEM_SAVER else []


def describe():
    return "\n".join([
        "ROOT       = %s" % ROOT,
        "ACPP       = %s  (%s)" % (ACPP, "存在" if os.path.exists(ACPP) else "缺失"),
        "ACPP_DIR   = %s" % ACPP_DIR,
        "backend    = %s  threads=%d  mem_saver=%s"
        % (ACPP_BACKEND, ACPP_THREADS, "on" if ACPP_MEM_SAVER else "off"),
        "MODEL      = %s  (%s)" % (MODEL, "存在" if os.path.exists(MODEL) else "缺失"),
        "EMO2VEC    = %s  (%s)" % (EMO2VEC, "存在" if os.path.exists(EMO2VEC) else "缺失"),
        "SV_HOME    = %s  (%s)" % (SV_HOME, "存在" if os.path.exists(SV_HOME) else "缺失"),
        "REF_STATS  = %s  (%s)" % (REF_STATS, "存在" if os.path.exists(REF_STATS) else "缺失"),
        "BG_Z       = %s  (%s)" % (BG_Z, "存在" if os.path.exists(BG_Z) else "缺失"),
        "EMO_LIB    = %s  (%s)" % (EMO_LIB, "存在" if os.path.exists(EMO_LIB) else "缺失"),
    ])


if __name__ == "__main__":
    print(describe())
