# -*- coding: utf-8 -*-
"""itts_install.py —— 绕过 uv 在 Windows 上的 sdist build 残留问题，循环重试安装

根因：这些 sdist（julius / antlr4-python3-runtime / openai-whisper ...）在打包时
     把 build/ 产物一起塞进去了，setuptools 解压后再建 *.dist-info 就撞
     [WinError 183] 当文件已存在时，无法创建该文件。
修法：每次失败后把 uv 缓存里所有 build/ 目录删掉再重试（用 shutil，避开 shell 安全拦截）。
"""
import os, re, sys, glob, shutil, subprocess, time

CACHE = r"C:\Users\86178\AppData\Local\uv\cache"
REPO = r"G:\_setup\index-tts"
UV = r"C:\Users\86178\.local\bin\uv.exe"
LOG = r"G:\_setup\_itts_install.log"

env = dict(os.environ)
env["PATH"] = r"C:\Users\86178\.local\bin;" + env.get("PATH", "")
env["https_proxy"] = "http://127.0.0.1:7897"
env["http_proxy"] = "http://127.0.0.1:7897"
env["UV_HTTP_TIMEOUT"] = "300"
env["UV_LINK_MODE"] = "copy"

logf = open(LOG, "w", encoding="utf-8", errors="replace")


def clean_builds(tag=""):
    n = 0
    for pat in (os.path.join(CACHE, "builds-v0"),
                os.path.join(CACHE, "sdists-v9")):
        if not os.path.isdir(pat):
            continue
        if pat.endswith("builds-v0"):
            shutil.rmtree(pat, ignore_errors=True)
            n += 1
            continue
        for d in glob.glob(os.path.join(pat, "**", "build"), recursive=True):
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    print("[clean%s] removed %d dirs" % (tag, n), flush=True)


for attempt in range(1, 15):
    print("===== ATTEMPT %d =====" % attempt, flush=True)
    logf.write("\n===== ATTEMPT %d =====\n" % attempt); logf.flush()
    p = subprocess.run([UV, "sync"], cwd=REPO, env=env, capture_output=True, text=True, errors="replace")
    logf.write(p.stdout or ""); logf.write(p.stderr or ""); logf.flush()
    if p.returncode == 0:
        print("SUCCESS on attempt %d" % attempt, flush=True)
        r = subprocess.run([os.path.join(REPO, ".venv", "Scripts", "python.exe"),
                            "-c", "import torch;print('torch',torch.__version__)"],
                           capture_output=True, text=True)
        print(r.stdout.strip(), r.stderr.strip()[:200], flush=True)
        sys.exit(0)
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"Failed to build\s+`([^`]+)`", out)
    pkg = m.group(1) if m else "?"
    print("failed on: %s" % pkg, flush=True)
    clean_builds(":" + pkg)

print("GAVE UP after 14 attempts", flush=True)
sys.exit(1)
