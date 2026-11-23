# -*- coding: utf-8 -*-
"""量化：影视域提示词在 RAG 账本里的首条命中率（术语型 vs 口语型 vs 加域词）。"""
import subprocess

PY = r"C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
CWD = r"G:/_setup/rag"

MOVIE_TOPICS = {
    "版本谱系先于找源", "SSDSSE 剧场版假标", "Her 2013 唯一版与 R 级",
    "未删减标题是反向判据", "同名同体积不等于同一种子", "打包形式三分类",
    "迅雷口径做种数不是标准", "剧集滚动更新与假整季包", "规格约束反推档位",
    "RX580 硬解边界", "字幕第 0 步查内封轨", "双语合并与 ASS 母本",
    "恒定偏移的前提与校准点", "SubHD 免登录三步链", "ASS PlayRes 必须匹配画幅",
    "渲染验字幕必须 copyts", "本机工具链环境坑", "先搜索再定向抓",
    "帧级版本比对可靠度", "工具链文档入口", "协作硬规矩",
}

TERM = [
    "同名发布组 RAR 分卷 单 mkv 文件列表 infohash",
    "Her 2013 未删减 R级 02:05:50 版本谱系",
    "ffmpeg -i 内封字幕 chi WEB-DL 第0步",
    "copyts PTS 归零 ass 滤镜 字节相同",
    "REPORT_MOVIE_TOOLCHAIN 工具链 自检 SOP",
    "RX580 HEVC Main10 硬解 DV HDR tone mapping",
    "PlayRes 1920x804 1.34 缩放 IMAX",
    "SubHD prepare-download tk_ cookie 三步链 GBK slug",
]
COLLOQ = [
    "为什么字幕对不上",
    "这个磁力下下来怎么不是视频文件",
    "4K 会不会卡",
    "未删减版到底有没有",
]
DOMAIN = [
    "找片 片源 为什么字幕对不上 恒定偏移 校准点",
    "找片 磁力 下下来不是 mkv RAR 分卷 infohash",
    "找片 片源 4K RX580 硬解 2160p",
    "找片 片源 未删减版 版本谱系 真实时长",
]


def probe(q):
    r = subprocess.run([PY, "rag.py", "fact", "search", q, "-k", "3"],
                       cwd=CWD, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    lines = (r.stdout or "").splitlines()
    import re
    topics = [re.sub(r"^ov=\d+\s*", "", l.split("] ", 1)[1].strip())
              for l in lines if l.startswith("[") and "] " in l]
    first_movie = bool(topics) and topics[0] in MOVIE_TOPICS
    any_movie = any(t in MOVIE_TOPICS for t in topics)
    return first_movie, any_movie, topics[0] if topics else "(无命中)"


for name, group in [("术语型", TERM), ("口语型（对照）", COLLOQ), ("口语+域限定词", DOMAIN)]:
    print("=" * 62)
    print(name)
    n_first = n_any = 0
    for q in group:
        f, a, top = probe(q)
        n_first += f
        n_any += a
        print("  %s 首条影视=%s 任意影视=%s | %s" % ("OK " if f else "-- ", f, a, q))
        print("       首条: %s" % top)
    print("  >>> 首条命中 %d/%d，任意命中 %d/%d" % (n_first, len(group), n_any, len(group)))
