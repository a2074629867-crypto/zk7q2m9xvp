# REPORT_MOVIE_FINDING — 影视找片 / 版本定性 / 字幕校验经验账

本文件是「豆瓣找片专家」这条对话线的蒸馏结论，供本地 RAG（`G:/_setup/rag`）索引，
也供其它 AI 直接读取。所有条目均有实测证据，证据位置写在每节末尾。
原始过程流水在 `C:/Users/86178/WorkBuddy/2026-10-18-15-59-50/.workbuddy/memory/*.md`，
片源清单在 `C:/Users/86178/WorkBuddy/2026-10-18-15-59-50/*_片源清单.md`。

三份文档分工（都在 RAG 索引源 `G:/_setup/*.md`，`REPORT_` 前缀吃 1.30 权威度）：
本文件 = **结论与检索锚点**；`REPORT_MOVIE_TOOLCHAIN.md` = **找片/字幕命令**；
`REPORT_DOWNLOAD_TOOLCHAIN.md` = **下载总链（BT / 视频站 / 配套字幕）**，
覆盖 yt-dlp、m3u8/HLS、ok.ru 三头、DRM/AES-128 边界、字幕决策树，
检索该域必须用 `rag.py search "下载 视频站 <具体术语>"`。

## 检索入口：其它 AI 怎么取到这里的经验

有本机 RAG 访问权限时，唯一正确的入口是：

```bash
PY="C:/Users/86178/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
cd G:/_setup/rag
"$PY" rag.py search "这里换成锚点词"
```

`search` 输出两段：**硬结论账本**（`facts.jsonl`，优先级最高）与**原文片段**。
账本检索是 jieba 分词后的 token 重叠，**不是语义向量**，所以查询必须用术语而非口语。
查不到时换更具体的名词重查；需要细节用 `rag.py get <id>` 取全文。
配音域与影视域用 tags 分隔：影视条目的 tags 含 `找片`，不会污染 TTS 账本。
**要动手跑命令，读配套文档 `G:/_setup/REPORT_MOVIE_TOOLCHAIN.md`**（环境路径、可复制命令块、
症状→修法、端到端 SOP）。本文件只给结论，那一份只给工具链，两者都在 RAG 索引源
`G:/_setup/*.md` 里，`REPORT_` 前缀吃 1.30 权威度加权。

## 版本谱系定性：用户说「未删减版 / 剧场版 / 加长版」时先查谱系

不要按资源标题去找片源，先确定这部片到底发行过几个剪辑版。
《她》Her (2013) 全球只有一个正式发行版 = 126 分钟 / 02:05:50 / R 级完整版；
150 分钟原始剪辑与索德伯格 90 分钟版从未发行（Lost Media Wiki 标 Lost），
蓝光只带幕后花絮、无删减片段。「未删减」的判定标准因此唯一：真实时长 2:05:50 +
1.85:1（1920×1036 或 1920×1040）+ 23.976fps。国内标题里的「未删减」是营销话术，
指相对国内流媒体/电视删减版；正经 BluRay 压制本来就是完整版。
「未删减」要分清两种含义：① 相对加长/导演剪辑版 ② 相对审查删减。
证据：memory/2026-11-05.md、Her_2013_片源清单.md。

## 剧场版 / 加长版 / R 级的判定只认真实时长

SSDSSE 的 `The.Tree.of.Life.2011.CC.Bluray.1080p.x265.10bit` 文件名带 CC（Criterion）、
发布页标「剧场版高码率」，实测 MKV 头部 Duration 元素 = **03:08:41（188.7 分钟）= 加长版**，
剧场版是 139 分钟 / 02:19:05。假标导致按剧场版做的 +41.92s 字幕整体报废。
判定铁律：挑「发布页明写 Runtime/Duration」的源，交付前用 `ffmpeg -i` 或解析 MKV Duration
量一遍真实时长再算数，**绝不凭文件名、组名、封面判断**。
R 级不是某个特别版本：MPA 原文 `Rated R for language, sexual content and brief graphic nudity`，
美国只发行过 R 级这一个剪辑，没有 PG-13 版、没有删减版蓝光。
反向判据：标题里特意写「未删减 / R级 / 纯净」的几乎都是国内网盘转码版（非 BT 种子），
反而可能被剪掉粗口、性相关对白、Isabella 替身戏；Scene/压制组从不打这种标签。
证据：memory/2026-10-27.md、memory/2026-11-05.md。

