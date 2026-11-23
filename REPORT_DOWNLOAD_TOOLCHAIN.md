# REPORT_DOWNLOAD_TOOLCHAIN — 下载总工具链（BT / 视频站 / 配套字幕）

本文件专讲**「把东西弄到手」**：BT 种子、各大视频网站、m3u8/HLS 直链，
以及**下完之后怎么找对应字幕**。所有命令于 2026-11-08 19:14–19:25 在本机逐项实测。
只做 `--simulate -F` / `--list-subs` 探测，**未实际下载任何影片**。

配套文档（三份互相引用，都在 RAG 索引源 `G:/_setup/*.md`，`REPORT_` 前缀吃 1.30 权威度）：
- `G:/_setup/REPORT_MOVIE_FINDING.md` —— 版本定性 / 片源选择 / 检索锚点词（**结论**）
- `G:/_setup/REPORT_MOVIE_TOOLCHAIN.md` —— 影视找片 A–L 节（**找片命令**）
- 本文件 —— **下载与配字幕**（下载链路自包含，不依赖前两份也能跑）

检索本域经验时**必须带域限定词**：`rag.py search "下载 视频站 <具体术语>"`。
理由见 L 节（这个 RAG 原本是配音域，纯口语会被 TTS 账本劫持）。

**索引源已含三个下载域 skill**（2026-11-08 补）：`video-download-toolchain`（路由）、
`chinese-subtitle-fetch`（字幕链）、`okru-video-download`（三头与码率表）。
此前只有报告可检索，问「这个视频怎么下」拿不到「先判断走哪条链」这层分发逻辑。

---

## A. 本机下载工具清单（2026-11-08 实测，别再全盘找）

| 用途 | 路径 / 值 | 备注 |
|---|---|---|
| **yt-dlp 主用** | `/g/voice_lib/tools/yt-dlp.exe` | **2026.10.26 最新**，1755 个 extractor |
| yt-dlp 备用 exe | `/g/Python310/Scripts/yt-dlp.exe` | 2026.10.21 |
| yt-dlp pip 包版 | `$PY -m yt_dlp` | 2026.08.19，**只在需要装插件时用**（见 D3） |
| aria2c | `/g/_setup/tools/aria2-1.37.0-win-64bit-build1/aria2c.exe` | 1.37.0，多线程/断点 |
| ffmpeg | `/e/tool/ETS/ffmpeg/ffmpeg.exe` | git-2020-04-26，**无 ffprobe**；有 libx264 / aac；yt-dlp 合并与切段都要它 |
| Python | `C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe` | 下称 `$PY`；已装 `pycryptodomex 3.24.0`（**AES-128 HLS 解密要用**）、requests、lxml |
| curl | `C:/Windows/System32/curl.exe` | 直链/页面抓取 |
| UnRAR | `C:/Program Files/WinRAR/UnRAR.exe` | RAR 分卷种子 |
| HTTP 代理 | `http://127.0.0.1:7897` | yt-dlp 用 `--proxy`，ffmpeg 用 `-http_proxy`，curl 用 `-x` |
| Clash API | `http://127.0.0.1:9097` + `Authorization: Bearer set-your-secret` | 换节点用 |
| **交付目录** | `G:/NEW MOVIE/` | 用户硬性指定 |
| **临时 / 缓存目录** | `D:/wb_tmp/` | **C 盘禁写**：yt-dlp 缓存、分片、中间文件全部落 D |
| Bash 超时 | 默认 120s | 长下载显式传 `timeout`，或后台跑 + 看门狗 |

**代理状态会变**：11-06 记录 7897 未启动，11-08 恢复。探测时 `ipinfo.io` 返回 429（限流）
也算通，**只有 HTTP 000 / 连接超时才算挂**。archive.org 的 `-F` 实测能列出格式即证明链路通。

---

## B. 开工自检（整块复制）

```bash
PY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
Y="/g/voice_lib/tools/yt-dlp.exe"
FF="/e/tool/ETS/ffmpeg/ffmpeg.exe"
AR="/g/_setup/tools/aria2-1.37.0-win-64bit-build1/aria2c.exe"
PX="http://127.0.0.1:7897"
mkdir -p D:/wb_tmp/ytdlp_cache D:/wb_tmp/ytdlp_temp

echo "--- 版本 ---"
"$Y" --version; "$AR" --version | head -1; "$FF" -version 2>&1 | head -1
echo "--- 代理（429/正常 JSON 都算通，000 才挂）---"
curl -s -x "$PX" https://ipinfo.io/json --max-time 10 | head -c 160; echo
echo "--- 探测通道（只列格式，不下载）---"
timeout 60 "$Y" --no-warnings --proxy "$PX" --simulate -F \
  "https://archive.org/details/BigBuckBunny_328" 2>&1 | tail -8
echo "--- 磁盘余量（确认 C 盘别写）---"
df -h /c /d /g | head -5
```

自检预期：archive.org 返回 3 档（`427x240 mp4 41.31MiB` / `544x304 ogv 46.46MiB` /
`1280x720 avi 381.90MiB`）。列不出格式 = 代理或 extractor 有问题，先修通道再谈下载。

---

## C. 通用下载模板（yt-dlp，可复制即跑）

### C0 铁律：先探测，再下载

```bash
Y="/g/voice_lib/tools/yt-dlp.exe"; PX="http://127.0.0.1:7897"
# ① 列格式（不下片）
"$Y" --proxy "$PX" --simulate -F "<URL>"
# ② 列字幕（不下片）
"$Y" --proxy "$PX" --list-subs --simulate "<URL>"
# ③ 确认档位后，才去掉 --simulate 真下
```

