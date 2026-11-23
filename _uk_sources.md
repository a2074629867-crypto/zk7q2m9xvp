# 英式男童音色：社区现成资源清单

> 背景：81 个候选全被否。根因不是筛得不好，是**这 81 个全说美音**——
> 素材只有 TEDxKids@ElCajon（加州）和 HiHo Kids（洛杉矶）。
> Fielding 是英国乡下男孩（《I'm the King of the Castle》），口音一开口就不对。

## 一、最对口：kidLUCID（UCL）

**London UCL Children's Clear Speech in Interaction Database**

| 项 | 内容 |
|---|---|
| 人数 | 96 个孩子（46 男 / 50 女），9;0–15;0 岁 |
| 口音 | **全英格兰南部口音**，母语者 |
| 录音 | 声学实验室，44.1kHz/16bit，**每人独立声道** |
| 标注 | 词级 + 音素级 Praat TextGrid，人工校对 |
| 内容 | 两人一组做 diapix 找不同任务，**自然对话**（不是朗读） |
| 许可 | 研究用途免费，OSCAAR 上申请 |
| 联系 | Valerie Hazan `v.hazan@ucl.ac.uk`（UCL） |

**问题**：`oscaar.ci.northwestern.edu` 我实测**站点已挂**（curl 返回 000，SSL 握手失败 35）。
所以现在拿不到，需要发邮件要。这是唯一"内容完全对口、又免费"的公开库。

## 二、付费但现成：DataTang 149 小时

`149Hours-BritishEnglishChildsSpontaneousSpeechData`（ModelScope 有页面）

- 12 岁以下英国儿童，多地区多文化背景
- 标注：文本 / 说话人 ID / 性别 / 口音 / 噪声
- 商用版权，数据堂售卖（datatang.com/dataset/1252）
- 优点：量大、标注全、直接买；缺点：要钱，且不知单价

## 三、美国库（口音不对，仅备选）

| 库 | 年龄 | 获取 |
|---|---|---|
| MyST | 7–11，朗读+故事 | 免费注册 |
| OGI Kids | 5–15 | 付费/机构 |
| CSLU Kids | 5–15 | LDC 付费墙 |
| CMU Kids | 6–11 | LDC |

## 四、今晚实测：CBBC《Our School》

`All Things Our School` 频道（`@allthingsourschool4911`），54 集，每集 ~20 分钟，
**Year 7 真实英国学生（11–12 岁）**，正是目标年龄。

问题（实测两集）：
- **下载成功率 ~1/3**（20/60 成功），多数报 format not available
- 有**成人旁白**（每条最长的说话人都是 18–24 岁的 male/female 旁白）
- 有**背景音乐**，且大量合唱/群体场景
- 20 分钟只分离出 33 个说话人，其中 **cc 判定通过全部闸门的男童只有 1 个**（13.7 秒）

结论：能出东西，但**产出率极低、且带 BGM**，不适合当 ref 主源。

## 五、还没试但有希望

1. **英国童星 press junket**（Matilda 2022 剧组、Billy Elliot 等）——录音棚音质、无 BGM、
   孩子 10–12 岁、英音；YouTube 上多为发布会片段，时长 2–5 分钟
2. **英国亲子 vlog**（Family Fizz、Dad V Girls、The Ingham Family）——孩子 8–12 岁自然说话，
   BGM 少；缺点是手机麦、房间混响
3. **现成 TTS 童声音色**（ElevenLabs 社区库有 "British boy"）——直接生成台词的音频，
   再拿它当 ref 喂 dots.tts；省掉找素材，但音色是合成的