## 种子交付前必须核实该 hash 自己的文件列表（血泪坑）

同名发布组 + 同体积 ≠ 同一个种子。SPARKS `Her.2013.1080p.BluRay.x264-SPARKS` 8.74GB
至少三个不同 infohash：`1DFA3F51B5E0B9BCBE75C45F05A78FD43E85182F` 是
**101 个文件的 RAR 分卷包**（`.r00`~`.r99` 每个 95.37MB + nfo + proof），根本没有 mkv；
`A33CAE25FF938CFC4E398D81B3CC16A8D9B6F078`（[PublicHD]）才是**单 mkv 8.74GB + txt + nfo**。
我把同名另一版的「单 mkv」特征张冠李戴套到了分卷版上，被用户当场指出。
同类坑：KiNGDOM `BD562A3E...` 虽印了 R 级 + 02:05:50，但 TPB 明写 `Container: MP4`、
`Files: 10`（含 sample），也不是 mkv。
固化规矩：给磁力前逐个核实该 hash 自己的 `Torrent File Content` / `File List`；
告知用户打包形式三分类：**单 mkv** / **RAR 分卷（.r00~.rNN）** / **MP4 + sample 多文件**。
itorrents.org、torrage.info、torrage.com 在本机代理下拿不到 `.torrent`（502/301/404），别磨。
证据：memory/2026-11-05.md「硬坑」节。

## 迅雷口径与假种识别

用户用迅雷，有云端缓存，**0 做种的老种照样能下**，所以做种数不是筛选标准，
应按规格（码率 / 音轨 / 画幅 / 打包形式）排优先级。国内 BT 站（1lou.me / yunpanb.com /
mini4k.io）常只给 `.torrent` 附件不给磁力，但 WebFetch 能读到完整 MediaInfo，
是验证时长最硬的证据源；附件对迅雷的命中率反而比裸磁力高。
漫威/迪士尼版权查得严，磁力可能被判「违规资源」，此时不改源改方式：下 `.torrent` 附件。
mini4k 的 `/torrents/<id>` 详情页是 JS 渲染，curl 直连不通，别在上面磨。
假种：`VisionQuest S01E02 1080p WEB H264 FLUX.exe` 1.28GB，文件是 `.exe` 不是视频。
给磁力前看一眼扩展名，别只看体积和做种数。
证据：memory/2026-11-05.md、memory/2026-11-06.md、Eternals_2021_片源清单.md。

## 剧集滚动更新与假整季包

找剧集先查播出表。VisionQuest (2026) Disney+ 8 集，2026-10-13 首播双集，
E07 11-03 出，**E08「Forever」11-10 才播**；11-06 只出了 7 集，
此刻任何标「S01 Complete / 全季 8 集」的都是假标或占位。
limetorrents 的 `VisionQuest (Season 1) WEB-DL 1080p` hash `9AE06727...`
实测只有 2 个文件（E01 2.24GB + E02 1.92GB），是滚动更新包不是整季。
证据：memory/2026-11-06.md、VisionQuest_2026_片源清单.md。

## 规格约束反推档位 + RX580 硬解边界

用户给硬约束「每集至少 2G」时，先列各档单集体积再判断能不能全季达标，不要直接推 1080p。
VisionQuest：2160p DSNP WEB-DL DV/HDR H.265 单集 3.8–6.3GB → 唯一全季达标的路；
1080p H.264 单集 1.8–2.46GB，E02/E03/E04 全部不足 2G；720p/480p/x265 重编码全不达标。
RX580（Polaris）没有 HEVC 10bit 硬解，2160p 全是 HEVC Main10 + DV/HDR → CPU 软解可能掉帧，
SDR 屏不做 tone mapping 会发灰；x264 1080p 硬解直吃。
折中方案：2160p 收藏 + 1080p 补看不达标那几集。
证据：memory/2026-11-06.md。

## 字幕第 0 步：先查视频内封轨，别先去字幕站

