"""LLM 网关 key 的读取入口 —— 不把 key 写进源码（仓库要公开）。

优先级：
1. 环境变量 ANN_LLM_KEY
2. 同目录 .secrets/ann_llm_key.txt（已 gitignore，只在本机存在）

2026-11-24：原来 4 个脚本里硬编码了同一个 sk- key，准备把项目公开到 GitHub，
必须挪出源码。调用方用 `from _llm_key import get_key`。
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_FILE = os.path.join(_HERE, ".secrets", "ann_llm_key.txt")


def get_key():
    k = (os.environ.get("ANN_LLM_KEY") or "").strip()
    if k:
        return k
    if os.path.exists(_FILE):
        with open(_FILE, encoding="utf-8") as f:
            return f.read().strip()
    return ""


if __name__ == "__main__":
    v = get_key()
    print("key 已读到（长度 %d，前缀 %s）" % (len(v), v[:6] + "…" if v else "空"))
