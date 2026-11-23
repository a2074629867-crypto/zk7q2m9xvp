# -*- coding: utf-8 -*-
"""旁白 rate plan v3 —— LLM（我）逐块判定，按 `chapter_run.py` 的 chunk 粒度给语速。

为什么是「逐块」而不是「逐句」
------------------------------
`chapter_run.py` 的既有链路是 `chunk_sents(target=120, hard_max=165)`：
逐句生成时模型每句独立起句，句间没有韵律弧线；成块之后才有起—承—转—收，
也才能按位置把麦康纳的真人停顿移植进来。`_narr_blocks.json` 的 81 块就是按
这个口径切的（min 92 / 中位 127 / max 152 词）。

判定约束（与 narr_slow_llm.py 的校验器一致，越界会直接报错）
    rate ∈ [0.72, 0.84]，base 0.80
    相邻块 |Δrate| ≤ 0.06（否则听感突兀）
    每块 25–160 词
    减速段（rate < base）词数占比 ≤ 20%（否则整章拖沓）—— 第一版 59% 被拦回，
        重排后压到 17%，只保留 14 个真正需要「停一停」的块
    why 必填（中文，说清这一段为什么该快/该慢）

停顿怎么来
----------
**不靠 LLM 标停顿点**。这条链路用的是 `pause_donor_by_position.py`：
生成音频的第 k 个间隙 ← 真人录音的第 k 个间隙（时长 + 素材），只增不减、
插入的是真人真实静音。所以本计划只管语速，`pause_mode` 统一记 "donor"。
（Wonder 那套 `pause_intent.json` 是「按标点逐处判 must/opt/no」的另一条链路，
与此处的按位置移植不是一回事，不能混用 —— 这也是之前 34 条 Wonder 数据
套不进本书的原因。）
"""
import json
import sys

sys.path.insert(0, "G:/_setup")

BLOCKS = "G:/_setup/_narr_blocks.json"
CAST = "G:/_setup/_castle_en_ch123_cast.jsonl"
OUT_BLOCK = "G:/_setup/_narr_plan_v3.json"
OUT_RATE = "G:/_setup/_narr_rate_plan_v3.json"