给 Eternals TEPES 版配字幕时，在 SubHD（站群 522）、zimuku（404 被墙）、
subf2m（只有机抽 Chinese BG code）、SubtitleCat（无中文）、OpenSubtitles、
lwltv（Cloudflare Turnstile，POST 下载口 405）之间绕了十几轮，
**而答案就在视频文件里**：`ffmpeg -i` 一眼看到 16 条内封字幕轨，
其中中文 3 条（0:15 港繁 / 0:16 简中 / 0:17 台繁），迪士尼官方译本，天然对轴、零偏移。
正确顺序：① `ffmpeg -i file.mkv` 列流 ② 有 `Subtitle: subrip` 且 lang 含 chi →
`ffmpeg -map 0:N -c:s srt out.srt` 直接抽 ③ 没有才去外站。
规律：WEB-DL 类片源（DSNP / AMZN / iTunes / MAX）经常保留全部官方字幕轨，
BluRay 压制版（CMCT/FRDS）通常只带双语 ASS 或不带 —— 别拿 BluRay 经验套 WEB-DL。
区分简繁港台看译名：大陆「天神族 / 阿里瑟姆」、台湾「瑟西」、香港「星神族 / 亞彌聖」。
证据：memory/2026-11-01.md、chinese-subtitle-fetch SKILL.md 第 0 步。

## 字幕合并与时间轴校准

做双语：中文轨 + 同片**纯对白**英文轨（不是 SDH，SDH 带 `(MUSIC PLAYING)`），
按时间重叠把英文挂到中文 cue 下。**英文原 cue 的内部换行必须保留**，
不能用 `re.sub(r'\s+',' ')` 压平，否则两句英文挤成一行；抽出的 `{\an8}` 置顶标记要保留。
不要拿两个 SRT 拼双语：同一压缩包里的中/英 SRT 常是两套时间轴
（CMCT 的 Tree of Life 包实测英文比中文晚 31.4 秒），双语必须从 ASS 拆。
单校准点法：用户报「第一句 Brother 出现在 1:28」，原字幕 0:46.08 → 偏移 +41.92s 全片恒定后移。
前提是字幕与片源**同剪辑结构**（此前全文比对 482 条命中、偏移恒定 30.06s、σ=0.74s、无漂移）。
偏移随时间线性增长 = 帧率差异（PAL 4%）；偏移有台阶 = 加长/删减版。
**字幕交付永远保留一份带完整样式的 ASS 母本**，只留 SRT 会在修订时丢光样式。
证据：memory/2026-10-27.md、memory/2026-11-01.md。

## SubHD 三步下载链（顺序错即失效）

详情页 slug 是 `/a/<6位字母数字>`（如 `N2kG4z`），**不是纯数字**，正则别写 `\d+`。
搜索结果卡片链接用**单引号** `href='/a/<slug>'`，用双引号 grep 会一条都匹配不到。
免登录下载三步，必须同一个 cookie jar、顺序不能错：
① `POST /api/sub/prepare-download` body `{"sid":"<slug>"}` 种 tk_ cookie
② `GET /down/<slug>`（带 cookie，给下一步发许可证）
③ `POST /api/sub/down` → `https://dl.subhd.me/YYYY/MM/xxx.zip|ass`
顺序错一步报「时间过长本临时页面已经失效」；直接 GET `/down/<slug>` 会静默重定向回详情页。
zip 内文件名是 GBK：`name.encode('cp437').decode('gbk')`。
预览接口 `/api/sub/preview/<slug>?manifest=1`（清单）与 `?file=0`（全文，需 Referer），
时间戳只精确到秒，只能验内容不能拿来用。
站群 subhd.tv / .cc / .me / subhdtw.com 会**整站同时 522**（源站问题，换域名没用），隔几小时再试。
证据：chinese-subtitle-fetch SKILL.md、memory/2026-11-01.md。

## ASS PlayRes 规格与渲染验证

