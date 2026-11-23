#!/usr/bin/env bash
# =============================================================================
# 云端一键部署 —— MintReader 配音链路（Ubuntu + NVIDIA GPU）
#
# 目标环境：腾讯云 HAI「PyTorch」模板（Ubuntu 22.04/24.04，已装驱动与 CUDA）
#           或 GPU 云服务器 CVM（自己装驱动）。
#
# 用法（在实例终端里，仓库已 clone 到 /root/mintreader 的情形）：
#     cd /root/mintreader
#     bash deploy_cloud.sh
#
# 可选环境变量：
#     MR_ROOT=/root/mintreader     工作区根（默认当前目录）
#     ACPP_BACKEND=cuda            后端：cuda | vulkan | cpu（默认 cuda）
#     ACPP_THREADS=8               线程数（默认 CPU 核数）
#     ACPP_MEM_SAVER=0             显存不够才设 1
#     HF_MIRROR=1                  走 hf-mirror.com（国内默认开）
#     SKIP_APT=1 / SKIP_PY=1 / SKIP_ACPP=1 / SKIP_MODELS=1   分段跳过
#
# 幂等：每一步都先检查"已经好了就跳过"，可以反复执行。
# =============================================================================
set -euo pipefail

ROOT="${MR_ROOT:-$(pwd)}"
ACPP_DIR="${ACPP_DIR:-$ROOT/_acpp}"
BACKEND="${ACPP_BACKEND:-cuda}"
THREADS="${ACPP_THREADS:-$(nproc 2>/dev/null || echo 8)}"
MEM_SAVER="${ACPP_MEM_SAVER:-0}"
PACK="$ROOT/_cloudpack.tar"

export MR_ROOT="$ROOT" ACPP_DIR="$ACPP_DIR" ACPP_BACKEND="$BACKEND" \
       ACPP_THREADS="$THREADS" ACPP_MEM_SAVER="$MEM_SAVER"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

mkdir -p "$ROOT"
cd "$ROOT"

# ---------------------------------------------------------------- 0 体检
log "0/6 环境体检"
echo "    主机    : $(uname -sr)  $(uname -m)"
echo "    Python  : $(python3 -V 2>&1 || echo 缺失)"
echo "    核数    : $(nproc 2>/dev/null || echo '?')"
echo "    磁盘    : $(df -h "$ROOT" | awk 'NR==2{print $4" 可用 / "$2}')"
if have nvidia-smi; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | sed 's/^/    GPU     : /'
else
    warn "没有 nvidia-smi：若 BACKEND=cuda 会失败，可改 ACPP_BACKEND=cpu 或 vulkan"
fi
echo "    工作区  : $ROOT"
echo "    acpp    : $ACPP_DIR  (backend=$BACKEND threads=$THREADS mem_saver=$MEM_SAVER)"

[ -f "$ROOT/_paths.py" ] || die "找不到 _paths.py —— 请在仓库根目录执行（先 git clone）"