### C1 主命令（每条都不能省的理由写在注释里）

```bash
Y="/g/voice_lib/tools/yt-dlp.exe"
FF="/e/tool/ETS/ffmpeg/ffmpeg.exe"
PX="http://127.0.0.1:7897"

"$Y" \
  --proxy "$PX" \
  --ffmpeg-location "$FF" \                # PATH 里没有 ffmpeg，不写合并/切段必失败
  --cache-dir "D:/wb_tmp/ytdlp_cache" \    # 默认写 C 盘 %APPDATA%，触犯磁盘红线
  --ignore-config \                        # 避免本机遗留配置干扰
  -P "home:G:/NEW MOVIE" \                 # 成品落交付目录
  -P "temp:D:/wb_tmp/ytdlp_temp" \         # 分片/中间文件落 D 盘
  -o "%(title)s [%(id)s].%(ext)s" \
  -f "bv*[height<=1080]+ba/b[height<=1080]" \
  --merge-output-format "mp4/mkv" \
  --continue --no-overwrites \
  --retries 10 --fragment-retries 10 \
  --concurrent-fragments 4 \
  --console-title \
  "<URL>"
```

- `-f "bv*+ba/b"` = 最佳分离视频 + 最佳音频，失败回退到合并流；`/b` 不能省。
- `-o` 若写绝对路径，`-P` 会被忽略（官方明确说明）。
- `--download-sections "*10:15-inf"` 只下片段，**依赖 ffmpeg**；本机实测
  `--download-sections "*0:10-0:20" --ffmpeg-location "$FF"` 输出 `Downloading 1 time ranges: 10.0-20.0`。
- 只下音频：`-x --audio-format m4a`；只列不落盘：加 `--simulate`。

### C2 加速与限速（别把两件事混了）

```bash
# aria2c 只接管 http/ftp 直链；dash/m3u8 分片不走它
"$Y" --downloader aria2c \
     --downloader "dash,m3u8:native" \
     --downloader-args "aria2c:-x8 -s8 -k1M" "<URL>"

# 分片并发是另一个开关（-N），默认 1
"$Y" -N 8 --fragment-retries infinite "<URL>"

# 限速 / 防封（批量抓站时必带）
"$Y" -r 4M --sleep-requests 1 --sleep-interval 5 --max-sleep-interval 10 "<URL>"

# 批量：下载归档，重跑自动跳过已完成的 ID
"$Y" --download-archive "D:/wb_tmp/ytdlp_done.txt" -a - < urls.txt
```

### C3 输出与元信息

`--write-info-json`（留档）、`--write-thumbnail`、`--embed-subs`（仅 mp4/webm/mkv）、
`--embed-metadata`、`--print after_move:filepath`（拿后处理后的真实文件名，
官方注明 `-o` 的名字可能因合并而变化）。

---

## D. 各站点实测与特例（2026-11-08，全部只做 format 探测）

### D1 本机 extractor 覆盖（`/g/voice_lib/tools/yt-dlp.exe --list-extractors`，共 1755 个）

| 站点 | extractor 数 | 实测 |
|---|---:|---|
| YouTube | 20 | ✅ `jNQXAC9IVRw` 完整列出 144p/240p（含 AV1/VP9），默认 `395+251` |
| Vimeo | 11 | 列表支持，未逐站实测 |
| TikTok / Twitch | 7 / 7 | 列表支持；`tiktok:effect/sound/tag`、`instagram:user` 官方标 Currently broken |
| Twitter/X | 6 | 列表支持 |
| VK | 5 | 列表支持；`vk` 系标 netrc machine |
| Dailymotion | 4 | 列表支持 |
| Weibo / Youku / iqiyi / Douyin | 3 / 2 / 1 / 1 | 列表支持 |
| BiliBili | 多条 | ✅ 实测 |
| Odnoklassniki (ok.ru) | 1 | ✅ 实测，**有坑，见 D2** |
| archive.org | 1（小写名） | ✅ 实测，自检基准 |
| generic | 3 | 未列出的站仍可能靠 embed / generic extractor 走通 |

官方文档原话：*「Not all sites listed here are guaranteed to work … The only reliable way to
check if a site is supported is to try it.」* ⇒ **别信列表，一律先 `--simulate -F`。**

### D2 ok.ru：yt-dlp 一键 ≠ 最高码率（重要）

对之前手工剪过的 Is-slottet `https://ok.ru/video/9447644727974` 实测：

- yt-dlp 一键列出 20+ 档，最高 `hls-1778 1194x720 1778k` / `webm-4 1194x720 1884k`；
  `mobile / lowest / low / sd / hd` 这些 mp4 档解析成 `unknown` 无分辨率。
- 而 `okru-video-download` skill 的手工解析能拿到 **`full` 1920x1080 / 5.04 Mbps**。

⇒ **要最高画质，走手工三头，不要用 yt-dlp 默认档**：

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36 Edg/153.0.4234.32"
ID=9447644727974
curl -sL --max-time 40 -x "$PX" -A "$UA" -H "Accept-Language: ru-RU,ru;q=0.9" \
  -o D:/wb_tmp/ok.html "https://ok.ru/video/$ID"
# 解析：html.unescape → replace('\\u0026','&') → "videos":[…] 取 name=='full'；或 hlsManifestUrl
# 下流时三个头必须齐，且不要加 -L（跟随重定向反而 400）
curl --max-time 1800 -x "$PX" -A "$UA" \
  -H "Referer: https://ok.ru/video/$ID" -H "Origin: https://ok.ru" \
  -o "G:/NEW MOVIE/out.mp4" "$FULL_URL"