PlayRes 决定能不能用在这个片源上：1920x1080 ✅ 原尺寸最佳；
1920x804 ⚠ 按蓝光 2.39:1 做的，放到 1080 高画面上字号和边距被乘 1.34 倍、长句沉底；
384x288 ⚠ 老式写法，字号明显偏小贴底；缺省不写时 libass 兜底，多数还能用。
「片源版本匹配」不只指时长，**PlayRes 也要对**：IMAX 16:9 片源优先挑 1920x1080。
拿真实视频烧字幕验排版：
`ffmpeg -copyts -ss 1824 -i movie.mkv -vf ass=x.ass -frames:v 1 D:/out.png`
**⚠ 必须加 `-copyts`**：不加时 `-ss` 在 `-i` 前会把 PTS 归零，ass 滤镜以为还在 0 秒，
输出 PNG 与无字幕底图**字节完全相同**，看着像渲染成功其实一个字没画。
判断办法：几张图 `ls -l` 大小一模一样 = 全是空图。
选时间点要写脚本解出所有候选 ASS 的 Dialogue 区间，找**所有版本都有字幕**的时刻，
对白空白处会出现「全部无字」的假象。
第三方 ASS 合集按 `01 xx - 说明.ass` 编号排位，另建子目录，说明里写清 PlayRes / 样式数 /
事件数 / 发布人 / 适合什么片源；特效字幕常带必须安装的 ttf 字体。
证据：memory/2026-11-01.md、chinese-subtitle-fetch SKILL.md §3.3/§3.4。

## ffmpeg 与 bash 环境坑（本机实测）

本机 ffmpeg 在 `/e/tool/ETS/ffmpeg/ffmpeg.exe`（2020-04 build，**无 ffprobe**，用 `-i` 看流，
输出走 stderr）。三条反复踩的坑：
1. **bash heredoc 里的反斜杠会被替换成 `/`**：`r'PlayResX:\s*(\d+)'` 进 Python 变成
   `'PlayResX:/s*(/d+)'`，正则静默失效（`search` 返回 None / `findall` 返回空），不报错。
   ⇒ 凡用到 `\s \d \n` 的 Python，一律用 Write 工具写成 .py 文件再跑，绝不用 heredoc。
2. **ffmpeg 传 Windows 绝对路径会报 No such file or directory**：
   `cd "/g/NEW MOVIE/eternal"` 后传纯文件名就正常；输出路径反过来必须写 `D:/...`，
   ffmpeg 不认 `/d/...`。处理中文/空格路径一律先 cd 再传相对名。
3. 输出路径必须 Windows 风格盘符正斜杠，否则静默失败。
其它：ffmpeg 拉 ok.ru 直链必须显式 `-http_proxy http://127.0.0.1:7897`
（沙箱默认 7104，ffmpeg 不认会卡死到 SIGTERM）；Bash 工具默认 120s 超时，
长任务显式传 timeout；drawtext 的 `text=` 里冒号会被当滤镜分隔符，要用 `textfile=`；
中文需 `fontfile=C\:/Windows/Fonts/msyh.ttc` + `export MSYS_NO_PATHCONV=1`。
证据：memory/2026-10-25.md、memory/2026-11-01.md、chinese-subtitle-fetch SKILL.md §6。

## 先搜索再定向抓，别自己瞎试

找 Is-slottet (1987) 时在 ok.ru 搜索接口、NRK psapi、archive.org、Dailymotion、
TPB、qBittorrent 之间绕十几轮全空，用户一句「为啥你就不能谷歌一下」点醒，
DDG lite 一次命中 ok.ru `9447644727974`。
搜索通道实测：`lite.duckduckgo.com/lite/?q=` 走代理 200 纯 HTML 最好用；
Brave 可用；**Google 返回 JS 跳转壳爬不了**；cn.bing 结果不含目标站；
ok.ru 自己的搜索接口对任何词都返回「Видео не нашлось」，**不可用，别浪费轮次**。
`rarefilmm.com` 是冷门片宝库，详情页内嵌 `//ok.ru/videoembed/<id>`，顺藤能拿签名直链。
证据：memory/2026-10-25.md。

## 帧级版本比对方法（判断两个视频是不是同一内容）

