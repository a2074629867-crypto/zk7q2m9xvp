"""ok.ru 片子体检：一条命令拿到「时长 + 直链 + 音轨语言」。

为什么需要它（2026-11-08 踩出来的）：
1. ok.ru 视频页 HTML 里直接有 `"videos":[{"name":"hd","url":"..."}]`，带签名，能 1.9MB/s
   直下；但 yt-dlp 默认走 m3u8 分片，速度只有 70KB/s，差 20 倍。
2. ok.ru 上大量条目是 **VF（法语配音）**，标题里的 "VF" 不可靠，只有抽 45s 跑 ASR 才知道。
   用错语言的片子去切音色 = 把角色的声线换成另一个国家的演员。
3. 直链绑定 srcIp（代理出口）与 expires（约 24h），取页面与下载必须同一次会话连续做完。

用法：
  python ok_probe.py --id 4488237091576 --at 2700
  python ok_probe.py --url "https://ok.ru/video/22614774201" --at 600 --lang-only

输出：时长(秒) / 直链 / 该点位的 ASR 语种与首段文本。
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile

PROXY = "http://127.0.0.1:7897"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
FFMPEG = "E:/tool/ETS/ffmpeg/ffmpeg.exe"


def fetch_page(url):
    fd, path = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    subprocess.run(["curl", "-s", "--max-time", "40", "-x", PROXY, "-A", UA,
                    "-o", path, url], check=True)
    s = open(path, encoding="utf-8", errors="replace").read()
    os.unlink(path)
    return html.unescape(s).replace("\\u0026", "&")


def parse(page):
    dur = None
    m = re.search(r'"duration"\s*:\s*(\d+)', page)
    if m:
        dur = int(m.group(1))
    i = page.find('"videos":[')
    streams = []
    if i > 0:
        seg = page[i:i + 8000]
        for mm in re.finditer(r'"name"\s*:\s*"([^"]+)"[^{}]*?"url"\s*:\s*"([^"]+)"', seg):
            streams.append((mm.group(1), mm.group(2)))
    return dur, streams


def grab(url, at, secs, out):
    env = dict(os.environ, http_proxy=PROXY, https_proxy=PROXY)
    hdr = "Referer: https://ok.ru/video/%s\r\nOrigin: https://ok.ru\r\n" % VIDEO_ID
    cmd = [FFMPEG, "-y", "-ss", str(at), "-t", str(secs),
           "-headers", hdr, "-user_agent", UA,
           "-i", url, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
           out, "-loglevel", "error"]
    subprocess.run(cmd, env=env, timeout=180)
    return os.path.exists(out)


def asr(wav):
    from faster_whisper import WhisperModel
    m = WhisperModel("small", device="cpu", compute_type="int8")
    segs, info = m.transcribe(wav, beam_size=5, vad_filter=False,
                              condition_on_previous_text=False)
    text = " ".join(s.text.strip() for s in segs).strip()
    return info.language, float(info.language_probability), text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="ok.ru 数字 id")
    ap.add_argument("--url", help="完整 ok.ru 链接（与 --id 二选一）")
    ap.add_argument("--at", type=int, default=2700, help="抽样起点（秒）")
    ap.add_argument("--secs", type=int, default=45)
    ap.add_argument("--lang-only", action="store_true", help="只报语种，不落 URL 文件")
    a = ap.parse_args()

    global VIDEO_ID
    url = a.url or "https://ok.ru/video/%s" % a.id
    VIDEO_ID = re.search(r"/video(?:embed)?/(\d+)", url).group(1)

    page = fetch_page(url)
    dur, streams = parse(page)
    print("id=%s" % VIDEO_ID)
    print("时长 %s 秒（%.1f 分钟）" % (dur, dur / 60) if dur else "时长未解析到")
    if not streams:
        sys.exit("没解析到 videos[]，页面可能有风控")

    for name, u in streams:
        print("  流 %-6s %s" % (name, u[:110]))

    best = streams[0][1]
    if not a.lang_only:
        open("ok_url.txt", "w", encoding="utf-8").write(best)

    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    if not grab(best, a.at, a.secs, wav):
        sys.exit("抽样失败（直链过期或代理出口变了，重取页面）")
    lang, prob, text = asr(wav)
    os.unlink(wav)
    print("抽样 @%ds 语种=%s (%.2f)" % (a.at, lang, prob))
    print("  ", text[:220])


if __name__ == "__main__":
    main()
