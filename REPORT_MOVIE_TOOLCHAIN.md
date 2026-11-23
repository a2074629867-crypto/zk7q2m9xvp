# REPORT_MOVIE_TOOLCHAIN — 影视找片工具链（可复制即跑）

配套文档：`G:/_setup/REPORT_MOVIE_FINDING.md`（经验结论与检索提示词）。
本文件只讲**怎么跑**：环境路径、每条任务链的命令模板、症状→原因→修法、端到端 SOP。
所有路径于 2026-11-08 18:55 在本机逐项核实存在；代理状态会变，开工前必须重新探测。
**下载类任务改走 `G:/_setup/REPORT_DOWNLOAD_TOOLCHAIN.md`**（BT / 视频站 / m3u8 / 配套字幕
三条链路自包含；本机 yt-dlp、aria2c、DRM 边界、字幕决策树都在那份）。
检索该域用 `rag.py search "下载 视频站 <具体术语>"`。

## A. 环境与路径清单

| 用途 | 路径 / 值 | 备注 |
|---|---|---|
| Python（托管） | `C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe` | 下称 `$PY` |
| ffmpeg | `/e/tool/ETS/ffmpeg/ffmpeg.exe` | 2020-04 build，**无 ffprobe** |
| 看流信息 | `"$FF" -hide_banner -i x.mkv 2>&1 \| grep -i "Stream\|Duration"` | 输出在 stderr |
| UnRAR | `C:/Program Files/WinRAR/UnRAR.exe` | 已装 |
| 中文字体 | `C:/Windows/Fonts/msyh.ttc` | drawtext 用 |
| **yt-dlp（下载主用）** | `/g/voice_lib/tools/yt-dlp.exe` | 2026.10.26，1755 extractor；命令模板见 `REPORT_DOWNLOAD_TOOLCHAIN.md` C 节 |
| **aria2c** | `/g/_setup/tools/aria2-1.37.0-win-64bit-build1/aria2c.exe` | 1.37.0，多线程直链 |
| pycryptodomex | 托管 Python 已装 3.24.0 | AES-128 HLS 原生解密要用 |
| MKV 时长解析 | `C:/Users/86178/WorkBuddy/2026-10-18-15-59-50/probe2.py` | EBML Duration 元素，无 ffmpeg 也能量 |
| 本地 RAG | `G:/_setup/rag/` | rag.py / facts.jsonl / db/rag.sqlite / eval_recall.py |
| RAG 规则 skill | `C:/Users/86178/.workbuddy/skills/project-rag/SKILL.md` | 改检索逻辑前必读 |
| 字幕 skill | `C:/Users/86178/.workbuddy/skills/chinese-subtitle-fetch/SKILL.md` | 三步链、PlayRes、环境坑 |
| 交付目录 | `G:/NEW MOVIE/` | 用户硬性指定 |
| 临时目录 | `D:/wb_tmp/` | **C 盘禁写**：下载/解压/缓存一律不落 C |
| HTTP 代理 | `http://127.0.0.1:7897` | curl `-x`；ffmpeg 用 `-http_proxy` |
| Clash API | `http://127.0.0.1:9097`，头 `Authorization: Bearer set-your-secret` | 策略组 `Now加速©️`（需 URL encode） |
| Bash 超时 | 默认 120s | 长任务显式传 `timeout`，否则被 SIGTERM |

## B. 开工前自检（整块复制，先看代理与环境）

```bash
PY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
FF="/e/tool/ETS/ffmpeg/ffmpeg.exe"
PX="http://127.0.0.1:7897"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

echo "--- 代理存活（429/正常 JSON 都算通，000 才算挂）---"
curl -s -x "$PX" https://ipinfo.io/json --max-time 10 | head -c 200; echo
echo "--- 出口 IP ---"
curl -s -x "$PX" https://ipinfo.io/json --max-time 10 | grep -o '"ip":[^,]*'
echo "--- Clash 策略组 ---"
curl -s -m 5 -H "Authorization: Bearer set-your-secret" http://127.0.0.1:9097/proxies | head -c 120; echo
echo "--- RAG 状态 ---"
cd /g/_setup/rag && "$PY" rag.py stats
echo "--- 磁盘余量（确认 C 盘别写）---"
df -h /c /d /g | head -5
```