按可靠度排序：① **镜头切点 Hough**（fps=5 + 32×32 gray 差分检测切点，
再对 (速度比 r, 偏移 o) 投票，237/359 一击命中；切点不受调色/画幅/码率影响）
② **原生分辨率帧匹配**（crop 同画幅后 scale=150×113、z 归一化矩阵乘，
同源 0.94–1.000，跨转录只有 0.5–0.8；对照组必须用同文件内的已知对齐段；
⚠ 32×24 太糊，对照组只有 0.63 等于没验）
③ 音轨包络互相关（弱，仅线索，近静音块 z 归一化会给出 >1 假相关）
④ 原始波形互相关（跨转录无效，已知对齐段对照也只有 0.09）。
PAL 提速 0.960 = 24/25，映射 `t87 = 0.960×t78 + 8.5`。
Is-slottet 87 分钟版定性结论：**不是删减内容**，是正片+片尾字幕放完后
这部电影自己的 footage 又重播了三遍（83:05 出现与片头 01:35 逐像素一致的片名卡，
337/359 切点命中 93.6%）。自写互相关窗口长度必须 > 块长，否则 cc 只剩 1 个样本永远返回偏移 0。
证据：memory/2026-10-25.md、Is-slottet 分析.txt。

## 用户协作规矩（硬性，其它 AI 也要遵守）

未经同意不下载、不代为添加种子；下载文件一律放 `G:\NEW MOVIE\`；
不把任何文件下载/解压/编译/缓存到 C 盘（C 盘常年只剩 2–3G），临时文件放 D 盘
（`D:/wb_tmp`），Go 构建目录固定 `D:\wb2api-build` 并显式指定 GOROOT/GOPATH/GOCACHE。
只要真实数据，不编造、不交空表，覆盖率如实报（E07 hash 没取到就留空并给精确文件名）。
同一方案失败立刻换路，不反复磨同一堵墙；抓完立即关浏览器。
在意删减版/原声配音、画质档位、RX580 兼容性、约 10GB 体积档。
「开工 / 默认 / 继续 / 快」= 直接执行不确认。中文沟通，代码术语用英文。
用户问「能不能看到 / 能不能找到」，在这个上下文里默认指**种子/片源**，不是在线平台
（误判成平台被明确纠正过）。
证据：USER.md、SOUL.md、memory/2026-11-05.md。

## 检索提示词速查表（能定位的锚点词）

账本检索靠 jieba token 重叠，下面每个词都出现在 `facts.jsonl` 的影视条目里，
直接 `rag.py search "<词>"` 可一击命中。

### ⚠ 定位的第一条规矩：必须带域限定词

这个 RAG 原本是 TTS/配音项目的外部记忆（163 条账本里 142 条是配音域），
**纯口语查询会被配音域账本劫持**。2026-11-08 用 16 条查询实测首条命中率：

| 查询类型 | 首条命中影视域 | 样例 |
|---|---|---|
| 术语型（8 条） | **8/8** | `同名发布组 RAR 分卷 单 mkv 文件列表 infohash` |
| 口语型（4 条） | **2/4** | 「为什么字幕对不上」→ 首条是配音域「字幕时间轴不等于说话人边界」；「4K 会不会卡」→ 首条是配音域声纹条目 |
| 口语 + 域限定词（4 条） | **4/4** | `找片 片源 为什么字幕对不上 恒定偏移 校准点` |

⇒ **万能模板：`找片 片源 <具体术语>`**。
把 `找片` 或 `片源` 放在查询最前面，再加一个只有影视域才有的术语
（磁力 / infohash / mkv / SubHD / PlayRes / 剧场版 / RX580 / 内封轨 / 三步链），
配音域条目就抢不走首位。这是「能定位」与「查不到」的分界线。

| 想找什么 | 用这个查询词 |
|---|---|
| 加长版假标 | `剧场版 加长版 真实时长 Duration SSDSSE` |
| 未删减版到底存不存在 | `Her 2013 未删减 R级 02:05:50 版本谱系` |
| 磁力给了但不是 mkv | `同名发布组 RAR 分卷 单 mkv 文件列表 infohash` |
| 种子打包形式 | `打包形式 单 mkv MP4 sample 分卷 .r00` |
| 做种数为零能不能下 | `迅雷 做种数 离线缓存 .torrent 附件` |
| 剧集整季包是假的 | `滚动更新 假标 S01 Complete E08 播出表` |
| 每集 2G 该选哪档 | `单集体积 2160p 1080p 档位 规格约束` |
| 4K 会不会卡 | `RX580 HEVC Main10 硬解 DV HDR tone mapping` |
| 字幕不用外站找 | `ffmpeg -i 内封字幕 chi WEB-DL 第0步` |
| 字幕对不上 | `恒定偏移 校准点 Brother 41.92 同剪辑结构` |
| 双语字幕合并 | `纯对白 SDH 内部换行 an8 ASS 母本` |
| SubHD 下载 | `prepare-download tk_ cookie 三步链 GBK slug` |
| ASS 字号变形 | `PlayRes 1920x804 1.34 缩放 IMAX` |
| 渲染出空图 | `copyts PTS 归零 ass 滤镜 字节相同` |
| ffmpeg 路径问题 | `Windows 绝对路径 cd 相对文件名 D:/ 输出` |
| 正则静默失效 | `heredoc 反斜杠 替换 正则 .py 文件` |
| 找冷门片源 | `DDG lite rarefilmm ok.ru videoembed 先搜索` |
| 两版本是否同内容 | `镜头切点 Hough PAL 0.960 帧匹配 150x113` |
| 完整命令怎么跑 | `REPORT_MOVIE_TOOLCHAIN 工具链 自检 SOP` |
| 下载类工具链 / 视频站 | **`下载 视频站 REPORT_DOWNLOAD_TOOLCHAIN yt-dlp ffmpeg-location cache-dir`**（域限定词是「下载 视频站」） |
| 下完找不到对应字幕 | `下载 字幕 内封轨 第0步 danmaku SubHD 三步链 PlayRes` |
| ffmpeg / Python / 代理路径 | `ffmpeg 无 ffprobe ETS python 7897 D:/wb_tmp` |
| 端到端该按什么顺序 | `端到端 SOP 版本定性 内封轨 恒定偏移 写回账本` |

## 给没有 RAG 的外部 AI：自包含提示词（可直接整段粘贴）

```
你是「豆瓣找片专家」，为一位中文用户找影视片源与字幕。按以下已验证规矩执行：