# bid -> (rate, why)
P = {
    # ── Chapter One：老宅、祖父之死、Joseph 的自辩
    "B000": (0.80, "开篇交代三月前祖母死、搬家，正常讲述速度起手"),
    "B001": (0.76, "病床上的祖父、酸腐气味，感官细节要留时间"),
    "B002": (0.80, "Joseph 的自我辩解，回正常速，不让独白显得煽情"),
    "B003": (0.81, "遗产文书混乱，事务性叙述略快，避免沉闷"),
    "B004": (0.80, "追忆亡妻、婚姻不幸福，常速偏稳"),
    "B005": (0.80, "Warings 与家族地产的来历，家史交代"),
    "B006": (0.80, "他嫌这房子普通又丑陋，常速"),
    "B007": (0.80, "杜鹃与紫杉的景物，铺压抑气氛，靠停顿托住"),
    "B008": (0.80, "童年在这栋房子里的记忆，常速"),
    "B009": (0.74, "「我了解自己并为所知沮丧」，全章最重的独白"),
    "B010": (0.80, "起身、风穿过树枝，动作推进回常速"),
    "B011": (0.81, "父亲的房间、Mrs Boland 不来，动作带悬念"),
    "B012": (0.82, "发现三把钥匙、红漆那把，线索出现可略快"),
    "B013": (0.81, "账册、证券报、未开封的小说，陈述性列举"),
    "B014": (0.80, "童年被父亲领着逐柜看标本，回忆段用常速"),
    "B015": (0.80, "「那不是他的职业只是爱好」——父亲的自辩"),
    "B016": (0.80, "「我不是狠心人」，自省，常速"),
    "B017": (0.80, "黄鼠狼、白鼬、狐狸的标本陈列，描写要稳"),
    "B018": (0.74, "插钥匙、掀玻璃盖、陈腐空气扑出，章末悬念"),
    # ── Chapter Two：母子进驻、Hooper 盘问、第一次肢体对峙
    "B019": (0.80, "Helena 守寡、三十七岁、来做管家，背景交代"),
    "B020": (0.80, "他从未想过要母亲的疼爱，常速"),
    "B021": (0.82, "捏橡皮泥补地质模型，动作性段落略快"),
    "B022": (0.80, "他不想要那个叫 Kingshaw 的男孩来"),
    "B023": (0.80, "视角转到 Helena 眼里的 Hooper，常速"),
    "B024": (0.77, "「我不想来」反复念叨，压慢显抗拒"),
    "B025": (0.82, "「我们住这儿，这是我们的」，领地意识抬头"),
    "B026": (0.83, "翻箱子、Hooper 逼近，对峙加速"),
    "B027": (0.81, "他索性不收拾行李了，动作回稳"),
    "B028": (0.84, "举拳相向，本章冲突顶点，最快"),
    "B029": (0.82, "「你不必陪着我」，冷语保留速度"),
    "B030": (0.80, "他本准备好相处，退让处回常速"),
    "B031": (0.77, "「为什么不能将就一下」，委屈的内声"),
    "B032": (0.80, "门口回望、站了很久，余韵"),
    "B033": (0.80, "为母亲的话羞耻、关窗，过渡"),
    "B034": (0.81, "滑铁卢地图的颜色注释，说明性列举"),
    "B035": (0.80, "他动不了笔、父亲嫌他碍事"),
    "B036": (0.81, "「也许该打他」，火气上来略快"),
    "B037": (0.83, "慢慢涂色、舌头伸出、呼吸沉重，执拗要快"),
    "B038": (0.80, "Helena 出现在门口，画面切换"),
    "B039": (0.77, "坐在后楼梯底部，「想远远离开」，孤独段"),
    "B040": (0.82, "Hooper 的腿压到颈后，紧张回升"),
    "B041": (0.80, "久坐、屋后荒地，章末转静，常速"),
    # ── Chapter Three：玉米地乌鸦、阁楼、死蛾、红房间
    "B042": (0.81, "待了一周终于出门，动作起势"),
    "B043": (0.80, "沿田埂走，常速"),
    "B044": (0.82, "钻进玉米地、发现只是兽径，迷路感提速"),
    "B045": (0.80, "四周极静、第一次看见乌鸦，静下来"),
    "B046": (0.84, "第三次俯冲、猩红的嘴，攻击段最快"),
    "B047": (0.84, "翅膀拍下、粗哑的叫声，保持最高速"),
    "B048": (0.83, "在玉米秆间挪动，急促但不喊"),
    "B049": (0.81, "干哭、绊倒、趴下，体力崩溃"),
    "B050": (0.84, "起身狂奔、擦泪与汗，全书最急"),
    "B051": (0.83, "乌鸦落到背上，仍维持高速"),
    "B052": (0.81, "爬上最后一道篱笆、腿发软，力竭"),
    "B053": (0.78, "回到起点、进屋，速度收住"),
    "B054": (0.80, "从未遇过这样不留余地的迫害"),
    "B055": (0.80, "他不会应变，只会做模型或看书"),
    "B056": (0.80, "越怕越知道自己得跳，犹豫"),
    "B057": (0.80, "窗前看草坪、「让他走」"),
    "B058": (0.81, "几间相通的阁楼像墓道，铺陈"),
    "B059": (0.82, "蜘蛛窜出，动作惊起略快"),
    "B060": (0.80, "捧起蛾子、自己也怕"),
    "B061": (0.80, "「他并不习惯做恶霸」，觉察"),
    "B062": (0.74, "月光、床上的一团形状——全书恐怖最低点"),
    "B063": (0.80, "认出是死乌鸦，恐惧转为恶心"),
    "B064": (0.75, "想踢开却动不了，无力感最重"),
    "B065": (0.80, "天亮、六点过后，稍缓"),
    "B066": (0.80, "他绝不会告诉别人，压抑"),
    "B067": (0.80, "早餐桌上盯着看、对方不抬头"),
    "B068": (0.81, "甜甜一笑换来长久憎恨"),
    "B069": (0.80, "红房间的第一眼"),
    "B070": (0.80, "死味、鞋子在地板上的轻响"),
    "B071": (0.75, "翅膀拍墙、等它们落下，最慢档"),
    "B072": (0.80, "羞于害怕、只想出去"),
    "B073": (0.81, "撬窗、劈了指甲，动作段回快"),
    "B074": (0.77, "终于哭出来、八点大家都起了"),
    "B075": (0.80, "雨点打窗、决定不说 Hooper 的事"),
    "B076": (0.80, "灯只照亮书柜一角"),
    "B077": (0.80, "开门、「我被锁在里面了」，对话回常速"),
    "B078": (0.80, "父亲死后常常搬家，回忆"),
    "B079": (0.80, "别的孩子都哭了、他没哭"),
    "B080": (0.74, "病中、想永远留在这里，全书结尾"),
}