# ---------------------------------------------------------------- 1 系统包
if [ "${SKIP_APT:-0}" != "1" ]; then
    log "1/6 系统依赖"
    miss=()
    for b in git cmake ninja gcc g++ unzip ffmpeg; do have "$b" || miss+=("$b"); done
    [ -f /usr/lib/x86_64-linux-gnu/libsndfile.so.1 ] || miss+=("libsndfile1")
    if [ ${#miss[@]} -gt 0 ]; then
        echo "    安装: ${miss[*]}"
        $SUDO apt-get update -qq
        $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
            build-essential cmake ninja-build git curl unzip ffmpeg \
            libsndfile1 libsndfile1-dev python3-dev python3-venv 2>&1 | tail -3
    fi
    ok "系统依赖就绪"
else
    warn "SKIP_APT=1，跳过系统依赖"
fi

# ---------------------------------------------------------------- 2 Python 依赖
if [ "${SKIP_PY:-0}" != "1" ]; then
    log "2/6 Python 依赖"
    if ! python3 -c "import numpy, soundfile, torch" 2>/dev/null; then
        echo "    补装 torch（CUDA 12.1 轮子）"
        python3 -m pip install -q --upgrade pip
        python3 -m pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cu121
    else
        ok "torch 已存在: $(python3 -c 'import torch;print(torch.__version__, "cuda=" + str(torch.cuda.is_available()))' 2>/dev/null)"
    fi
    python3 -m pip install -q -r "$ROOT/requirements-cloud.txt"
    python3 - <<'PY'
import importlib.metadata as md
need = ["numpy", "soundfile", "librosa", "praat-parselmouth", "onnxruntime",
        "transformers", "faster-whisper", "demucs", "huggingface_hub", "modelscope"]
bad = []
for p in need:
    try:
        print("    %-20s %s" % (p, md.version(p)))
    except Exception:
        bad.append(p)
if bad:
    raise SystemExit("    缺包: %s" % ", ".join(bad))
PY
    ok "Python 依赖就绪"
else
    warn "SKIP_PY=1，跳过 Python 依赖"
fi

# ---------------------------------------------------------------- 3 audio.cpp
if [ "${SKIP_ACPP:-0}" != "1" ]; then
    log "3/6 audio.cpp 运行时（TTS/ASR 引擎）"
    BIN="$ACPP_DIR/audiocpp_cli"
    if [ -x "$BIN" ] && "$BIN" --version >/dev/null 2>&1; then
        ok "已存在: $("$BIN" --version | tr '\n' ' ')"
    else
        mkdir -p "$ACPP_DIR"
        built=0

        # 路线 A：源码编译 CUDA（唯一能用 NVIDIA 卡的路；官方 Ubuntu 预编译只有 CPU/Vulkan）
        if [ "$BACKEND" = "cuda" ] && have nvcc; then
            echo "    路线 A：源码编译 CUDA（首次约 10~25 分钟）"
            SRC="$ACPP_DIR/src"
            [ -d "$SRC/.git" ] || git clone --depth 1 https://github.com/pingdotgg/audio.cpp "$SRC" \
                || { warn "clone 失败，试镜像"; git clone --depth 1 https://ghfast.top/https://github.com/pingdotgg/audio.cpp "$SRC"; }
            ( cd "$SRC" && bash scripts/build_linux.sh --deployment-build --backend cuda \
                  --target audiocpp_cli ) || warn "CUDA 编译失败"
            cand=$(find "$SRC/build" -type f -name audiocpp_cli -perm -u+x 2>/dev/null | head -1)
            if [ -n "${cand:-}" ]; then cp "$cand" "$BIN"; chmod +x "$BIN"; built=1; fi
        fi

        # 路线 B：官方 Ubuntu 预编译包（CPU / Vulkan），从 Releases 按名字挑
        if [ "$built" -eq 0 ]; then
            echo "    路线 B：下载官方 Ubuntu 预编译包（CPU/Vulkan）"
            api="https://api.github.com/repos/pingdotgg/audio.cpp/releases/latest"
            url=$(curl -fsSL "$api" 2>/dev/null | grep -oE '"browser_download_url": *"[^"]+"' \
                  | cut -d'"' -f4 | grep -iE 'linux|ubuntu' \
                  | grep -iE 'vulkan|cpu' | head -1 || true)
            if [ -n "${url:-}" ]; then
                echo "    -> $url"
                tmp="$ACPP_DIR/_dl"; rm -rf "$tmp"; mkdir -p "$tmp"
                curl -fL --retry 3 -o "$tmp/pkg" "$url"
                case "$url" in
                    *.zip) unzip -q -o "$tmp/pkg" -d "$tmp" ;;
                    *)     tar -xf "$tmp/pkg" -C "$tmp" ;;
                esac
                cand=$(find "$tmp" -type f -name audiocpp_cli -perm -u+x | head -1)
                if [ -n "${cand:-}" ]; then
                    cp "$cand" "$BIN"; chmod +x "$BIN"
                    # 同目录的 .so 一起带上（ggml 后端是动态库）
                    find "$(dirname "$cand")" -maxdepth 1 -name '*.so*' -exec cp {} "$ACPP_DIR/" \;
                    built=1
                fi
            else
                warn "没找到匹配的预编译包（可能只发布了 Windows/CUDA zip）"
            fi
        fi

        [ "$built" -eq 1 ] || die "audio.cpp 没装上。手动方案：装 CUDA Toolkit 后重跑，或改用 ACPP_BACKEND=cpu 下载 CPU 包"
    fi
    echo "    版本: $("$BIN" --version 2>&1 | tr '\n' ' ')"
    echo "    设备:"; "$BIN" --list-devices 2>&1 | sed 's/^/      /' || true
    if [ "$BACKEND" = "cuda" ] && ! "$BIN" --version 2>&1 | grep -qi cuda; then
        warn "这个二进制没编进 CUDA 后端（backends 里只有 cpu/vulkan）。"
        warn "T4 上仍可用 vulkan：export ACPP_BACKEND=vulkan（需 libvulkan1，deploy 已装）"
        warn "或用 CUDA 源码包重编：cd $ACPP_DIR/src && bash scripts/build_linux.sh --deployment-build --backend cuda --target audiocpp_cli"
    fi
else
    warn "SKIP_ACPP=1，跳过引擎"
fi

# ---------------------------------------------------------------- 4 模型
if [ "${SKIP_MODELS:-0}" != "1" ]; then
    log "4/6 模型权重"
    [ "${HF_MIRROR:-1}" = "1" ] && export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}" \
        && echo "    HF 镜像: $HF_ENDPOINT"

    HFCLI=""
    have hf && HFCLI="hf"
    if [ -z "$HFCLI" ] && have huggingface-cli; then HFCLI="huggingface-cli"; fi
    hf_dl() {   # hf_dl <repo> <pattern-or-empty> <local-dir>
        if [ -n "$HFCLI" ]; then
            if [ -n "${2:-}" ]; then "$HFCLI" download "$1" "$2" --local-dir "$3" >/dev/null 2>&1
            else "$HFCLI" download "$1" --local-dir "$3" >/dev/null 2>&1; fi
        else
            python3 - <<PY >/dev/null 2>&1
from huggingface_hub import snapshot_download
kw = dict(repo_id="$1", local_dir="$3")
snapshot_download(**kw, allow_patterns=["$2"] if "$2" else None)
PY
        fi
    }

    # 4.1 DotTTS-Edit q8_0（2.8GB）
    GGUF="$ROOT/models_tts/DotTTS-Edit-GGUF/dots-tts-edit-q8_0.gguf"
    if [ -s "$GGUF" ]; then
        ok "DotTTS 已存在 $(du -h "$GGUF" | cut -f1)"
    else
        echo "    下载 DotTTS-Edit q8_0（2.8GB）"
        mkdir -p "$ROOT/models_tts"
        hf_dl HereIsMark/audio.cpp-gguf "DotTTS-Edit-GGUF/*" "$ROOT/models_tts" \
            || warn "HF 直连失败，建议 MR_ROOT 下放 _cloudpack.tar 由第 5 步补"
        [ -s "$GGUF" ] && ok "DotTTS $(du -h "$GGUF" | cut -f1)" || warn "DotTTS 仍缺失"
    fi

    # 4.2 emotion2vec_plus_large（1.9GB，ModelScope）
    EMO="$ROOT/models/ms/iic/emotion2vec_plus_large"
    if [ -d "$EMO" ] && [ -n "$(ls -A "$EMO" 2>/dev/null)" ]; then
        ok "emotion2vec 已存在 $(du -sh "$EMO" | cut -f1)"
    else
        echo "    下载 emotion2vec_plus_large（1.9GB，ModelScope）"
        mkdir -p "$(dirname "$EMO")"
        ( have modelscope && modelscope download --model iic/emotion2vec_plus_large --local_dir "$EMO" ) \
          || python3 - <<PY || warn "emotion2vec 下载失败"