**2026-11-06 记录代理 7897 未启动，11-08 实测已恢复。状态会变，别写死。**
代理挂了就直连 + 换搜索通道，别在同一条路上磨。

## C. 版本定性链（判剧场版 / 加长版 / 未删减）

```bash
PY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
FF="/e/tool/ETS/ffmpeg/ffmpeg.exe"

# 方式 1：有 ffmpeg 时（最常用，输出走 stderr）
cd "/g/NEW MOVIE"
"$FF" -hide_banner -i "movie.mkv" 2>&1 | grep -i "Duration\|Stream"

# 方式 2：不用 ffmpeg，直接解析 MKV 头部 Duration 元素
"$PY" "C:/Users/86178/WorkBuddy/2026-10-18-15-59-50/probe2.py"
```

判据（写进交付说明，别凭文件名）：
- Tree of Life 剧场版 `02:19:05`（139min）/ 加长版 `03:08:41`（188.7min）
- Her (2013) 唯一版 `02:05:50`（126min，R 级）
- Eternals (2021) `02:35:50`（157min）
- 真实时长不符 = 版本不对，字幕时间轴全部作废，先换源再配字幕

## D. 种子核验链（给磁力前的强制步骤）

```bash
# 1) 先搜，再定向抓（Google 是 JS 壳爬不了）
PX="http://127.0.0.1:7897"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
curl -s -x "$PX" -A "$UA" "https://lite.duckduckgo.com/lite/?q=<URL编码关键词>" \
  -o D:/wb_tmp/ddg.html -w "HTTP:%{http_code} SIZE:%{size_download}\n" --max-time 30

# 2) 拿该 hash 自己的文件列表：TorrentQuest / KAT / limetorrents 的 "Torrent File Content"
#    必须确认是：单 mkv / RAR 分卷(.r00~.rNN) / MP4 + sample
# 3) 只有确认单 mkv 才能给用户；否则换同名其它 hash

# 4) 生成磁力（HASH 换成 40 位 infohash）
magnet:?xt=urn:btih:<HASH>&dn=<文件名>&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce
```

别在 `itorrents.org` / `torrage.info` / `torrage.com` 拿 `.torrent` 上磨（本机代理下 502/301/404）。
索引站反爬时（1337x Cloudflare、limetorrents Access denied、TorrentFunk 502），
换定向 hash 搜索，取不到就**如实留空并给精确文件名让迅雷自己搜**，不编 hash。

## E. 字幕链（顺序就是坑的顺序）

```bash
PY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
FF="/e/tool/ETS/ffmpeg/ffmpeg.exe"
cd "/g/NEW MOVIE/<片源目录>"     # 必须先 cd：ffmpeg 打不开 G:/ 绝对路径

# 第 0 步：查内封轨（永远先做，答案常在这里）
"$FF" -hide_banner -i "movie.mkv" 2>&1 | grep -i "Subtitle"
# 看到 Subtitle: subrip + lang chi → 直接抽，天然对轴
"$FF" -hide_banner -loglevel error -y -i "movie.mkv" -map 0:16 -c:s srt "D:/wb_tmp/chi_16.srt"
# 英文用纯对白轨，不用 SDH（SDH 带 (MUSIC PLAYING)）
"$FF" -hide_banner -loglevel error -y -i "movie.mkv" -map 0:2  -c:s srt "D:/wb_tmp/eng_2.srt"

# 渲染验排版（必须 -copyts，否则出空图）
"$FF" -hide_banner -loglevel error -y -copyts -ss 1824 -i "movie.mkv" \
      -vf "ass=x.ass" -frames:v 1 "D:/wb_tmp/prev.png"
# 验空图：几张 PNG 字节数一模一样 = ass 没画上字，检查 -copyts 与该时刻有无 Dialogue 事件

# 无视频也能渲染（lavfi 造底图，r=1 秒出图）
"$FF" -f lavfi -i "color=c=0x1a1a1a:s=1920x1080:d=3010:r=1" \
      -vf "ass='x.ass'" -ss 2997.5 -frames:v 1 -y "D:/wb_tmp/out.png"
```