```

三头缺一即 400：`User-Agent` 现代浏览器 / `Referer` / `Origin`。签名带 `srcIp` 与 `expires`（约 24h），
取页面和下载要在同一次会话连续做完；Python `requests` 走 7897 常报 502，**直接用 curl**。
完整排查顺序见 `C:/Users/86178/.workbuddy/skills/okru-video-download/SKILL.md`。

### D3 B站：无 cookie 也能 1080p，但字幕是弹幕

对 `https://www.bilibili.com/video/BV1GJ411x7h7` 实测：

- 无 cookie 即列出 `30016/30032/30064/30080`（360p/480p/720p/**1080p** AVC）、
  `100109~100026`（HEVC / AV1）与 `30216/30232/30280` 音轨，默认选 `100026+30280`（AV1 1080p）。
- `--list-subs` 会提示 `Format(s) 1080P 高清 are missing; you have to become a premium member
  to download them. Use --cookies-from-browser or --cookies` ⇒ **1080P 高码率 / 4K / 杜比仍需大会员 cookie**。
- **可用字幕只有 `danmaku xml`（弹幕），不是对白字幕**。这就是「下完视频找不到对应字幕」的高发点：
  视频站自带的「字幕」常常是弹幕或 AI 自动轨，不能当译本用，得走 G 节外站链路。

```bash
# 需要会员档时（Chrome/Edge 已登录）
"$Y" --cookies-from-browser "edge" --proxy "$PX" -F "<B站URL>"
# 或导出 netscape cookies.txt
"$Y" --cookies "D:/wb_tmp/cookies.txt" "<B站URL>"
```

### D4 YouTube：本机实测可用，失败才按 EJS → PO token 顺序排

本机 `2026.10.26` exe 对公开视频 `jNQXAC9IVRw` **正常列出全部格式**，
没有出现社区说的「只剩 storyboard 图」。所以**别一上来就装一堆插件**。
只有症状出现时才按下面顺序（社区定稿解法，按「最后解决了没有」筛过）：

1. `Only images are available for download` / 只剩 `sb*` 图、或格式大量缺失
   ⇒ 缺 `yt-dlp-ejs` + JS runtime。装 `yt-dlp-ejs`，并给 `--js-runtimes deno:<path>`
   （官方默认只启用 deno，node/quickjs/bun 要显式指定）。
2. **插件发现坑**：standalone zipapp exe **不认 `pip install --user` 装的插件**。
   要插件生效必须用 **pip 版 yt-dlp**（`$PY -m yt_dlp`）让两者共享 site-packages；
   本机 pip 版是 2026.08.19，需要时再更新（**装到 D 盘独立 venv，不要污染 C 盘 venv**）。
3. 仍 403 / 明确报 PO token ⇒ 才装 `bgutil-ytdlp-pot-provider` 并跑它的服务
   （默认 `127.0.0.1:4416`），自定义地址用
   `--extractor-args "youtubepot-bgutilhttp:base_url=http://127.0.0.1:8080"`。
4. 只在**需要账号的内容**（年龄限制/会员/私享）才加 `--cookies`，别写进全局配置；
   官方警告账号用于 yt-dlp 可能被临时或永久封禁。

### D5 DRM 边界（源码一手证据，别听二手文章）

`yt_dlp/downloader/hls.py` 的 `can_download()`：

```python
UNSUPPORTED_FEATURES += [r'#EXT-X-KEY:METHOD=(?!NONE|AES-128)']  # 只排除非 AES-128
def _has_drm(manifest):   # skd:// / KEYFORMAT=com.apple.streamingkeydelivery
    ...                   # KEYFORMAT=com.microsoft.playready / #EXT-X-FAXS-CM:
```

⇒ **标准 AES-128 HLS 是支持的**：`#EXT-X-KEY:METHOD=AES-128` 时会解析 key URI / IV，
用 pycryptodomex（本机 3.24.0 已装）或 ffmpeg 解密。网上「yt-dlp 不支持 AES-128」的说法**是错的**。
⇒ **Widevine / PlayReady / FairPlay 一律不支持**：`This format is DRM protected;
Try selecting another format with --format or --allow-unplayable-formats`。
`--allow-unplayable-formats` 只会让你下到**加密碎片**，不是解密手段。

**红线：Netflix / Disney+ / Prime Video / Hulu / Max / Apple TV+ / Crunchyroll 等订阅流媒体不碰**，
既下不动也不该绕。要这些片子的收藏版，回到 BT/片源层（F 节）找已发行的 WEB-DL/REMUX。
标准 AES-128 且 key URI 可直接 GET 的公开 m3u8 才在能力范围内。

### D6 ok.ru 两个新坑（2026-11-08 22:00 实测，做角色音色时踩的）

**① 直链比 HLS 快 20 倍。** 视频页 HTML 里有带签名的 `"videos":[{"name":"hd","url":"https://vdNNN.okcdn.ru/?...sig=..."}]`，
curl 带齐 UA/Referer/Origin 三头直下 **1.3–1.9 MB/s**；yt-dlp 默认吃 m3u8 分片只有 **70 KB/s**
（95 分钟片子 ETA 1.5 小时）。直链绑 `srcIp`（= 代理出口）与 `expires`（约 24h），
**取页面和下载必须在同一次会话里连续做完**，Range 断点可用（206）。

```bash
# 一条命令出「时长 + 直链 + 这条片到底是什么语言」
G:/Python310/python.exe ok_probe.py --url "https://ok.ru/video/<id>" --at 2700
```

**② 大量条目是 VF 法语配音，标题里的 "VF/VO" 都不能当证据。**
实测 Son of Rambow（id 4488237091576）时长 5733s 与正片 95 分钟完全吻合、画质也好，
抽 45s 跑 ASR → **fr 0.97**，全程法语对白。拿它去切英国男孩的音色 = 换了一个国家的演员。
**规矩：任何 ok.ru 素材进库前必须抽 45s 跑 ASR 判语种**，`ok_probe.py` 已内置。
另：搜到的 Another Year 条目（22614774201）页面含 `удален/недоступ`，是已删除的死链。

---

## E. HLS / m3u8 直链与远程切段（不下整片）

```bash
Y="/g/voice_lib/tools/yt-dlp.exe"; FF="/e/tool/ETS/ffmpeg/ffmpeg.exe"; PX="http://127.0.0.1:7897"

# E1 直接吃 m3u8（generic extractor 常能走通）
"$Y" --proxy "$PX" --ffmpeg-location "$FF" --cache-dir "D:/wb_tmp/ytdlp_cache" \
     -N 8 -f "bv*+ba/b" --merge-output-format mkv -o "G:/NEW MOVIE/out.%(ext)s" "<M3U8_URL>"

# E2 带鉴权头的 m3u8（--add-header 可多次）
"$Y" --add-header "Referer:https://site/" --add-header "Origin:https://site" "<M3U8_URL>"

# E3 只切一段：yt-dlp 版
"$Y" --proxy "$PX" --ffmpeg-location "$FF" --download-sections "*0:08:40-0:13:03" \
     -f "bv*+ba/b" --force-keyframes-at-cuts -o "G:/NEW MOVIE/seg.%(ext)s" "<URL>"

# E4 只切一段：ffmpeg 远程 Range 版（ok.ru 等签名直链，is-slottet 用的就是这条）
"$FF" -http_proxy "$PX" -user_agent "$UA" -referer "<页面URL>" \
      -ss 520 -to 783 -i "<签名直链>" \
      -c:v libx264 -crf 18 -preset veryfast -c:a aac "D:/wb_tmp/seg1.mp4"
# 拼接 + 修接缝（concat 后必现 Non-monotonic DTS，整体重编码一次）
"$FF" -f concat -safe 0 -i "D:/wb_tmp/list.txt" -c copy "D:/wb_tmp/joined.mp4"
"$FF" -i "D:/wb_tmp/joined.mp4" -c:v libx264 -crf 18 -c:a aac "G:/NEW MOVIE/final.mp4"
```

- `-ss/-to` 放在 `-i` **前**（seek 快）；长片段显式给 Bash 传 `timeout`（默认 120s 会被杀）。
- **ffmpeg 拉远程必须显式 `-http_proxy`**：沙箱默认 7104，ffmpeg 不认会卡死到 SIGTERM。
- 输出路径写 `D:/...` 或 `G:/...`（盘符+正斜杠），ffmpeg 不认 `/d/...`；
  输入中文/空格路径先 `cd` 进目录传纯文件名。
- 手工拼多段时 `list.txt` 每行 `file 'D:/wb_tmp/segN.mp4'`。

---

## F. BT / 磁力层（要点，完整版见 REPORT_MOVIE_TOOLCHAIN.md D 节）

| 环节 | 硬规矩 |
|---|---|
| 挑源 | 用户用**迅雷**，有云端缓存，**0 做种照样能下** ⇒ 做种数不是筛选标准，按规格排 |
| 交付前 | 必须核实**该 infohash 自己的文件列表**：分 **单 mkv** / **RAR 分卷 `.r00~.rNN`** / **MP4 + sample** 三类。同名同体积 ≠ 同一种子（SPARKS `1DFA3F51…` 是 101 个分卷，`A33CAE25…` 才是单 mkv） |
| 入口 | 国内站（1lou / yunpanb / mini4k）常只给 `.torrent` 附件，对迅雷命中率比裸磁力高；漫威/迪士尼磁力可能被判「违规资源」，此时**换方式不换源** |
| 磁力模板 | `magnet:?xt=urn:btih:<40位HASH>&dn=<名>&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce` |
| qBittorrent | WebUI 8080 被 Steam webhelper 占时，改 `qBittorrent.ini` `WebUI\Port=18080`，用完改回 |
| 解压 | RAR 分卷：`UnRAR.exe x -y -o+ x.rar D:/wb_tmp/ex/`；字幕 zip 内文件名是 GBK，见 G3 |
| 假种 | 看扩展名，`.exe` 一律不碰；剧集标 `S01 Complete` 先查播出表 |
| 拿不到 `.torrent` | `itorrents.org` / `torrage.info` / `torrage.com` 在本机代理下 502/301/404，**别磨**，换索引站文件列表页 |

---

## G. 找对应字幕（下完之后的关键链路）

### G0 决策树（顺序就是成本顺序，别跳步）

```
视频站随片字幕  →  ① --list-subs（含自动字幕/弹幕，先判断是不是真对白）
        ↓ 没有或不合用
内封字幕轨      →  ② ffmpeg -i 列 Subtitle 轨（WEB-DL 常保留官方多语字幕，天然对轴）
        ↓ 没有
外站字幕        →  ③ SubHD 三步链 / 其它站（按片源版本+时长挑）
        ↓ 拿到
匹配校验        →  ④ 时长/剪辑版/画幅(PlayRes)/帧率 四项对齐 + 时间轴校准
        ↓
交付            →  ⑤ 与视频同名自动挂载 + 说明.txt + 保留 ASS 母本
```

### G1 视频站随片字幕（yt-dlp 官方参数，已核拼写）

```bash
Y="/g/voice_lib/tools/yt-dlp.exe"; PX="http://127.0.0.1:7897"

# 先看有什么（不下片）
"$Y" --proxy "$PX" --list-subs --simulate "<URL>"
# 下人工字幕 + 自动字幕，转 srt/ass
"$Y" --proxy "$PX" --write-subs --write-auto-subs \
     --sub-langs "zh.*,en.*" --sub-format "srt/ass/best" \
     --convert-subs "srt" --skip-download "<URL>"
# 连片一起下并内封字幕（仅 mp4/webm/mkv）
"$Y" --proxy "$PX" --write-subs --sub-langs "all,-live_chat" --embed-subs "<URL>"
```

`--sub-langs` 支持正则与排除（`"en.*,ja"`、`"all,-live_chat"`）。
**实测**：YouTube `jNQXAC9IVRw` 自动字幕给出 `vtt / srt / ttml / json3 / srv1-3`，还有
`ab-en`（Abkhazian from English）这类**翻译轨**——翻译轨不是中文原字幕，别误当译本。
B站 `BV1GJ411x7h7` 只有 `danmaku xml`（弹幕），**不能当对白字幕用**。
⇒ 视频站字幕多为机翻/ASR/弹幕，要正经中英双语仍走 G2/G3。

### G2 内封轨第 0 步（最容易被跳过，答案常在这里）

```bash
FF="/e/tool/ETS/ffmpeg/ffmpeg.exe"
cd "/g/NEW MOVIE/<片源目录>"          # 先 cd：ffmpeg 打不开 G:/ 绝对路径
"$FF" -hide_banner -i "movie.mkv" 2>&1 | grep -i "Stream\|Duration"
# 看到 Subtitle: subrip + lang chi → 直接抽，天然对轴
"$FF" -hide_banner -loglevel error -y -i "movie.mkv" -map 0:16 -c:s srt "D:/wb_tmp/chi.srt"
```

Eternals TEPES 版实测内封 16 条字幕轨，含 0:15 港繁 / 0:16 简中 / 0:17 台繁，
全是迪士尼官方译本，**在 SubHD/zimuku/lwltv 绕十几轮之前，一次 `ffmpeg -i` 就能解决**。
规律：WEB-DL（DSNP/AMZN/iTunes/MAX）常保留全部官方字幕轨；BluRay 压制组版常只带双语 ASS 或不带。
做双语用**纯对白英文轨**（不是 SDH，SDH 带 `(MUSIC PLAYING)`），按时间重叠挂载，
**保留英文 cue 内部换行**与 `{\an8}` 置顶标记，别用 `re.sub(r'\s+',' ')` 压平。

### G3 外站字幕（SubHD 三步链，完整 curl 见 REPORT_MOVIE_TOOLCHAIN.md F 节）

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
SID="N2kG4z"    # /a/<6位字母数字>，不是纯数字
J="D:/wb_tmp/sh.jar"; rm -f "$J"
curl -s -x "$PX" -A "$UA" -c "$J" -b "$J" -e "https://subhd.tv/a/$SID" \
  -H "Content-Type: application/json" -X POST -d "{\"sid\":\"$SID\"}" \
  https://subhd.tv/api/sub/prepare-download                      # ① 种 tk_ cookie
curl -s -x "$PX" -A "$UA" -c "$J" -b "$J" -e "https://subhd.tv/a/$SID" \
  "https://subhd.tv/down/$SID" -o /dev/null                       # ② 发许可证（缺必报「临时页面失效」）
curl -s -x "$PX" -A "$UA" -c "$J" -b "$J" -e "https://subhd.tv/down/$SID" \
  -H "Content-Type: application/json" -X POST -d "{\"sid\":\"$SID\"}" \
  https://subhd.tv/api/sub/down                                  # ③ 取 dl.subhd.me 真址
```

- 搜索页链接是**单引号** `href='/a/<slug>'`；详情页 slug 6 位字母数字。
- zip 内文件名 GBK → `name.encode('cp437').decode('gbk')`（写成 .py 文件跑，别用 heredoc）。
- 站群 `subhd.tv/.cc/.me/subhdtw.com` 会整站 522，换域名没用，隔几小时再试。
- 其它源可用性（`chinese-subtitle-fetch` skill 实测）：`assrt.net` SSL 断、`zimuku` 404、
  `subf2m` 中文覆盖差（常只有 BG code）、`subdl` 403、`opensubtitles` API 302、
  `lwltv` 有货但下载口被 Cloudflare Turnstile 拦（POST 405）。

### G4 匹配校验（字幕「对不上」的四类根因）

| 现象 | 根因 | 修法 |
|---|---|---|
| 全片恒定偏几秒 | 片头厂标长度不同 | 单校准点法：用户报「第一句 Brother 在 1:28」、原字幕 0:46.08 → **+41.92s 全片平移** |
| 偏移随时间线性增长 | 帧率差（PAL 4%，`24/25=0.960`） | 按 `t2 = 0.960×t1 + offset` 重映射，不是平移 |
| 偏移有台阶 | 加长版 / 删减版，剪辑结构不同 | **换字幕**，别硬调轴；先 `ffmpeg -i` 量真实时长定性 |
| 字号变大/沉底 | ASS `PlayRes 1920x804` 用在 1080 高画面（×1.34） | 换 `PlayRes 1920x1080` 的版本 |

渲染验排版（**必须 `-copyts`**）：

```bash
"$FF" -hide_banner -loglevel error -y -copyts -ss 1824 -i "movie.mkv" \
      -vf "ass=x.ass" -frames:v 1 "D:/wb_tmp/prev.png"
```

不加 `-copyts` 时 `-ss` 归零 PTS，ass 以为还在 0 秒，输出 PNG 与无字幕底图**字节完全相同**。
几张图大小一模一样 = 全是空图。选时间点要写脚本找「所有候选 ASS 都有 Dialogue」的时刻。
片头不确定时**同时给原版 + 偏移备用两套时间轴**，说明里写「开场第一句在几分几秒」。

### G5 交付命名

`<视频名>.ass` / `<视频名>.srt` 与视频同目录 → PotPlayer / mpv / VLC 自动挂载。
前缀带 `【备用】` / `变体` 的不会自动加载，正好用来放备选。
第三方 ASS 合集另建子目录按 `01 xx - 说明.ass` 排位，说明里写 PlayRes / 样式数 / 事件数 /
发布人 / 适合片源；特效字幕常带**必须安装的 .ttf**。**永远保留一份完整样式 ASS 母本**，
只留 SRT 会在修订时丢光样式。

---

## H. 验收（下完必做的三件事）

1. **真实时长**：`"$FF" -hide_banner -i x.mkv 2>&1 | grep -i Duration`（无 ffprobe）；
   或用 `C:/Users/86178/WorkBuddy/2026-10-18-15-59-50/probe2.py` 解析 MKV Duration 元素。
   Her = `02:05:50`、Eternals = `02:35:50`、Tree of Life 剧场版 = `02:19:05` / 加长版 `03:08:41`。
   **时长不符 = 版本不对，字幕时间轴全部作废，先换源。**
2. **流与字幕轨**：`grep -i "Stream\|Subtitle"`，确认音轨是原声、有没有 chi 内封轨。
3. **文件形态**：`ls -la` 看是不是单 mkv、有没有残留 `.part` / `.ytdl` / `.xltd`；
   假种看扩展名（`.exe` 不碰）；RAR 分卷用 UnRAR 解到 D 盘。

---

## I. 症状 → 原因 → 修（下载类速查）

| 症状 | 真因 | 修法 |
|---|---|---|
| `-F` 卡住 / HTTP 000 | 7897 代理没启动 | 先跑 B 节自检；挂了就直连 + 换通道，别磨 |
| 合并后没声音 / 只有一条轨 | ffmpeg 不在 PATH | 每条命令带 `--ffmpeg-location "$FF"` |
| `--download-sections` 不可用 | 同上，官方注明 Needs ffmpeg | 同上 |
| 下完发现 C 盘被写 | yt-dlp 默认缓存/临时在 `%APPDATA%` | `--cache-dir D:/...` + `-P temp:D:/...` |
| `Only images are available for download` | 缺 `yt-dlp-ejs` + JS runtime | 装 EJS，`--js-runtimes deno:<path>`；要用 **pip 版** yt-dlp 才认插件 |
| 装了 EJS 仍不生效 | standalone zipapp 不认 `--user` 插件 | 换 `$PY -m yt_dlp` 与插件共享 site-packages |
| YouTube 403 / 报 PO token | 部分 client 要令牌 | 先更新 + `--verbose` 复现 → 需要账号才 cookie → 真报 PO token 才装 bgutil provider |
| `This format is DRM protected` | Widevine/PlayReady/FairPlay | **不碰**，回到 BT/WEB-DL 层；`--allow-unplayable-formats` 只会下到加密碎片 |
| m3u8 下完播不了 | 误判成「yt-dlp 不支持 AES-128」 | 标准 AES-128 是支持的；检查 key URI 是否需鉴权，补 `--add-header` / cookie |
| B站 `1080P 高清 are missing` | 高码率档要大会员 | `--cookies-from-browser edge` 或 `--cookies` |
| B站 字幕只有 `danmaku xml` | 那是弹幕不是对白字幕 | 走 G2/G3 找正经译本 |
| ok.ru 只到 720p | yt-dlp 默认档拿不到 `full` | 走 D2 手工三头解析 `videos[].url['full']` |
| ok.ru 直链 400 | 缺 `Origin` / UA 是 IE 时代 / 加了 `-L` | 三头齐、现代 UA、去掉 `-L`；签名过期就重抓页面 |
| ffmpeg 拉远程卡死到 SIGTERM | 不认沙箱默认 7104 代理 | 显式 `-http_proxy http://127.0.0.1:7897` |
| concat 后 `Non-monotonic DTS` | 分段时间戳不连续 | 整体重编码一次修接缝（E4） |
| SubHD 报「临时页面失效」 | 漏第 ② 步 / cookie jar 不一致 | 三步同 jar、严格按序 |
| zip 里中文乱码 | 文件名 GBK | `.encode('cp437').decode('gbk')` |
| 正则恒 None 不报错 | bash heredoc 把 `\s` 换成 `/s` | 含 `\s \d \n` 的 Python 一律 Write 成 .py 再跑 |
| ffmpeg `-i "G:/..."` 报 No such file | 本机 ffmpeg 不认 Windows 绝对路径 | 先 cd 进目录传纯文件名；输出写 `D:/...` |
| 长任务莫名中断 | Bash 默认 120s | 显式传 `timeout` / 后台跑 + 看门狗 |
| 渲染字幕 PNG 字节全相同 | `-ss` 归零 PTS | 加 `-copyts` |
| qB WebUI 无监听 | 8080 被 Steam webhelper 占 | 改端口 18080，用完改回 |

---

## J. 端到端 SOP（三条线，按顺序跑）

**J1 视频站下载线**
1. `rag.py search "下载 视频站 <站名/术语>"` 先看已有结论
2. B 节自检（代理 / 版本 / 探测通道）
3. `--simulate -F` 列格式 + `--list-subs` 列字幕，**确认档位与字幕是否真对白**
4. 按 D 节站点特例决定：一键 yt-dlp / 手工三头 / cookie / 换源
5. C1 主命令下载（必带 `--ffmpeg-location` / `--cache-dir` / `-P temp:D:`）
6. H 节验收 → G 节配字幕 → 清 `D:/wb_tmp`

**J2 BT / 磁力线**
1. 版本谱系定性（发行过几个剪辑版）→ 定真实时长判据
2. DDG lite 搜源 → 核**该 hash 自己的文件列表** → 确认单 mkv
3. 出磁力 / `.torrent` 附件入口 + 档位对比 + 避坑名单（不代为添加种子）
4. 用户下完 → H 节验收 → G2 内封轨 → G3 外站 → G4 校准
5. 清单落盘 + 硬结论写回账本

**J3 纯配字幕线**
1. G0 决策树，第 0 步永远 `ffmpeg -i` 查内封轨
2. 有 chi 轨 → 抽 + 双语合并；没有 → SubHD 三步链
3. G4 四项匹配 → 渲染验排版（`-copyts`）→ 用户校准一句台词
4. 同名自动挂载 + 备用时间轴 + 说明.txt + ASS 母本
5. `rag.py up` 写回 → `rag.py index` → 跑三套回归

---

## K. 纪律与红线（其它 AI 也要遵守）

- **未经同意不下载、不代为添加种子**；成品一律 `G:\NEW MOVIE\`。
- **不把任何文件下载 / 解压 / 编译 / 缓存到 C 盘**（常年只剩 2–3G）：
  yt-dlp 缓存与 temp 显式指向 D 盘；Go 构建固定 `D:\wb2api-build` 并指定 GOROOT/GOPATH/GOCACHE。
- **DRM 订阅流媒体不碰**（D5）；只在授权 / 公开 / 自有内容范围内操作，遵守平台条款。
- 程序纪律：**限时 + 后台运行 + 看门狗防卡死**；抓完立即关浏览器。
- 只要真实数据，不编造、不交空表，覆盖率如实报；同一方案失败立刻换路，不磨同一堵墙。
- 中文沟通、代码术语用英文；「开工 / 默认 / 继续 / 快」= 直接执行不确认。

---

## L. 检索锚点词（能定位，必须带域限定词）

RAG 原本是配音域（现 187 条账本里 142 条 TTS），**纯口语查询会被配音域或影视域账本劫持**。
索引 3193 块 / 92 文件（含三个下载域 skill，2026-11-08 22:05 重建）。
2026-11-08 用 16 条查询实测**下载域**首条命中率：术语型 **8/8**、口语型 **3/4**
（补「下载后字幕压缩包乱码怎么修」这条直接回答之前是 2/4）、**口语 + 域限定词 4/4**；
影视域同期对照为 8/8 / 2/4 / 4/4（见 `REPORT_MOVIE_FINDING.md`）。
本域两个模板：**`rag.py search "下载 视频站 <具体术语>"`**（视频站 / yt-dlp / m3u8 / DRM 类）
与 **`rag.py search "下载 字幕 <具体术语>"`**（找对应字幕类）。
回归脚本 `eval_recall_download.py`；写回下载结论用 `--tags "下载,视频站"` 或 `"下载,字幕"` 保持域隔离。

```
下载 视频站 yt-dlp 1755 extractor 2026.10.26 ffmpeg-location cache-dir
下载 视频站 simulate -F list-subs 先探测 不下载
下载 视频站 ok.ru full 1080 三头 Origin 720p 手工解析
下载 视频站 B站 danmaku xml 1080P 高清 premium cookie
下载 视频站 YouTube EJS js-runtimes PO token zipapp 插件发现
下载 视频站 DRM Widevine PlayReady 不支持 AES-128 原生解密 allow-unplayable
下载 视频站 m3u8 HLS 分片 -N aria2c http ftp 区别
下载 视频站 download-sections ffmpeg Range 切段 concat DTS
下载 视频站 aria2c 1.37 多线程 断点 cache-dir C盘禁写
下载 片源 迅雷 0做种 torrent 附件 infohash 文件列表 单 mkv RAR 分卷
下载 字幕 内封轨 ffmpeg -i 第0步 WEB-DL 官方多语
下载 字幕 SubHD 三步链 tk_ cookie GBK slug 522
下载 字幕 恒定偏移 校准点 41.92 PAL PlayRes copyts 自动挂载
下载 字幕 纯对白 SDH 双语 ASS 母本 内部换行
下载 工具链 REPORT_DOWNLOAD_TOOLCHAIN 自检 SOP 验收 真实时长
```

跑法：

```bash
PY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
cd G:/_setup/rag
"$PY" rag.py search "下载 视频站 <上面任一条>"
"$PY" rag.py get <id>                 # 取某块全文
"$PY" eval_recall_download.py        # 本域回归
```

## M. 给没有 RAG 的外部 AI：自包含提示词（可整段粘贴）

```
你是下载与配字幕助手，服务一位中文用户。按以下已实测规矩执行：

1. 未经同意不下载、不代为添加种子；成品放 G:\NEW MOVIE\；yt-dlp 缓存/temp 必须显式
   指向 D 盘（--cache-dir、-P temp:），绝不落 C 盘。长任务限时 + 后台 + 看门狗，抓完关浏览器。
2. 工具：yt-dlp 主用 /g/voice_lib/tools/yt-dlp.exe（2026.10.26，1755 extractors）；
   aria2c /g/_setup/tools/aria2-1.37.0-win-64bit-build1/aria2c.exe；
   ffmpeg /e/tool/ETS/ffmpeg/ffmpeg.exe（2020-04，无 ffprobe）；代理 http://127.0.0.1:7897。
   每条 yt-dlp 命令必带 --ffmpeg-location（PATH 里没 ffmpeg，否则合并/切段失败）。
3. 先 --simulate -F 和 --list-subs 探测，确认档位再下；官方明说「列表支持 ≠ 一定可用」。
   选格式 -f "bv*+ba/b"，合并 --merge-output-format "mp4/mkv"，切段 --download-sections "*起-止"。
   -N 是分片并发；--downloader aria2c 只管 http/ftp，dash/m3u8 分片不走它，别混。
4. 站点特例：ok.ru 一键只到 720p，要 full 1080 必须手工解析 videos[].url 并带齐
   UA/Referer/Origin 三头、不要 -L；B站无 cookie 可到 1080p，但高码率要大会员 cookie，
   且字幕轨常只有 danmaku xml 弹幕、不是对白字幕；YouTube 本机可用，只有出现
   "Only images" / 403 才按 yt-dlp-ejs+JS runtime → pip版插件发现 → PO token → cookie 顺序排。
5. DRM 边界：标准 AES-128 HLS（key URI 可直接 GET）yt-dlp 原生支持解密；
   Widevine/PlayReady/FairPlay 一律不支持，--allow-unplayable-formats 只会下到加密碎片。
   Netflix/Disney+/Prime 等订阅流媒体不碰，改走 BT/WEB-DL 已发行片源。
6. BT 层：用户用迅雷，0 做种也能下，按规格挑；给磁力前必须核实该 infohash 自己的
   文件列表，明确单 mkv / RAR 分卷 / MP4+sample；国内站 .torrent 附件命中率更高。
7. 配字幕决策树：视频站 --list-subs → ffmpeg -i 查内封轨（WEB-DL 常自带官方多语，
   天然对轴）→ SubHD 三步链（prepare-download / down / api-sub-down，同 cookie jar，
   zip 文件名 GBK）→ 四项匹配（时长/剪辑版/PlayRes/帧率）。双语用纯对白英文轨不用 SDH，
   保留英文内部换行与 {\an8}；渲染验字幕必须加 -copyts；永远留 ASS 母本、同名自动挂载。
   用户报「第一句台词在 X 秒」→ 算恒定偏移全片平移；偏移随时间增长是 PAL 帧率差，
   有台阶是剪辑版不同（换字幕别硬调）。
8. 验收：ffmpeg -i 量真实时长与字幕轨，时长不符则版本错、字幕作废。
   本机 ffmpeg 不认 Windows 绝对路径，先 cd 再传纯文件名，输出写 D:/ 或 G:/。
   含 \s \d 的 Python 正则不要用 bash heredoc（反斜杠会被换成 /），写成 .py 再跑。
9. 结论与完整命令见 G:/_setup/REPORT_DOWNLOAD_TOOLCHAIN.md；版本定性见
   REPORT_MOVIE_FINDING.md；找片命令见 REPORT_MOVIE_TOOLCHAIN.md。
   有本机 RAG 时先跑 rag.py search "下载 视频站 <具体术语>"（必须带域限定词，
   否则被配音域账本抢首位），干完把新硬结论 rag.py up --tags "下载,视频站" 写回，
   再跑 eval_recall.py 5 / eval_recall_movie.py / eval_recall_download.py 确认三域基线不退。
10. 只要真实数据，不编造，覆盖率如实报；同一方案失败立刻换路；中文沟通、代码术语用英文。
```

---

## 证据索引

- 本文件所有实测：2026-11-08 19:14–19:25，`--simulate` / `--list-subs` 探测，**未下载影片**
- yt-dlp 官方 README（选项拼写）：`https://github.com/yt-dlp/yt-dlp#readme`
- yt-dlp 官方 supportedsites.md（列表 ≠ 保证可用）
- yt-dlp 源码 `yt_dlp/downloader/hls.py`（AES-128 与 `_has_drm()` 一手证据）
- 社区定稿解法（EJS / PO token / zipapp 插件发现）：yt-dlp wiki EJS 与 PO-Token-Guide、
  `youtube-acquisition` skill 文档、2026-08 线上链路复盘
- ok.ru 三头与码率表：`C:/Users/86178/.workbuddy/skills/okru-video-download/SKILL.md`
- 字幕链：`C:/Users/86178/.workbuddy/skills/chinese-subtitle-fetch/SKILL.md`
- BT 与版本定性：`G:/_setup/REPORT_MOVIE_FINDING.md`、`REPORT_MOVIE_TOOLCHAIN.md`
- 日志：`C:/Users/86178/WorkBuddy/2026-10-18-15-59-50/.workbuddy/memory/2026-11-{01,05,06,08}.md`
