#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成/合并事实账本 facts.jsonl —— 硬结论，一条一结论，带证据位置。

跑法：python seed_facts.py
幂等：同 id 不重复写，但 conclusion/evidence 有变化会更新。
"""
import hashlib
import json
import os
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
FACTS = os.path.join(ROOT, "facts.jsonl")
TODAY = time.strftime("%Y-%m-%d")

# (topic, conclusion, evidence, status, tags)
F = [
    # ---------------- 配音红线
    ("语速硬限制", "tempo 硬夹 [0.70, 1.00]，任何路径不得低于 0.70；原速 ≤255wpm 直接不动（用户：原声慢的不用加快）。到 0.70 仍不达标只能重生成，不许再拉。",
     "REQUIREMENTS.md 第10-11条 / MEMORY.md §语速", "定稿", "配音,红线"),
    ("声纹阈值", "声纹 ≥0.65 可接受（带情绪），≥0.70 更好；段间声纹 <0.55 判异常。跨锚点不可比，必须用同区域原声做锚。",
     "REQUIREMENTS.md 第2-3条 / MEMORY.md §声纹", "定稿", "配音,红线"),
    ("电平统一", "全库 voiced RMS 统一 −24.0 dBFS，条间跨度 ≤1dB。基准脚本 ch123_unify.py（句内慢包络→增益→压峰→迭代补增益）。",
     "REQUIREMENTS.md 第23条 / MEMORY.md §全库电平", "定稿", "配音,红线"),
    ("峰值限制", "峰值 ≤ −1 dBFS；波峰因数 23dB 时峰值天然落 −1dBFS，不需要 limiter。",
     "REQUIREMENTS.md 技术红线表", "定稿", "配音,红线"),
    ("F0 报警线", "F0 >305Hz 就是喊（报警）；正常区 Charles 170-250 / Hooper 200-280；段间 F0 跨度 >40Hz 判异常。",
     "REQUIREMENTS.md 技术红线表", "定稿", "配音,红线"),
    ("短句禁 emo", "短对话句一律不打 emo 标签。happy→顶成吼（F0 300-445）、disgusted→砖墙压缩峰值0.98、surprised→311Hz、melancholic→音色发飘、angry→F0 抬一个八度。表情靠文本/停顿/seed 选型。",
     "REQUIREMENTS.md 第6-7条", "定稿", "配音,红线,emo"),
    ("不许拆句", "拆句 = 每段各演一次，毁整句语调弧线（L088 四段 F0 304/218/179/145，跨度 159Hz）。修复：整句一次生成→切段→电平对齐→重排停顿→rubberband 控速。",
     "REQUIREMENTS.md 第15条 / MEMORY.md §拆句", "定稿", "配音,红线"),
    ("口吃不拆条", "`I've got... I've got a picture of him.` 必须当一句生成，拆两条会切断口吃。L076 已并入 L075。",
     "REQUIREMENTS.md 第17条", "定稿", "配音,红线"),
    ("极短句必崩", "`I don't know.` / `No. But...` / `In a flat.` 单句生成几乎必失败（空音/只念前半/吐填充词），11 种写法 + 扫 seed 全无效。唯一可行：与同说话人下一句合并生成再切段。",
     "MEMORY.md §极短句 / L078", "定稿", "配音,红线"),
    ("结尾不许硬切", "father 尾音 /ə/ 必须念完有自然衰减。dots.tts 整段尾部 5ms 内掉 50dB 是通病 ⇒ 加尾随短语生成再切。",
     "REQUIREMENTS.md 第20条", "定稿", "配音,红线"),
    ("禁用 lookahead limiter", "lookahead limiter 会产生增益调制（听感抽吸/炸）。只做整体增益 + 压峰。",
     "REQUIREMENTS.md 第24条 / MEMORY.md §全库电平", "定稿", "配音,红线"),
    ("禁句内包络二次处理", "U.proc 句内包络二次处理必吞弱词（L059 died 被抹掉）。变速后只做整体增益 + 限峰。",
     "REQUIREMENTS.md 第25条", "定稿", "配音,红线"),
    ("拉伸音色边界", "tempo 拉伸幅度↔声纹（L068 锚 CH_neutral）：1.00=0.835 / 0.92=0.798 / 0.85=0.763 / 0.794=0.716。0.85 是音色边界，再往下必掉。",
     "REQUIREMENTS.md 技术红线表 / MEMORY.md §语速", "定稿", "配音,红线"),

    # ---------------- 工作流
    ("生成工作流（硬顺序）", "① 每条 2 seed 各一遍（无 pitch/rate 标签）→ ② 检测取最佳 → ③ 未达标再 1 seed → ④ 第 3 遍仍不行才加标签。顺序不许颠倒，不许跳过检测直接重生成。",
     "REQUIREMENTS.md §零 / 用户 2026-10-29 原话", "定稿", "工作流,红线"),
    ("标签是最后手段", "ctl（无标签）与 tag（带标签）不许并行起跑。2026-10-28 那批 784 条 = 8seed × ctl/tag 并行，顺序完全反了，一半算力浪费且污染对照。",
     "REQUIREMENTS.md §零 推论", "定稿", "工作流"),
    ("重生成四道闸门", "①span 落进 [p25,p75] ②ASR 词召回不低于原 take ③声纹 ≥0.65 ④峰值 <0.999。任一不过回退原 take。",
     "REQUIREMENTS.md 第31条", "定稿", "工作流"),
    ("逐段测音色", "每条音频必须切段，逐段测声纹+F0+电平。前面正常后面变怪物 ⇒ 单独重生成后面那句，不许整条凑合。",
     "REQUIREMENTS.md 第3条（用户原话）", "定稿", "工作流,红线"),
    ("一次不行二次合成", "反复生成找合适的，不许拿一版交差。检查项：ASR 逐词、逐段声纹、F0 跨度、电平、结尾衰减。",
     "REQUIREMENTS.md 第26-27条", "定稿", "工作流"),

    # ---------------- 不可行路径（踩过的坑）
    ("Vulkan OOM 无解", "RX580 8GB 上 Vulkan OOM（ErrorOutOfDeviceMemory）重启也救不了，模型峰值就超 8GB。唯一可行：--threads 2 + max_tokens≤260 + --session-option dots_tts.mem_saver=true（30-90s/条，禁并发）。threads=6 必 OOM，--backend cpu 直接崩 0xC0000005。",
     "MEMORY.md §环境 / 2026-10-19 复测", "定稿", "坑,GPU"),
    ("emo 标签净负收益", "TTSDS2 PROSODY 对照：ctl 85.06 > delivered 83.66 > cand 80.79。唯一正项 Pitch(+7.31)，轮廓 −3.03 / 节奏 −7.09 / 语速 −2.79 全倒退。根因 <emo> 只能抬 A 不能降 A。",
     "MEMORY.md §TTSDS2 / emo_bench REPORT_EMOTION_JUDGE.md", "定稿", "坑,emo"),
    ("禁 stretch_segments", "段长 <0.4s 时在边界造伪影，NISQA DIS 掉 2.4 分（L014 4.18→1.81）。改 stretch_whole 回 4.53。代价是停顿同比变长。",
     "MEMORY.md §三条硬结论", "定稿", "坑,后期"),
    ("已否定的 TTS 路线", "GSV 声纹 0.7997 不如我们 / CosyVoice2 不可控 / seed_vc 用户实测垃圾。链里禁止引入这三条。",
     "MEMORY.md §生产链", "定稿", "坑,选型"),
    ("pitch 只抬寄存器", "`<pitch, semitones=9>` 只能整体抬寄存器且饱和（5 和 9 都给 +3~4.7 半音），负向不动。单词级 pitch 完全无效（slowly 包 +9，F0 80.9→80.9）。重音不能用 pitch 做。",
     "MEMORY.md §dots.tts", "定稿", "坑,重音"),
    ("rate 是唯一能定位到词", "包单个词 0.7 → 时长 +33%、名次 3→2；edit 模板比 tts 模板更灵（0.8→×1.154 vs ×1.03）。但精度不如 rubberband（<1%），生产链不改。",
     "MEMORY.md §dots.tts", "定稿", "重音"),
    ("换 seed 不能修起伏", "854 对同文本跨 seed 只差 1.4dB、判定一致 99%、0 例「一个平一个陡」。起伏靠粒度：太平往细拆、太陡往粗并。",
     "REQUIREMENTS.md 第29条", "定稿", "坑,起伏"),
    ("WORLD 与 formant 无效", "formant=preserved 对纯 tempo 拉伸无效（md5 相同）；WORLD(pyworld) 声纹 0.702 更差，已弃。transients=crisp 毁短句起音 ⇒ 只用 pitchq=quality。",
     "MEMORY.md §语速", "定稿", "坑,后期"),
    ("DNSMOS 不能测表演", "DNSMOS 只测伪影不测表演，L083 截断与 L053 A/B 都判反；时长偏差 r=0.42，短句禁用绝对阈值。",
     "MEMORY.md §社区评测", "定稿", "坑,评测"),

    # ---------------- 情绪判定
    ("情绪判据表", "6 类单类 AUC：兴奋=A×V 0.898 / 激动反抗=D 0.886 / 警惕=e2v disgusted 0.834 / 紧张=A×(1−D) 0.812 / 平静=V 0.808 / 委屈=1−A 0.779。用单类 AUC 替代 7 类 top-1。",
     "G:/_setup/emo_bench/REPORT_EMOTION_JUDGE.md", "定稿", "情绪,判据"),
    ("三档分位判定", "按正例分位判档：≥P25 到位 / P10–P25 勉强 / <P10 没演出来。用负例阈值判档会因判据方向不一致而反转。",
     "G:/_setup/emo_bench/verdict.py", "定稿", "情绪,判据"),
    ("TTS 压低 V", "TTS 转换系统性压低 valence 0.15–0.30，EQ 与降速都补不回来（EQ 仅 +0.005~0.011）。",
     "REPORT_EMOTION_JUDGE.md", "定稿", "情绪"),
    ("文本也影响 V", "同一 ref 下，中性句 V=0.330、兴奋句 V=0.574（差 0.24）。想抬 V 要同时换文本。",
     "REPORT_EMOTION_JUDGE.md", "定稿", "情绪"),
    ("兴奋救回方案", "Expresso 004_speaker1_22s_24s.wav（V=0.898, F0=285）+ 兴奋文本 + 无标签 → A×V 0.467/0.404/0.392/0.379，4/5 过 P25(0.374)。打标签反而掉到 0.339。",
     "REPORT_EMOTION_JUDGE.md §兴奋", "定稿", "情绪,兴奋"),
    ("ref 天赋映射", "8 档 ref 天赋：C_excited 92% / C_angry 88%（激动反抗）、C_soft 92% / E_calm 76%（委屈）、E_begging 36%（警惕）。选对 ref 比调参数重要。",
     "G:/_setup/out_sv/ref_talent.json", "定稿", "情绪,ref"),
    ("ref V 传导非线性", "V≤0.6 时传导率 0.65–0.70；V=0.898 时降到 0.55–0.67。高 V ref 的收益会被衰减。",
     "REPORT_EMOTION_JUDGE.md", "定稿", "情绪,ref"),

    # ---------------- 声纹链路
    ("声纹四模型全 5/8", "CAM++英文(VoxCeleb) / CAM++中文(3D-Speaker) / WavLM-XVector / ECAPA-VoxCeleb / ResNet293 五个模型在 8 类情绪上是 5/8，没有一个全能。",
     "G:/_setup/REPORT_SPEAKER_EMOTION_REF.md", "定稿", "声纹"),
    ("1-NN + Z-norm", "每条 ref 单独当模板（不取平均），s_norm=(s−μ)/σ，μ/σ 用 393 条电影对白估。不做 Z-norm 会被单条模板吸走（7_hooper_begging 曾吸走 153/393）。",
     "G:/_setup/sv_1nn.py / sv_znorm.py", "定稿", "声纹"),
    ("情绪音色方差 > 说话人音色", "同角色不同情绪互比可低到 −0.019（Charles selfintro vs veux_partir），跨角色 0.34。⇒ 一个角色只能配一个中性 ref，情绪 ref 另立一档。",
     "REPORT_SPEAKER_EMOTION_REF.md", "定稿", "声纹,情绪"),
    ("跨语言声纹链路", "59 条英文成品 × 法语 ref 模板：Charles 23/23 = 100%，Thomas 26/36 = 72%，合计 83%，高置信 91%。跨语言可行但损失约 17%。",
     "G:/_setup/spk_sb_eval.py 产出", "定稿", "声纹"),
    ("Charles 音色来源", "Charles = 法语原声切片 castle_fr_ref/（真人童声），不要用文字描述硬造（必偏女性化；deep/husky 过冲到成年男，sad/tearful/timid 把音色调软）。",
     "MEMORY.md §角色音色", "定稿", "声纹,角色"),
    ("语义反证规则", "maman/ma mère→Charles；papa/mon père→Thomas；à/pour Charles→Thomas；je suis Charles→Charles。用于纠锚点混人。",
     "REPORT_SPEAKER_EMOTION_REF.md", "定稿", "声纹,锚点"),

    # ---------------- 测量口径
    ("rel_z 唯一核", "副词重音唯一测量核 = G:/_setup/_align_lib.py。rel 分母 = 句内全部内容词 sps 中位（含自身）。旧库三种分母并行，_anchor_ours*.json 与 _anchor_compare.json 已作废不可引用。",
     "MEMORY.md §副词重音对齐线", "定稿", "测量,重音"),
    ("rel_z 建在句内归一上", "rel_z 必须建在句内归一的 rel 上：真人句间方差占 28%（0.58σ）是纯噪声。log(rel)=0.2041−0.4339·log(nsyl)，sd 0.3575。判据 REL_Z_OK=1.6。",
     "MEMORY.md §副词重音对齐线", "定稿", "测量,重音"),
    ("真人重读两通道", "句内最长词 rel_z +1.19（loc 只 +0.73）/ 句内最高音词 loc +2.72（rel 只 1.00）。我们只做了音高：loc 分位 87 / rel_z 分位 66。噪声上沿 +1.47 > 目标 +1.19 ⇒ 时长轴只能顺带捡。",
     "MEMORY.md §副词重音对齐线 / _anchor_report.md", "定稿", "测量,重音"),
    ("音节数必须 cmudict", "启发式音节数在 55 条副词上错 17 条，必须用 cmudict（pip install --no-deps cmudict）。",
     "MEMORY.md §副词重音对齐线", "定稿", "测量"),
    ("voiced wpm 跨源不可比", "voiced/span 比值旁白 0.40 vs Charles 0.60，span 口径 107 vs 111 wpm 其实差不多。voiced wpm 跨源比较是第 8 次分母塌陷。",
     "MEMORY.md §副词重音对齐线", "定稿", "测量,坑"),
    ("单条韵律分不能当闸门", "TTSDS2 prosody 与人耳相关只 0.34–0.60，总分 0.67 是四因子合起来的。拆成逐条后「基础越好标签伤得越重」是选择效应，零分布 ctl→ctl 也有 +2.44/−0.54/−2.38。只做批次验收。",
     "MEMORY.md §韵律体检前置", "定稿", "测量,坑"),
    ("零分布对照规则", "按某测量值分层比较前，必须先跑「同一程序、只换掉被检验变量」的零分布对照。同型错误已犯 9 次。",
     "MEMORY.md §韵律体检前置", "定稿", "方法论,坑"),

    # ---------------- 工作方式
    ("同一坑禁止踩第二次", "遇到问题先查 MEMORY.md / skills / 官方 issue，只认「最后解决了没有 + 怎么解决」。每条结论必须写清「我们哪里做错了」。",
     "用户 2026-10-19 明确要求", "定稿", "工作方式,红线"),
    ("停顿按角色标定", "停顿标定基准必须是本角色不是旁白：Charles 真人原声 n=33 处实测中位 0.43s（p25 0.35 / p75 0.60 / 区间 0.15-0.76）。马修母带 1.16/1.56 是 97wpm 睡前朗读，给情绪化对话用会长出 2-3 倍。",
     "REQUIREMENTS.md 第19-0条", "定稿", "停顿,红线"),
    ("停顿逐处 LLM 判定", "停顿由 LLM 逐处判定（pause_llm.json），不给统计常数，每处写 why。优先级：对抗/抢话 0.15-0.35 > 情绪落点 0.45-0.62 > 填充词 0 > 从句未完 0.20-0.25。同一句每个停顿不一样长。",
     "REQUIREMENTS.md 第19-0条", "定稿", "停顿"),
    ("链路顺序不许颠倒", "生成 → 降速(tempo≥0.70) → clean(整体增益−24dBFS) → 停顿+底噪 → 交付。先停后变速会把停顿一起拉长；先铺底噪再 clean 会把底噪放大 34dB。",
     "REQUIREMENTS.md §五之二", "定稿", "工作流,红线"),
    ("底噪统一 −58dBFS", "dots.tts 静音段是 −199.9dB 一听就假，必须整条叠加底噪（不是只填空段）。底噪 −58dBFS，面板来自马修真人原声 wonder_train.wav。验收：静音段 p05 跨度 ≤16dB。",
     "REQUIREMENTS.md 第25a-25b条", "定稿", "音质"),

    # ---------------- 元
    ("RAG 外部记忆", "项目长期记忆 = G:/_setup/rag/。双通道（FTS5 中文 bigram 词法 + bge-small-zh 语义）RRF 融合 + facts.jsonl 硬结论账本。用法：python rag.py search \"...\"。每逢新结论先进账本再进日志。",
     "G:/_setup/rag/rag.py", "定稿", "元,工具"),
]


def fid(t, c):
    return hashlib.sha1((t + c).encode()).hexdigest()[:10]


def main():
    old = {}
    if os.path.exists(FACTS):
        with open(FACTS, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    old[r["id"]] = r
    n_new = n_upd = n_same = 0
    for topic, concl, ev, status, tags in F:
        k = fid(topic, concl)
        rec = {"id": k, "topic": topic, "conclusion": concl, "evidence": ev,
               "status": status, "date": TODAY,
               "tags": [t for t in tags.split(",") if t]}
        if k not in old:
            old[k] = rec
            n_new += 1
        elif old[k].get("conclusion") != concl or old[k].get("evidence") != ev:
            old[k].update({"conclusion": concl, "evidence": ev, "status": status, "date": TODAY})
            n_upd += 1
        else:
            n_same += 1
    with open(FACTS, "w", encoding="utf-8") as f:
        for r in old.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"账本 {len(old)} 条（新增 {n_new} / 更新 {n_upd} / 未变 {n_same}）→ {FACTS}")


if __name__ == "__main__":
    main()