输出路径**必须**写 `D:/...`（正斜杠+盘符），ffmpeg 不认 `/d/...`。
中文/带空格路径：先 cd 进目录，再传纯文件名。
双语合并规则：中文 cue + 同片纯对白英文轨按时间重叠挂载；
**保留英文原 cue 内部换行**（不能 `re.sub(r'\s+',' ')` 压平）、**保留 `{\an8}`**。
交付永远留一份完整样式 ASS 母本，别只留 SRT。

## F. SubHD 三步下载链（可复制 bash，顺序错即失效）

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PX="http://127.0.0.1:7897"
SID="N2kG4z"          # /a/<6位字母数字>，不是纯数字
J="D:/wb_tmp/sh_$SID.jar"
rm -f "$J"

# 搜索页：链接是单引号！grep 用 "href='/a/" 别用双引号
curl -sL -x "$PX" -A "$UA" "https://subhd.tv/search/<URL编码片名>" -o D:/wb_tmp/s.html
grep -o "href='/a/[A-Za-z0-9]\{6\}'" D:/wb_tmp/s.html | sort -u

# ① 种 tk_ cookie
curl -s -x "$PX" -A "$UA" -c "$J" -b "$J" -e "https://subhd.tv/a/$SID" \
  -H "Content-Type: application/json" -X POST \
  -d "{\"sid\":\"$SID\"}" https://subhd.tv/api/sub/prepare-download
# ② 打开临时页（给下一步发许可证，缺这步必报「临时页面失效」）
curl -s -x "$PX" -A "$UA" -c "$J" -b "$J" -e "https://subhd.tv/a/$SID" \
  "https://subhd.tv/down/$SID" -o /dev/null
# ③ 取真实地址
curl -s -x "$PX" -A "$UA" -c "$J" -b "$J" -e "https://subhd.tv/down/$SID" \
  -H "Content-Type: application/json" -X POST -d "{\"sid\":\"$SID\"}" \
  https://subhd.tv/api/sub/down
# → {"success":true,"pass":true,"url":"https://dl.subhd.me/YYYY/MM/xxx.zip"}
```

解压（zip 内文件名 GBK）——**写成 .py 文件跑，别用 heredoc**：

```python
import zipfile, os
z = zipfile.ZipFile(r"D:/wb_tmp/x.zip")
out = r"D:/wb_tmp/ex"
os.makedirs(out, exist_ok=True)
for i in z.infolist():
    if i.is_dir():
        continue
    name = i.filename.encode("cp437").decode("gbk")   # 关键
    open(os.path.join(out, os.path.basename(name)), "wb").write(z.read(i))
```

RAR 包：`"C:/Program Files/WinRAR/UnRAR.exe" x -y -o+ x.rar D:/wb_tmp/ex/`。
站群 subhd.tv / .cc / .me / subhdtw.com 会整站 522，换域名没用，隔几小时再试。

## G. RAG 链（让其它 AI 取到经验 / 干完活写回）

```bash
PY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
cd G:/_setup/rag

"$PY" rag.py search "<锚点词>"          # 账本优先 + 原文片段；查不到换更具体的术语
"$PY" rag.py search "<锚点词>" --json    # 机器可读
"$PY" rag.py get <id>                   # 取某块全文
"$PY" rag.py fact search "<词>"          # 只搜硬结论账本
"$PY" rag.py up -t "短主题" -c "结论一句话，带数值/阈值" \
      -e "证据文件/脚本" --tags "找片,片源"   # 记结论 + 增量刷新索引
