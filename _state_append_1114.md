
---

## 2026-11-14 16:00-17:10 会话增补（新会话必读）

### 已交付

1. **旁白自然度判决表**（以前从未出过）：`G:/_setup/_nat_narr.json`
   - 865 条：**OK 764 / WARN 37 / FAIL 18（2.1%）/ 短句不判 46**
   - FAIL：`N0070 N0094 N0279 N0335 N0350 N0356 N0375 N0413 N0439 N0463 N0472 N0562 N0584 N0640 N0647 N0664 N0753 N0787`
   - 生成脚本 `G:/_setup/_nat_narr_table.py`；数据源 `_nat_cache.json`（键=文件名|md5，覆盖 865/865）+ `_nat_stat.json`
   - 2.1% 与文档记录逐字对上，口径未漂
2. **第 15 项 F0 复核已完成（定案）**：`G:/_setup/_f0_crosscheck2.json`
   - 目标集 = `_narr_check4/_narr_check.json` 里 WATCH/FIX 且 why 含 F0/八度 = **636 条**，实跑 641
   - 结果：**双估计器都报 ≥2 次突跳 = 0 条**；仅 praat 报 = 18；仅 pyin 报 = 0；两者都 <2 = 623
   - ⇒ **F0 突跳全部是 praat 倍频跟踪错误，没有真缺陷**；判据必须重定（不能单估器）
   - 修的两处 bug：`why` 是 **list** 不是 str；取样原按 `verdict=="FIX"`（该账本 FIX=130，不是记录的 1）

### 口径变更（已写入 DECISIONS.md）

- **音色稳定性只抓极端**（用户 15:46）：持续 ≥0.75s 同向偏移才判；F0 只在跨八度/基频丢失时判；谱质心 ×2 不单独成立；能量用 voiced RMS 且排除首尾 0.5s；**sep 下线**（召回 77.5%/同人跨情绪误报 38.5%，AND 后 23.1% 仍不可接受）
- 实测：239 条 12 条 FAIL 里 9 条是单窗 0.25s 瞬态，加持续过滤后 → 3 条
- **`_drift_cache.json` 过期**：mtime 11-12 19:07，94 条音频已回填重写，重算后 48 条判决变（新增 FAIL 7 / 原 FAIL 降 WARN 4）。特征缓存必须带源时长指纹

### 云端 GPU（新会话接手看这里）

- 实例：**Tesla V100-SXM2 16G**，驱动 525.125 / CUDA 12.0，64 核
- 可用 torch：**2.0.1+cu117**（镜像默认装的 2.14.1+cu130 在 525 驱动上 cuda=False，已卸）
- 权重：`/home/aistudio/models/EmphaClass/emphaclass_en`（3.6G，md5 `5e7ae2cd3050047ad4d83e9f2cf281e4`）
- 推理脚本：`G:/_setup/_emp_infer.py`（已修 fp16 输入 dtype；探针 3 条通过，`frames≈时长×50`，emph_rate 0.057~0.109）
- **`w11.py` 常驻执行器反复死**（重启 3 次）⇒ 改用「单元格 + curl 回传 ntfy」一次性模式

### 传输坑（重要）

- **ntfy.sh 附件额度已爆**：>0.5MB 返回 413，免费额度当日耗完
- 改用 **ntfy.envs.net**：42 片 × 500KB **全部上传成功**（`G:/_setup/_cloud_fetch.sh` 含 42 个 URL）
- `rcc.py` 已改为用 curl 发/收（urllib 对 ntfy.sh 会 SSL handshake timeout）

### 待办（优先级序）

1. 云端拼装 `in_narr`（跑 `_cloud_fetch.sh`）→ `python3 emp_infer.py --dir in_narr`，拿 120 条强调率
2. 旁白音色稳定性（句内 + 跨章）——**一条都没测**；跨章建议 RDR + 冷启动漂移（`ch123_scs.py` 里有，未接线）
3. 标注层：glm 第三路 0 条，676 句单模型草稿
4. 停顿注入：`pause_llm.json` 对本书 0 命中（34 条全是 Wonder 编号）
