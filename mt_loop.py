# -*- coding: utf-8 -*-
"""mt_loop.py —— 生成 → 门禁 → 重生 的闭环调度器。

与「每单元固定生成 3 个候选再挑」的区别：
  旧：3 条/单元，不管质量，事后比 centroid 挑（大量算力浪费在已经够好的单元上）
  新：1 条/单元 → 门禁 → 不过才生成第 2 条 → …，到 PASS 或上限就停

实测依据（536 候选 / 180 单元）：
  候选级 PASS 79.5% ⇒ 平均只需 1.26 条/单元（旧方案 3 条），省 58% 生成时间。

用法：
  python mt_loop.py --init                      # 用现有 prom 初始化状态文件
  python mt_loop.py --status                    # 看进度
  python mt_loop.py --run --max-new 20          # 最多为 20 个未过单元各生成 1 条新候选
  python mt_loop.py --run --units N0001,N0002   # 只跑指定单元
  python mt_loop.py --run --plan-next ch4       # 新章节：按需生成（先 1 条，不够再加）

状态文件 _mt_loop_state.json 是唯一真相，可随时中断续跑。
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, "G:/_setup")
import _gate
from _gate import gate_one, load_plan_texts
from _verify_accent import read_prom
from _wpt_run import write_textgrid
import mt_gen

ROOT = "G:/_setup"
STATE = os.path.join(ROOT, "_mt_loop_state.json")
PROM = os.path.join(ROOT, "_wpt_out")
TG = os.path.join(ROOT, "_wpt_tg")
BATCH = os.path.join(ROOT, "_wpt_loop_batch")
WPTPY = os.path.join(ROOT, "wpt_venv", "Scripts", "python.exe")
ASRPY = os.path.join(ROOT, "asr_venv", "Scripts", "python.exe")
CFG = os.path.join(ROOT, "_wpt", "mt.yaml")

SEED_POOL = [42, 1234, 777, 2024, 8888, 31337, 5150, 909]
MAX_CAND = 3
JOBS = 6


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"meta": {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "max_cand": MAX_CAND, "seeds_used": []},
            "units": {}}


def save_state(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


# 声纹审计（第二道门）。来源：mt_spk_audit.py 产出的 _spkaudit_<ch>.json
# 为什么必须加：重音门禁只判「读没读到重音」，测不出「换了个人」。
# 2026-10-26 的 0.29 事故就是 PASS 了但音色换了。这里把 VOID 的 take 直接排除。
AUDIT = {}


def load_audit(ch=None):
    AUDIT.clear()
    pat = "_spkaudit_%s.json" % ch if ch else "_spkaudit_*.json"
    for p in sorted(glob.glob(os.path.join(ROOT, pat))):
        try:
            for r in json.load(open(p, encoding="utf-8")):
                AUDIT[(str(r["uid"]), str(r["seed"]))] = r["verdict"]
        except Exception:
            continue
    if AUDIT:
        log("载入声纹审计 %d 条（VOID %d）"
            % (len(AUDIT), sum(1 for v in AUDIT.values() if v == "VOID")))
    return len(AUDIT)


def spk_void(uid, seed):
    return AUDIT.get((str(uid), str(seed))) == "VOID"


def unit_verdict(tries, uid=None):
    """一个单元的定级：任一 PASS 即 PASS；否则按 PASS > SKIP > MANUAL > ARTIFACT 取最好的。

    声纹 VOID 的 take 不参与定级；如果全部 take 都被判换人，本单元直接 ARTIFACT（要重生）。
    """
    pool = [t for t in tries if not (uid is not None and spk_void(uid, t.get("seed")))]
    if tries and not pool:
        return "ARTIFACT"
    vs = {t["verdict"] for t in (pool or tries)}
    for v in ("PASS", "SKIP", "MANUAL", "ARTIFACT"):
        if v in vs:
            return v
    return "ARTIFACT"


def stable_top1(tries, k=2, min_n=3):
    """最近 k 次重生成的主重音词完全相同 ⇒ 判定为文本驱动，重生无效。

    实测（2026-10-25）：
      N0033 3 次全是 which、N0091 3 次全是 dull、N0101 3 次全是 Above —— 重生零收益
      N0009 3 次里从 For 变成 middle —— 重生有效，且只有 1/3 概率
    所以「top1 稳定」是比「试满 N 条」更省时间的停止条件。
    """
    if len(tries) < min_n:
        return False
    seq = sorted(tries, key=lambda t: (t.get("round", 0), str(t.get("seed", ""))))
    return len({str(t.get("top1", "")).lower() for t in seq[-k:]}) == 1


def plateau(tries):
    """已经停止进化：state 没过，但 top1 连续稳定。"""
    return stable_top1(tries)


def pick_best(tries, uid=None):
    """PASS 取 sep 最高；否则取 sep 最高（MANUAL 次之）。

    ★ 声纹 VOID / 音频检测 FAIL 的一律不选。**一个都没有就返回 None。**
      2026-10-31 审计：原实现是 `pool = ok or usable(tries) or tries`，
      最后那级 `or tries` 把前两级「排除 VOID / audio_fail」的意图整个撤销 ——
      实测 pick_best(2 条全 audio_fail) 会返回其中一条被门禁否掉的 take，
      于是 state 出现 unit=ARTIFACT 但 pick 指向被拒 take 的自相矛盾。
    """
    def usable(ts):
        return [t for t in ts
                if not (uid is not None and spk_void(uid, t.get("seed")))
                and not t.get("audio_fail")]

    def clean(ts):
        """音频检测真跑过（没 det_err）的才算过关卡；没检的排在后面。"""
        return [t for t in ts if not t.get("det_err")]

    if not tries:
        return None
    ok = clean(usable([t for t in tries if t["verdict"] == "PASS"]))
    pool = ok or clean(usable(tries)) or usable(tries)
    if not pool:
        return None                 # 全被拒：不挑，让 unit 保持 ARTIFACT
    return max(pool, key=lambda t: (t.get("sep") if t.get("sep") is not None else -9,
                                    -t.get("pos", 99)))


# ---------------- init ----------------

def cmd_init(args):
    load_audit()
    st = load_state()
    plan = load_plan_texts()
    gate_rows = json.load(open(os.path.join(ROOT, "_mt_gate.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(ROOT, "_mt_gate.json")) else []
    by = defaultdict(list)
    for r in gate_rows:
        by[r["uid"]].append(r)

    # 章节映射
    chmap = {}
    for p in ["B:/mt-tts/data/plan/mt_plan3b.json", os.path.join(ROOT, "_mt_plan3b.json")]:
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            items = d if isinstance(d, list) else d.get("items", [])
            for it in items:
                chmap[str(it.get("id"))] = it.get("ch")
            break

    n_new = 0
    for uid, rows in by.items():
        if uid in st["units"]:
            continue
        tries = []
        for r in rows:
            tries.append(dict(seed=str(r["seed"]), wav="_mt_raw_s%s/%s.wav" % (r["seed"], uid),
                              verdict=r["verdict"], code=r["code"], sep=r["sep"],
                              top1=r["top1"], pos=r["pos"], n=r["n"], gap=r["gap"],
                              cov=r.get("cov"), round=0))
        st["units"][uid] = dict(ch=chmap.get(uid), text=plan.get(uid, ""),
                                state=unit_verdict(tries, uid), tries=tries,
                                pick=pick_best(tries, uid))
        n_new += 1
    save_state(st)
    log("init: 新增 %d 个单元，总计 %d" % (n_new, len(st["units"])))
    cmd_status(args)


# ---------------- status ----------------

def cmd_status(args):
    load_audit()
    st = load_state()
    us = st["units"]
    if not us:
        log("状态为空，先跑 --init")
        return
    c = Counter(u["state"] for u in us.values())
    print("\n=== 单元状态（%d）===" % len(us))
    for v in ("PASS", "SKIP", "PLATEAU", "MANUAL", "ARTIFACT"):
        k = c.get(v, 0)
        if not k:
            continue
        print("  %-9s %4d  %5.1f%%  %s" % (v, k, 100.0 * k / len(us), "█" * int(50 * k / len(us))))
    nc = Counter(len(u["tries"]) for u in us.values())
    print("\n  候选数分布: %s" % dict(sorted(nc.items())))
    print("  平均候选数: %.2f（固定 3 候选方案 = 3.00）"
          % (sum(len(u["tries"]) for u in us.values()) / len(us)))
    by_code = Counter(t["code"] for u in us.values() for t in u["tries"])
    print("  待重生单元的首因: %s"
          % dict(Counter((u["pick"] or {}).get("code") for u in us.values()
                         if u["state"] != "PASS").most_common()))


# ---------------- run ----------------

def collect_todo(st, units=None, max_new=None, max_cand=None):
    todo = []
    for uid, u in st["units"].items():
        if u["state"] in ("PASS", "SKIP"):
            continue
        # 先判「top1 已经稳定」：这是文本驱动的证据，比试满条数更早、更省
        if stable_top1(u["tries"]):
            u["state"] = "PLATEAU"
            continue
        if len(u["tries"]) >= (max_cand or MAX_CAND):
            continue
        if units and uid not in units:
            continue
        todo.append(uid)
    todo.sort(key=lambda u: -len(st["units"][u]["tries"]))   # 优先补候选少的？反之：已有的先补满
    if max_new:
        todo = todo[:max_new]
    return todo


def next_seed(st, uid):
    used = {t["seed"] for t in st["units"][uid]["tries"]}
    for s in SEED_POOL:
        if str(s) not in used:
            return s
    return None


def gen_one_round(st, uids, use_rate=False):
    """为一批 uid 各生成 1 条新候选。返回 {uid: wav_path}。

    默认 **不带 rate 标签**（原速生成）。理由：用户明确「不降速了」，
    而 _mt_rate_<ch>.json 是旧 TEMPO=0.80 口径的产物（ch1 183 条里 161 条要降速），
    直接沿用会把降速重新带回生产链。需要旧口径时显式 --rate。
    """
    plan = {u: st["units"][u] for u in uids}
    by_seed = defaultdict(list)
    for uid, u in plan.items():
        s = next_seed(st, uid)
        if s is None:
            log("  %s 无可用 seed，跳过" % uid)
            continue
        by_seed[s].append(uid)

    made = {}
    for seed, us in by_seed.items():
        outdir = os.path.join(ROOT, "_mt_raw_s%d" % seed)
        os.makedirs(outdir, exist_ok=True)
        rate = {}
        if use_rate:
            rf = os.path.join(ROOT, "_mt_rate_%s.json" % st["units"][us[0]]["ch"])
            if os.path.exists(rf):
                rate = json.load(open(rf, encoding="utf-8"))
                log("  !! 使用旧 rate 文件 %s（%d 条要降速）"
                    % (os.path.basename(rf), sum(1 for v in rate.values() if v < 0.999)))
        items = [(uid, st["units"][uid]["text"], rate.get(uid, 1.0)) for uid in us]
        tag = "loop_s%d_%s" % (seed, us[0])
        t0 = time.time()
        ok = mt_gen.gen_batch(items, tag, outdir, seed)
        log("  seed %d：%d/%d 成功，%.1f 分钟" % (seed, ok, len(items), (time.time() - t0) / 60))
        for uid in us:
            p = os.path.join(outdir, uid + ".wav")
            if os.path.exists(p):
                made[uid] = (seed, p)
    return made


def build_prom(made, chunk=120):
    """ASR → TextGrid → wpt，产出/刷新 .prom。返回 staged=[(uid, seed, base)]。

    音频被替换过（例如改了 rate 策略重生成）时也用它重新出 prom。
    ASR 分块（命令行长度限制）并 --append 合并；wpt 一次批量并行。
    """
    if not made:
        return []
    paths = [p for _s, p in made.values()]
    asr_json = os.path.join(ROOT, "_words_loop.json")
    if os.path.exists(asr_json):
        os.remove(asr_json)
    lst = os.path.join(ROOT, "_words_loop.list")
    t0 = time.time()
    for i in range(0, len(paths), chunk):
        part = paths[i:i + chunk]
        with open(lst, "w", encoding="utf-8") as f:
            f.write("\n".join(part))
        r = subprocess.run([ASRPY, os.path.join(ROOT, "_asr_lib.py"),
                            "--out", asr_json, "--list", lst, "--append", "--trim"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=7200)
        if r.returncode != 0:
            log("  !! ASR 第 %d 块失败 rc=%d：%s"
                % (i // chunk + 1, r.returncode, (r.stderr or "")[-400:]))
    if not os.path.exists(asr_json):
        log("  !! ASR 无输出")
        return []
    # 路径分隔符统一：--list 写入时转成 /，而 os.path.join 给的是 \，
    # 不归一化就对不上 key（N0184 那批全丢就是这个原因）
    asr = {os.path.normpath(k).lower(): v
           for k, v in json.load(open(asr_json, encoding="utf-8")).items()}
    log("  ASR %d/%d 条，%.1f 分钟" % (len(asr), len(paths), (time.time() - t0) / 60))

    os.makedirs(BATCH, exist_ok=True)
    os.makedirs(TG, exist_ok=True)
    staged = []
    for uid, (seed, p) in made.items():
        key = os.path.normpath(p).lower()
        if key not in asr:
            log("  !! %s 无 ASR 结果（%s）" % (uid, p))
            continue
        base = "_mt_raw_s%d__%s" % (seed, uid)
        tg = os.path.join(TG, base + ".TextGrid")
        write_textgrid(tg, asr[key]["dur"], asr[key]["words"])
        shutil.copy2(p, os.path.join(BATCH, base + ".wav"))
        shutil.copy2(tg, os.path.join(BATCH, base + ".TextGrid"))
        staged.append((uid, seed, base))

    t0 = time.time()
    r = subprocess.run([WPTPY, "-m", "wavelet_prosody_toolkit.prosody_labeller",
                        "-j", str(JOBS), "-c", CFG, "-o", PROM, BATCH],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore", timeout=3600)
    log("  wpt %d 条，%.1f 分钟（rc=%d）" % (len(staged), (time.time() - t0) / 60, r.returncode))
    if r.returncode != 0:
        log("    stderr: " + (r.stderr or "")[-300:].replace("\n", " "))

    for f in os.listdir(BATCH):
        try:
            os.remove(os.path.join(BATCH, f))
        except OSError:
            pass
    return staged


AUDIO_GATE = True   # --no-audio-gate 关闭
_DET = None         # 缓存的 mt_detectors 模块
_DET_ERR = None     # 加载失败原因（一旦非 None 直接中止整轮，不许静默降级）


def _load_det():
    """加载检测器模块。**失败必须响亮** —— 2026-10-31 审计：

    原实现把 `import mt_detectors` 包在 per-take 的宽 except 里，失败只写
    `g["det_err"]` 就继续；本机默认 `python` 没有 numpy，于是**整批音频门禁
    一个都没跑，日志仍是全绿 PASS**。这种降级比不接还危险。
    """
    global _DET, _DET_ERR
    if _DET is not None:
        return _DET
    if _DET_ERR:
        return None
    try:
        import mt_detectors as _m
        _DET = _m
        return _DET
    except Exception as e:  # noqa: BLE001
        _DET_ERR = "%s: %s" % (type(e).__name__, e)
        return None


def analyse(st, made, round_no):
    """跑 prom 并把门禁结果写回 state。"""
    staged = build_prom(made)
    n = 0
    det_err_n = 0
    for uid, seed, base in staged:
        pf = os.path.join(PROM, base + ".prom")
        if not os.path.exists(pf):
            log("  !! %s 无 prom 输出" % uid)
            continue
        g = gate_one(st["units"][uid]["text"], read_prom(pf))
        if not g:
            log("  !! %s 门禁对齐失败" % uid)
            continue
        wav = "_mt_raw_s%d/%s.wav" % (seed, uid)
        g.update(seed=str(seed), wav=wav, round=round_no)
        # ★ 条件化音频检测（2026-10-31 接入）：只加两条有实测支撑的单条判据
        #   crest_clip（削波，AUC 1.00 / SNR 4.7）
        #   span_flatten（音高被压平，AUC 1.00 / SNR 2.96）
        #   其余（硬切/气声）因条件不满足会自己 SKIP，不会误杀。
        if AUDIO_GATE and os.path.exists(wav):
            DET = _load_det()
            if DET is None:
                # 加载不了就别装没事。这里直接抛，让整轮停掉。
                raise SystemExit(
                    "音频检测器加载失败，拒绝在无门禁状态下继续生成：%s\n"
                    "（通常是用错了解释器 —— 需要 G:/Python310/python.exe）" % _DET_ERR)
            try:
                role = (st["units"][uid] or {}).get("role") or "narr"
                _m = DET.acoustics(os.path.join(ROOT, wav), role)
                # ★ 2026-10-31 二次修：前置条件实现了但**没人填 ctx**，等于没写。
                #   以前传 `{}`，于是 need=path/text 一律为假 —— seg_drift 明明拿着
                #   文件路径，却因为 ctx 里没有 path 被 SKIP 掉。现在把手上有的都塞进去。
                _ctx = dict(path=os.path.join(ROOT, wav),
                            text=st["units"][uid].get("text"),
                            role=role, paused=False)   # 单条 take 不含插入停顿
                _d = DET.item_check(_m, _ctx)
                # ★ SKIP 不再整条丢掉 —— 否则「没测」和「测过且通过」在 state 里同形。
                #   但 state 要小：blocked 的原因有几百字，只留前 90 字。
                g["det"] = [dict(id=x["id"], verdict=x["verdict"],
                                 level=x["level"], why=(x.get("why") or "")[:90],
                                 escalate=x.get("escalate"), skip=x.get("skip"))
                          for x in _d]
                g["det_cov"] = DET.coverage(_d)
                _bad = [x for x in _d if x["verdict"] == "FAIL" and x["level"] == "veto"]
                if _bad:
                    g["audio_fail"] = ["%s: %s" % (x["name"], x["why"]) for x in _bad]
                    g["verdict"] = "ARTIFACT"
                    g["code"] = "audio_" + _bad[0]["id"]
            except Exception as _e:  # noqa: BLE001
                # 单条出错不影响整批，但必须留痕 + 标记「这条没检」
                g["det_err"] = "%s: %s" % (type(_e).__name__, str(_e)[:100])
                g["det_cov"] = dict(ran=0, total=0, skip=0, err=True)
                det_err_n += 1
        st["units"][uid]["tries"].append(g)
        st["units"][uid]["state"] = unit_verdict(st["units"][uid]["tries"], uid)
        st["units"][uid]["pick"] = pick_best(st["units"][uid]["tries"], uid)
        n += 1
        log("  %s r%d seed%s → %-8s %-13s sep=%+.2f top1=%s"
            % (uid, round_no, seed, g["verdict"], g["code"],
               g["sep"] if g["sep"] is not None else 0, g["top1"]))
    if det_err_n and n and det_err_n >= n:
        raise SystemExit("本轮 %d 条 take 的音频检测全部报错，拒绝继续（首条：%s）"
                         % (det_err_n, st["units"][uid]["tries"][-1].get("det_err")))
    if det_err_n:
        log("  !! %d/%d 条音频检测报错，这些 take 未过门禁" % (det_err_n, n))
    return n


def cmd_run(args):
    load_audit()
    st = load_state()
    if not st["units"]:
        log("状态为空，先跑 --init")
        return
    units = {x.strip() for x in args.units.split(",")} if args.units else None

    if args.plan_next:
        add_new_chapter(st, args.plan_next)
        save_state(st)

    rounds = args.rounds
    total = 0
    for r in range(1, rounds + 1):
        todo = collect_todo(st, units=units, max_new=args.max_new, max_cand=args.max_cand)
        if not todo:
            log("第 %d 轮：无待处理单元" % r)
            break
        log("=== 第 %d 轮：%d 个单元 ===" % (r, len(todo)))
        made = gen_one_round(st, todo, use_rate=args.rate)
        n = analyse(st, made, r)
        total += n
        save_state(st)
        c = Counter(u["state"] for u in st["units"].values())
        log("  第 %d 轮结束：本轮 %d 条，累计状态 %s" % (r, n, dict(c)))
        if args.once:
            break

    save_state(st)
    log("共处理 %d 条" % total)
    cmd_status(args)


def add_new_chapter(st, ch):
    """新章节按需生成：先把单元以 pending 状态加入（无候选）。"""
    plan = None
    for p in ["B:/mt-tts/data/plan/mt_plan3b.json", os.path.join(ROOT, "_mt_plan3b.json")]:
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            plan = d if isinstance(d, list) else d.get("items", [])
            break
    if not plan:
        log("找不到 plan")
        return
    n = 0
    for it in plan:
        uid = str(it.get("id"))
        if it.get("ch") != ch or uid in st["units"]:
            continue
        st["units"][uid] = dict(ch=ch, text=it.get("text", ""), state="ARTIFACT",
                                tries=[], pick=None)
        n += 1
    log("加入新章节 %s：%d 个单元" % (ch, n))


def cmd_reanalyse(args):
    """对已有 wav 重跑 prom（音频被替换后必须重跑，否则 prom 与音频对不上）。"""
    seed = int(args.reanalyse)
    uids = [x.strip() for x in (args.units or "").split(",") if x.strip()]
    made = {}
    for uid in uids:
        p = os.path.join(ROOT, "_mt_raw_s%d" % seed, uid + ".wav")
        if not os.path.exists(p):
            log("缺 %s" % p)
            continue
        made[uid] = (seed, p)
    if not made:
        log("没有可重分析的 wav")
        return
    staged = build_prom(made)
    log("重分析完成：%d/%d 条 prom 已刷新" % (len(staged), len(uids)))
    log("下一步：重跑 _gate.py --json _mt_gate.json，再重建 state")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--reanalyse", default=None, help="对 _mt_raw_s<N> 已有 wav 重跑 prom（传 seed）")
    ap.add_argument("--units", default=None)
    ap.add_argument("--max-new", type=int, default=None)
    ap.add_argument("--max-cand", type=int, default=MAX_CAND)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--once", action="store_true", help="只跑一轮")
    ap.add_argument("--plan-next", default=None, help="把某章单元以 pending 加入")
    ap.add_argument("--rate", action="store_true",
                    help="沿用旧 _mt_rate_<ch>.json 降速（默认关闭：用户要求不降速）")
    a = ap.parse_args()

    if a.init:
        cmd_init(a)
    elif a.status:
        cmd_status(a)
    elif a.run:
        cmd_run(a)
    elif a.reanalyse:
        cmd_reanalyse(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