from modelscope import snapshot_download
snapshot_download("iic/emotion2vec_plus_large", local_dir="$EMO")
PY
        [ -d "$EMO" ] && ok "emotion2vec $(du -sh "$EMO" | cut -f1)" || warn "emotion2vec 仍缺失"
    fi

    # 4.3 吞字闸的 wav2vec2（约 360MB，transfomers 自动下，这里预热）
    if python3 -c "import transformers" 2>/dev/null; then
        echo "    预热 wav2vec2-base-960h（吞字闸用）"
        hf_dl facebook/wav2vec2-base-960h "" "$ROOT/models_tts/wav2vec2" || warn "wav2vec2 预热失败（首次跑闸会自动下）"
    fi
else
    warn "SKIP_MODELS=1，跳过模型"
fi

# ---------------------------------------------------------------- 5 小件素材
log "5/6 参考音频与小台账（_cloudpack.tar）"
if [ -f "$PACK" ]; then
    mkdir -p "$ROOT/_unpack"
    tar -xf "$PACK" -C "$ROOT"
    ok "已展开 $(du -h "$PACK" | cut -f1) 的包"
else
    warn "没有 $PACK"
    warn "本机执行 pack_cloud.sh 生成后上传；缺了它就没参考音频，生成会全部 NO_REF"