1. 未经同意不下载、不代为添加种子；文件放 G:\NEW MOVIE\；任何下载/解压/缓存不落 C 盘，
   临时文件放 D 盘。用真实数据，不编造，覆盖率如实报；同一方案失败两次立刻换路。
2. 用户说「未删减/剧场版/加长版」→ 先查版本谱系（发行过几个剪辑版），再找源。
   版本判定只认真实时长（ffmpeg -i 或 MKV Duration），绝不凭文件名/发布页标签。
   Her (2013) 只有 126 分钟 R 级一个版本；R 级不是特别版本。
3. 给磁力前必须核实该 hash 自己的文件列表，明确告知打包形式：
   单 mkv / RAR 分卷(.r00~.rNN) / MP4 + sample。同名同体积不等于同一种子。
   用户用迅雷，做种数不是筛选标准，按规格挑；国内站 .torrent 附件命中率更高。
4. 剧集先查播出表，未播完时「Complete/全季」一律假标；规格约束要先反推档位。
   RX580 无 HEVC 10bit 硬解，2160p DV/HDR 会软解掉帧、SDR 屏发灰；x264 1080p 硬解直吃。
5. 配字幕第 0 步永远是 ffmpeg -i 查内封轨（WEB-DL 常保留官方多语字幕），
   有就直接 -map 0:N -c:s srt 抽出，天然对轴；没有才去 SubHD 等外站。
   双语用纯对白英文轨不用 SDH，保留英文内部换行与 {\an8}；永远留一份 ASS 母本。
   ASS 的 PlayRes 必须匹配片源画幅；ffmpeg 渲染验字幕必须加 -copyts。
   片头不确定时给两套时间轴，用「第一句台词在几分几秒」让用户校准。
6. 本机 ffmpeg 在 /e/tool/ETS/ffmpeg/ffmpeg.exe（无 ffprobe）；先 cd 进目录再传相对文件名，
   输出路径写 D:/...；不要在 bash heredoc 里写含 \s \d 的正则（反斜杠会被替换成 /），
   一律写成 .py 文件再跑。找冷门片先用 lite.duckduckgo.com/lite/?q= 搜索再定向抓。
