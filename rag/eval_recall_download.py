# -*- coding: utf-8 -*-
"""量化：下载域提示词在 RAG 账本里的首条命中率（术语型 vs 口语型 vs 加域词）。

用法： cd G:/_setup/rag && python eval_recall_download.py
账本条目的 topic 集合见 DOWNLOAD_TOPICS；首条命中 = fact search 的第一条属于本域。
"""
import subprocess
import re

PY = r"C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
CWD = r"G:/_setup/rag"

DOWNLOAD_TOPICS = {
    "本机下载工具清单与实测版本",
    "yt-dlp 每条命令必带 ffmpeg-location 与 cache-dir",
    "先 simulate -F 与 list-subs 再决定下载",
    "yt-dlp 通用主命令参数与格式选择",
    "ok.ru 用 yt-dlp 一键只到 720p",
    "ok.ru 手工三头与签名直链 400 排查顺序",
    "B站无 cookie 可到 1080p 但字幕轨常是弹幕",
    "YouTube EJS JS runtime 与 zipapp 插件发现坑",
    "DRM 与 AES-128 的源码级边界",
    "订阅流媒体 DRM 红线",
    "分片并发 N 与 aria2c 外部下载器的分工",
    "download-sections 切段依赖 ffmpeg 与实测输出",
    "HLS m3u8 直链与 ffmpeg 远程 Range 切段",
    "BT 磁力下载入口与迅雷口径",
    "找对应字幕的决策树顺序",
    "视频站随片字幕多数不是译本",
    "字幕四项匹配与偏移判据",
    "下载后验收必量真实时长",
    "下载类文档与路由 skill 指针",
    "下载任务的磁盘与进程纪律",
    "下载域检索必须带域限定词",
    "下载后字幕压缩包乱码怎么修",
}

# 术语型：只用下载域账本里真实存在的名词
TERM = [
    "yt-dlp ffmpeg-location cache-dir 合并 C盘禁写",
    "ok.ru full 1080 三头 Origin 720p 手工解析 400",
    "B站 danmaku xml 1080P 高清 大会员 cookies",
    "DRM AES-128 源码 hls.py allow-unplayable-formats",
    "YouTube EJS js-runtimes PO token zipapp 插件发现",
    "concurrent-fragments aria2c dash m3u8 download-sections ffmpeg",
    "视频站随片字幕 ASR 弹幕 不是译本 list-subs write-subs",
    "BT 磁力 迅雷 0做种 infohash 文件列表 RAR 分卷",
]
# 口语型：对照组，预期被配音域/影视域账本抢走首位
COLLOQ = [
    "这个视频怎么下不下来",
    "下完字幕对不上怎么办",
    "为什么只有 720p",
    "字幕文件里全是乱码",
]
# 口语 + 域限定词：预期全部命中下载域
DOMAIN = [
    "下载 视频站 为什么只有 720p ok.ru full 三头 Origin",
    "下载 字幕 下完字幕对不上 恒定偏移 PlayRes copyts",
    "下载 视频站 视频下不下来 ffmpeg-location cache-dir 代理",
    "下载 字幕 字幕文件乱码 GBK SubHD 三步链",
]


def probe(q):
    r = subprocess.run([PY, "rag.py", "fact", "search", q, "-k", "3"],
                       cwd=CWD, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    lines = (r.stdout or "").splitlines()
    topics = [re.sub(r"^ov=\d+\s*", "", l.split("] ", 1)[1].strip())
              for l in lines if l.startswith("[") and "] " in l]
    first = bool(topics) and topics[0] in DOWNLOAD_TOPICS
    any_hit = any(t in DOWNLOAD_TOPICS for t in topics)
    return first, any_hit, topics[0] if topics else "(无命中)"


for name, group in [("术语型", TERM), ("口语型（对照）", COLLOQ), ("口语+域限定词", DOMAIN)]:
    print("=" * 62)
    print(name)
    n_first = n_any = 0
    for q in group:
        f, a, top = probe(q)
        n_first += f
        n_any += a
        print("  %s 首条下载=%s 任意下载=%s | %s" % ("OK " if f else "-- ", f, a, q))
        print("       首条: %s" % top)
    print("  >>> 首条命中 %d/%d，任意命中 %d/%d" % (n_first, len(group), n_any, len(group)))