fi
for d in _ref9 castle_fr_ref out_sv models/sv_hub; do
    if [ -d "$ROOT/$d" ]; then
        printf '    %-16s %s\n' "$d" "$(du -sh "$ROOT/$d" | cut -f1)"
    else
        warn "$d 缺失"
    fi
done

# ---------------------------------------------------------------- 6 校验
log "6/6 自检"
python3 "$ROOT/_paths.py"
echo
if [ -x "$ACPP_DIR/audiocpp_cli" ]; then
    "$ACPP_DIR/audiocpp_cli" --version | sed 's/^/    /'
fi
python3 - <<'PY'
import sys, os
sys.path.insert(0, os.environ["MR_ROOT"])
import _paths as P
need = {"模型": P.MODEL, "emotion2vec": P.EMO2VEC, "声纹ONNX": P.SV_ONNX_DIR,
        "参考目录": os.path.join(P.ROOT, "_ref9"), "Z-norm背景": P.BG_Z,
        "模板库": P.EMO_LIB, "ref_stats": P.REF_STATS}
miss = [k for k, v in need.items() if not os.path.exists(v)]
print("    缺件:", ", ".join(miss) if miss else "无")
sys.exit(1 if miss else 0)
PY

cat <<EOF

────────────────────────────────────────────────────────────
部署完成。常用命令（都可加 --dry 先看参数）：

  # 单条验证：先跑一条短的，确认音色与时长正常
  python3 _regen9.py --ids c2_0263 --seeds 42 --strip-end-punct --no-ref-text \\
      --out _sweep/cloud_test

  # 67 条 ref_text 错配重生成（不给参考文本，零渗漏）
  python3 _regen9.py --ids "\$(cat _notxt_ids.txt)" --seeds 43,44 \\
      --no-ref-text --out _sweep/notxt_cloud

  # 吞字/覆盖率闸
  python3 _align_gate.py --dir _sweep/notxt_cloud --plan-text --out _align_cloud.json

  # 情绪 + 声纹闸（需要 PYTHONPATH 带上 emo_bench）
  PYTHONPATH="$ROOT:$ROOT/emo_bench" python3 dialog_gate.py \\
      --wav _sweep/notxt_cloud/xxx.wav --who Joseph --emo 平静 \\
      --lib $ROOT/_emo_refs_v2.json --bg-map @$ROOT/_bg_map_v2.json

用完记得关机（HAI 关机不计费，数据盘保留；关机超 15 天才开始对整块盘计费）。
────────────────────────────────────────────────────────────
EOF