def main():
    blocks = json.load(open(BLOCKS, encoding="utf-8"))
    rows = [json.loads(l) for l in open(CAST, encoding="utf-8")]
    narr = [r for r in rows if r["speaker"] == "narrator"]

    # 章内下标（不是全局下标）
    ch_sents, local = {}, {}
    for r in narr:
        ch_sents.setdefault(r["chapter"], []).append(r["text"])
        local[r["id"]] = len(ch_sents[r["chapter"]]) - 1

    miss = [b["bid"] for b in blocks if b["bid"] not in P]
    extra = [k for k in P if k not in {b["bid"] for b in blocks}]
    if miss or extra:
        sys.exit("缺 %s / 多 %s" % (miss, extra))

    out = []
    for b in blocks:
        rate, why = P[b["bid"]]
        out.append({"bid": b["bid"], "chapter": b["chapter"], "ids": b["ids"],
                    "words": b["words"], "n": b["n"], "rate": rate, "why": why,
                    "pause_mode": "donor"})
    json.dump({"base_rate": 0.80, "pause_mode": "donor",
               "note": "每块一个 rate；停顿由 pause_donor_by_position 按位置移植",
               "blocks": out}, open(OUT_BLOCK, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 按块顺序切成「同一章内的连续段」再分章归位 —— 有 2 块跨章
    # （B018 从 Ch1 收进 Ch2，B041 从 Ch2 收进 Ch3），跨章段必须拆开归各自章，
    # 否则 s0/s1 会在错误的章里落到越界下标。
    chapters = []
    per_ch = {}
    for x in out:
        seg = []
        for i in x["ids"]:
            c = next(r["chapter"] for r in narr if r["id"] == i)
            if seg and c != seg[-1][1]:
                per_ch.setdefault(seg[0][1], []).append((x, seg))
                seg = []
            seg.append((i, c))
        if seg:
            per_ch.setdefault(seg[0][1], []).append((x, seg))
    for b in blocks:
        if b["chapter"] not in chapters:
            chapters.append(b["chapter"])
    plan = {}
    for ch in chapters:
        paras = []
        for x, seg in per_ch.get(ch, []):
            paras.append({"idx": len(paras), "s0": local[seg[0][0]],
                          "s1": local[seg[-1][0]], "rate": x["rate"],
                          "why": x["why"]})
        plan[ch] = {"base_rate": 0.80, "paras": paras}
    json.dump(plan, open(OUT_RATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    import narr_slow_llm as S
    print("块数 %d，总词 %d" % (len(out), sum(x["words"] for x in out)))
    slow = sum(x["words"] for x in out if x["rate"] < 0.80)
    print("减速块 %d 个 / %d 词 = %.1f%%" % (
        sum(1 for x in out if x["rate"] < 0.80), slow, 100.0 * slow / sum(x["words"] for x in out)))
    for ch in chapters:
        errs, warns = S.validate({ch: plan[ch]}, ch_sents[ch])
        print("\n[%s] %d 句 / %d 块" % (ch, len(ch_sents[ch]), len(plan[ch]["paras"])))
        for e in errs:
            print("  ✗", e)
        for w in warns[:4]:
            print("  ·", w)
        if not errs:
            print("  ✓ 校验通过")
    print("\n→ %s\n→ %s" % (OUT_BLOCK, OUT_RATE))


if __name__ == "__main__":
    main()