7. 回答先给结论再给依据，中文沟通、代码术语用英文；不铺垫、不说场面话。
8. 完整工具链（环境路径、SubHD 三步 curl、ffmpeg 命令模板、GBK 解压脚本、
   症状→原因→修法速查、端到端 SOP）见 `G:/_setup/REPORT_MOVIE_TOOLCHAIN.md`；
   结论与检索锚点词见 `G:/_setup/REPORT_MOVIE_FINDING.md`。
   有本机 RAG 时开工先跑 `cd G:/_setup/rag && python rag.py search "找片 片源 <具体术语>"`
   （**必须带域限定词**，否则会被配音域账本抢走首位；实测术语型 8/8、口语型 2/4、
   口语加域词 4/4），干完把新的硬结论
   `rag.py up -t -c -e --tags "找片,片源"` 写回账本，再跑 `eval_recall.py 5`
   确认配音域 top5 基线不低于 25/25。
```

## 工具链指针（其它 AI 直接整份读走）

`G:/_setup/REPORT_MOVIE_TOOLCHAIN.md` 分 A–L 节：A 环境路径清单（2026-11-08 逐项核实）、
B 开工自检块、C 版本定性、D 种子核验、E 字幕链、F SubHD 三步链、G RAG 链、
H 搜索通道、I 远程切段、J 症状→修法速查、K 磁盘/进程纪律、L 端到端 SOP。
所有命令可复制即跑；代理 7897 状态会变，**开工前用 B 节重新探测**，不要写死。

**下载单独走一份**：`G:/_setup/REPORT_DOWNLOAD_TOOLCHAIN.md` 分 A–M 节 ——
A 本机下载工具清单（yt-dlp 三版本 / aria2c / ffmpeg / pycryptodomex 实测）、B 自检、
C 通用下载模板、D 各站点实测与特例（ok.ru 一键只到 720p、B站 字幕是 danmaku、
YouTube EJS/PO token、DRM 与 AES-128 源码级边界）、E HLS/m3u8 与远程切段、
F BT/磁力要点、**G 找对应字幕决策树（视频站 → 内封轨 → 外站 → 匹配校验 → 交付）**、
H 验收、I 症状速查、J 三条端到端 SOP、K 纪律红线、L 锚点词、M 自包含提示词。
检索该域用 `rag.py search "下载 视频站 <具体术语>"`，回归 `eval_recall_download.py`。
路由 skill：`C:/Users/86178/.workbuddy/skills/video-download-toolchain/SKILL.md`。

## 证据索引（可复核路径）

- 本地 RAG：`G:/_setup/rag/`（rag.py / facts.jsonl / db/rag.sqlite / eval_recall.py）
- 工具链：`G:/_setup/REPORT_MOVIE_TOOLCHAIN.md`（A–L 节，可复制命令块）
- 下载工具链：`G:/_setup/REPORT_DOWNLOAD_TOOLCHAIN.md`（A–M 节，BT/视频站/m3u8/配套字幕）
- 影视域召回回归脚本：`G:/_setup/rag/eval_recall_movie.py`（16 条查询，术语/口语/加域词三组）
- 下载域召回回归脚本：`G:/_setup/rag/eval_recall_download.py`（本域 16 条，带域限定词）
- 本地 RAG：`G:/_setup/rag/`；2026-11-08 白天状态 3087 块 / 88 文件 / 账本 165 条
  （配音 142 + 影视 22 + 委屈判据补全 1），双域回归：影视术语 8/8、配音 top5 25/25；
  **同日傍晚灌入下载域后：3144 块 / 89 文件 / 账本 187 条**，三域回归：
  下载术语 8/8 / 加域词 4/4、影视术语 8/8 / 加域词 4/4、配音 top5 25/25
- 蒸馏规则：`C:/Users/86178/.workbuddy/skills/project-rag/SKILL.md`
- 字幕 skill：`C:/Users/86178/.workbuddy/skills/chinese-subtitle-fetch/SKILL.md`
- 日志：`C:/Users/86178/WorkBuddy/2026-10-18-15-59-50/.workbuddy/memory/2026-10-{18,20,22,24,25,27}.md`、
  `2026-11-{01,05,06}.md`
- 清单：同工作区 `Her_2013_片源清单.md`、`VisionQuest_2026_片源清单.md`、
  `Eternals_2021_片源清单.md`、`The_Tree_of_Life_2011_片源清单.md`
- 交付物：`G:/NEW MOVIE/eternal/ASS字幕(第三方)/`（7 份 ASS + 字体 + 4 张实帧预览）、
  `G:/NEW MOVIE/Is-slottet (1987) 剪辑/`