"$PY" rag.py index                      # 增量（按 mtime/size 跳过未变文件）
"$PY" rag.py stats
"$PY" eval_recall.py 5                  # 回归：配音域真实口径 top5 基线 25/25，低于即退步
"$PY" eval_recall_movie.py             # 回归：影视域 16 条提示词首条命中率（术语 8/8 / 口语 2/4 / 加域词 4/4）
"$PY" eval_recall_download.py          # 回归：下载域，查询模板 "下载 视频站 <具体术语>"
```

**构造查询的硬规矩（2026-11-08 实测）**：这个 RAG 原本是配音域记忆，
163 条账本里 142 条是 TTS。**纯口语查询会被配音域账本劫持**——
「为什么字幕对不上」首条返回的是配音域「字幕时间轴不等于说话人边界」。
实测首条命中率：术语型 8/8、口语型 2/4、**口语 + 域限定词 4/4**。
⇒ 万能模板 `rag.py search "找片 片源 <具体术语>"`，
术语从磁力 / infohash / mkv / SubHD / PlayRes / 剧场版 / RX580 / 内封轨 / 三步链里挑。
写回影视结论时 `--tags "找片,片源"` 保持域隔离。

红线：不要用 `--rebuild` 当日常操作（重算全部向量）；不要跳过 `eval_recall.py`
就宣称检索改好了；账本只写**结论**（数值、阈值、已证实不可行路径、被推翻的旧结论），
不写过程流水。影视域条目 tags 带 `找片`，与配音域隔离。
2026-11-08 灌入 21 条影视结论 + 2 份 REPORT_ 文档后测得 24/25（「委屈判据」未命中），
诊断是配音域本该有一条直接回答的账本结论却分散在 3 条里、且 `1−A` 全角减号
与判据半角 `1-A` 对不上；补「委屈音色选哪个」一条后**恢复 25/25 = 100%**。
改索引内容后必须复跑，掉了要修回来再交付。
索引源是 `rag.py` 里 `DEFAULT_SOURCES` 的固定 5 个路径，**不含本工作区**；
要被索引就把蒸馏文档放 `G:/_setup/*.md`（`REPORT_` 前缀吃 1.30 权威度加权）。

## H. 搜索通道与代理（先搜索，再定向抓）

| 通道 | 实测 | 用法 |
|---|---|---|
| `lite.duckduckgo.com/lite/?q=` | 200 纯 HTML，最好用 | `-x "$PX"`，直接扒标题+URL |
| `search.brave.com/search?q=` | 200 可用 | 备选 |
| Google | JS 跳转壳，爬不了 | 别用 |
| cn.bing.com | 200 但常无目标站 | 弱 |
| ok.ru 自带搜索 | 任何词都返回「Видео не нашлось」 | **不可用，别浪费轮次** |
| rarefilmm.com | 冷门片宝库 | 详情页内嵌 `//ok.ru/videoembed/<id>`，顺藤拿签名直链 |
| 国内 BT 站 1lou / yunpanb / mini4k | 只给 `.torrent` 附件 | WebFetch 能读完整 MediaInfo，是验时长最硬的证据 |
| mini4k `/torrents/<id>` | JS 渲染，curl 不通 | 别磨，直接给附件页链接 |

冷门片找源 SOP：DDG lite 一次命中 → 顺着 embed 拿 ID → ffmpeg 远程 Range 切段。

## I. 远程视频切段链（ok.ru 之类，不下整片）

```bash
FF="/e/tool/ETS/ffmpeg/ffmpeg.exe"
# 沙箱 http_proxy 默认指向 7104，ffmpeg 不认会卡死 → 必须显式指定
"$FF" -http_proxy "http://127.0.0.1:7897" \
      -user_agent "$UA" -referer "<页面URL>" \
      -ss 520 -to 783 -i "<签名直链>" \
      -c:v libx264 -crf 18 -preset veryfast -c:a aac "D:/wb_tmp/seg1.mp4"
# concat demuxer 拼接
"$FF" -f concat -safe 0 -i list.txt -c copy "D:/wb_tmp/joined.mp4"
# 拼接必现 Non-monotonic DTS，整体重编码一次修接缝
"$FF" -i "D:/wb_tmp/joined.mp4" -c:v libx264 -crf 18 -c:a aac "D:/wb_tmp/final.mp4"
```

`-ss/-to` 放在 `-i` **前**（seek 快）；长片段显式给 Bash 传 `timeout`，默认 120s 会被杀。
drawtext 的 `text=` 里冒号会被当滤镜分隔符 → 用 `textfile=`；
中文要 `fontfile=C\:/Windows/Fonts/msyh.ttc` 且 `export MSYS_NO_PATHCONV=1`。

## J. 症状 → 原因 → 修（速查）

| 症状 | 真因 | 修法 |
|---|---|---|
| 正则 `search` 恒 None，不报错 | bash heredoc 把 `\s` 替换成 `/s` | 含 `\s \d \n` 的 Python 一律 Write 成 .py 文件再跑 |
| `ffmpeg -i "G:/..."` 报 No such file | 本机 ffmpeg 不认 Windows 绝对路径 | 先 `cd` 进目录，传纯文件名 |
| 输出 PNG 与无字幕底图字节相同 | `-ss` 归零 PTS，ass 以为是 0 秒 | 加 `-copyts` |
| `grep 'href="/a/'` 一条都没有 | SubHD 结果卡片用单引号 | 改 `href='/a/` |
| `/api/sub/down` 报「临时页面失效」 | 漏了第 ② 步或 cookie jar 不一致 | 三步同 jar、严格按序 |
| zip 里全是乱码文件名 | 文件名是 GBK | `.encode('cp437').decode('gbk')` |
| 拉 ok.ru 卡死到被杀 | ffmpeg 不认沙箱默认 7104 代理 | 显式 `-http_proxy http://127.0.0.1:7897` |
| qBittorrent WebUI 404 无监听 | 8080 被 Steam webhelper 占 | 改 `qBittorrent.ini` `WebUI\Port=18080`，用完改回 |
| 长任务莫名中断 | Bash 默认 120s | 显式传 `timeout` |
| Python subprocess 调 ffmpeg 找不到 | 用了 `/c/...` 路径 | 改 `C:/...` |
| ASS 字号整体变大/沉底 | PlayRes 1920x804 用在 1080 高画面 | 换 PlayRes 1920x1080 的版本 |

## K. 磁盘 / 进程纪律

- **不把任何文件下载、解压、编译、缓存到 C 盘**（C 盘常年只剩 2–3G）。
  Go 构建固定 `D:\wb2api-build`，并显式指定 `GOROOT`/`GOPATH`/`GOCACHE` 到 D 盘，
  否则缓存默认写 `%LOCALAPPDATA%`（C 盘）。
- 其它可用盘：D ~59G / E 145G / F 153G / G 761G。
- 临时产物一律 `D:/wb_tmp/`，交付完立刻清理；不留下半成品。
- 程序纪律：限时 + 后台运行 + 看门狗防卡死；**抓完立即关浏览器**（用户明确要求）。
- 未经同意不下载、不代为添加种子；下载位置固定 `G:\NEW MOVIE\`。

## L. 端到端 SOP（一个找片任务，按顺序跑）

1. `rag.py search "找片 片源 <片名/锚点词>"` → 先看这条线已有的结论，别重复踩坑；
   下载/视频站/配字幕任务改查 `rag.py search "下载 视频站 <具体术语>"`，
   完整链路见 `REPORT_DOWNLOAD_TOOLCHAIN.md`（A–M 节）
2. 版本谱系定性：查发行过几个剪辑版 → 定「真实时长」判据
3. DDG lite 搜源 → 索引站核 **该 hash 自己的文件列表** → 确认单 mkv
4. 出磁力 / `.torrent` 附件入口，附档位对比 + 避坑名单，清单落盘
5. 用户下完 → `cd` 进目录，`ffmpeg -i` 量真实时长 + 列 Subtitle 轨
6. 有 chi 内封轨 → 直接抽 + 双语合并；没有 → SubHD 三步链
7. 渲染验排版（`-copyts`）→ 用户校准一句台词的实际秒数 → 恒定偏移重排
8. 交付：与视频同名自动挂载 + 备用时间轴 + 说明.txt；ASS 母本必留
9. 新的硬结论 `rag.py up` 写回账本 → `rag.py index` → `eval_recall.py 5` 确认基线不退
10. 清 `D:/wb_tmp/`，写当日 memory，关浏览器
