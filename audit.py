# -*- coding: utf-8 -*-
"""audit —— 把「反复栽倒的失效模式」变成一条命令能跑的静态检查。

为什么需要它（2026-11-11，一天之内同类问题栽 4 次后的结论）：

  改数值 ≠ 改分类；文档说改了 ≠ 代码改了；判据改对了 ≠ 产物重跑了。
  这三句话的共同点是：**没有任何一步会报错**。所以必须有脚本去抓。

六类失效模式 → 本脚本的检查项：
  A 两把尺子（同指标多实现/多口径）  → span_physical / span_single_source
  B 声明与实现脱节（文档说改了）      → dead_params / no_stretch_segments / peak_ceil /
                                        texts_hardcode / wpm_scale / dialog_cap
  C 陈旧产物（判据改了没重跑）        → stale_artifacts
  D 分类错但数值对                    → tier_literals / expr_coverage / tiers_track
  E 用噪声伪造信号                    → shape_jitter（查 apply_pause_shape 是否只抖动）
  F 抽样当分布 / 调阈值凑指标          → 无静态检查手段，只能靠 resume.py 常驻提醒

用法：
  G:/Python310/python.exe audit.py            # 全部
  G:/Python310/python.exe audit.py -v         # 附证据行
  G:/Python310/python.exe audit.py --only span,peak

退出码：0 = 全 PASS（可有 WARN）；1 = 有 FAIL。可以挂进 CI / 每次改完就跑。
"""
import argparse
import ast
import glob
import json
import os
import re
import sys
import time

SETUP = r'G:/_setup'
RESULTS = []          # (name, status, detail)


def add(name, status, detail):
    RESULTS.append((name, status, detail))


def read(p):
    try:
        return open(os.path.join(SETUP, p), encoding='utf-8').read()
    except Exception as e:
        return ''


def mtime(p):
    fp = os.path.join(SETUP, p)
    return os.path.getmtime(fp) if os.path.exists(fp) else 0


# ---------------------------------------------------------------- A 两把尺子
def chk_span_physical():
    """16bit 音频动态范围 96dB。span / cut_drop 超过 96 一定是把数字静音的谷底
    当成了「最低点」。今天两次假阳性（494 条结尾硬切 172dB、我们 span p95 111.5dB）
    都是靠这一条才抓出来的。"""
    bad = []
    for fn, keys in (('_narr_check6/_narr_check.json', ('energy_span', 'cut_drop')),
                     ('_narr_check5/_narr_check.json', ('energy_span', 'cut_drop'))):
        fp = os.path.join(SETUP, fn)
        if not os.path.exists(fp):
            continue
        try:
            rows = json.load(open(fp, encoding='utf-8'))
        except Exception:
            continue
        for r in rows:
            for k in keys:
                v = r.get(k)
                if isinstance(v, (int, float)) and v > 96.0:
                    bad.append('%s %s %s=%.1f' % (fn, r.get('unit'), k, v))
    if bad:
        add('span_physical', 'FAIL',
            '出现 >96dB 的值（16bit 上限），口径把静音谷底算进了动态范围：' + '; '.join(bad[:4]))
    else:
        add('span_physical', 'PASS', '所有 span / cut_drop ≤ 96dB')


def chk_span_single_source():
    """判据侧必须 import 带构建侧的同一个函数。两套实现 = 两把尺子。"""
    src = read('narr_check.py')
    ok = 'mt_rhythm_bands' in src and 'span_only' in src
    # 反向：文件里不能自己再实现一份 21 槽 span
    own = re.search(r'prof\.append\(float\(np\.percentile\(db', src)
    if ok and not own:
        add('span_single_source', 'PASS', 'narr_check 用 mt_rhythm_bands.span_only，无自建实现')
    elif own:
        add('span_single_source', 'FAIL',
            'narr_check 里还有自建的 21 槽 span 计算（两把尺子），应只调 span_only')
    else:
        add('span_single_source', 'FAIL', 'narr_check 没有 import mt_rhythm_bands.span_only')


# ------------------------------------------------------- B 声明与实现脱节
def _ast(fn):
    src = read(fn)
    if not src:
        return None
    try:
        return ast.parse(src)
    except Exception:
        return None


def _arg_dests(tree):
    """从 add_argument 调用里取真实 dest（含 dest= 显式指定，如 --in 的 dest='inp'）。"""
    out = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'add_argument'):
            continue
        flags = [x.value for x in n.args
                 if isinstance(x, ast.Constant) and isinstance(x.value, str)]
        longs = [f for f in flags if f.startswith('--')]
        if not longs:
            continue
        dest = None
        for kw in n.keywords:
            if kw.arg == 'dest' and isinstance(kw.value, ast.Constant):
                dest = str(kw.value.value)
        out.append(dest or longs[0][2:].replace('-', '_'))
    return out


def chk_dead_params():
    """add_argument 声明了、全文却没有 args.X 引用 = 死参数。
    `--bed-self` 就这么躺了很久：STATE 写「用 --bed --bed-self」，实际不生效。

    必须用 AST：正则版会把 `--in`（dest='inp'，代码读 a.inp）误报成死参数。"""
    bad = []
    for fn in ('mt_final_pause.py', 'dialog_gate.py', 'narr_gate_phys.py'):
        tree = _ast(fn)
        if tree is None:
            continue
        dests = set(_arg_dests(tree))
        used = {n.attr for n in ast.walk(tree)
                if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id == 'a'}
        for d in sorted(dests - used):
            bad.append('%s --%s (dest=%s)' % (fn, d.replace('_', '-'), d))
    if bad:
        add('dead_params', 'FAIL', '声明了但从未读取的参数：' + '; '.join(bad))
    else:
        add('dead_params', 'PASS', '无死参数（AST 取 dest，已排除别名假阳性）')


def chk_no_stretch_segments():
    """账本定稿「禁 stretch_segments」，10-20 就定了。ch123_final_build 一直没落。

    AST 只认**真实调用**：正则版把 `narr_post.py` 文档字符串里的
    「不用 stretch_segments」和 `ch123_slow5.py` 的 `def stretch_segments` 都算成违规。"""
    hits = []
    for fn in ('ch123_final_build.py', 'narr_post.py', 'mt_post.py', 'ch123_slow5.py'):
        tree = _ast(fn)
        if tree is None:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'stretch_segments':
                hits.append('%s:%d' % (fn, n.lineno))
            if (isinstance(n, ast.Attribute) and n.attr == 'stretch_segments'
                    and isinstance(n.value, ast.Name) and n.value.id in ('S', 'mt_post')):
                hits.append('%s:%d (模块调用)' % (fn, n.lineno))
    if hits:
        add('no_stretch_segments', 'FAIL', '生产链仍在调 stretch_segments：' + '; '.join(hits))
    else:
        add('no_stretch_segments', 'PASS', '生产链无 stretch_segments 实际调用')


def chk_peak_ceil():
    """峰值 ≤ −1 dBFS ⇒ 0.891。只允许更小，不允许更大。"""
    bad = []
    for fn in ('ch123_clean.py', 'mt_final_pause.py', 'ch123_unify.py'):
        src = read(fn)
        for m in re.finditer(r'^(CEIL|PEAK_CEIL)\s*=\s*([0-9.]+)', src, re.M):
            v = float(m.group(2))
            if v > 0.891 + 1e-6:
                bad.append('%s %s=%s (%.2fdBFS)' % (fn, m.group(1), m.group(2),
                                                    20 * __import__('math').log10(v)))
        for m in re.finditer(r'np\.abs\(y\)\.max\(\)\)?\s*>\s*([0-9.]+)', src):
            v = float(m.group(1))
            if v > 0.891 + 1e-6:
                bad.append('%s 内联阈值 %s' % (fn, m.group(1)))
    if bad:
        add('peak_ceil', 'FAIL', '峰值上限超过 −1dBFS：' + '; '.join(bad))
    else:
        add('peak_ceil', 'PASS', '峰值上限 ≤ 0.891（−1dBFS）')


def chk_texts_hardcode():
    """mt_final_pause 的原文表必须能从外部 jsonl 读，否则非 Wonder 编号的书
    LLM 判定分支根本不执行（标了也喂不进去）。"""
    src = read('mt_final_pause.py')
    has_arg = "--texts" in src
    has_import = 'from ch123_plan import' in src
    if has_arg and 'a.texts' in src:
        add('texts_hardcode', 'PASS',
            '支持 --texts' + ('（内建 ch123_plan 仍作兜底）' if has_import else ''))
    else:
        add('texts_hardcode', 'FAIL', 'mt_final_pause 没有可用的外部原文表入口')


def chk_wpm_scale():
    """停顿不随 wpm 线性缩放（wpm 只算语音段，停顿是独立量）。
    那次 ×0.57 让 1085 处少插 483.5s。

    合法形态是「默认 scale=1.0，只有显式 --scale 才缩放」，
    所以要查的是**默认路径**有没有缩放，而不是文件里有没有出现过这个公式。"""
    src = read('mk_pause_plan.py')
    if not src:
        add('wpm_scale', 'SKIP', 'mk_pause_plan.py 不存在')
        return
    guarded = re.search(r'if\s+a\.scale\s*:', src)
    default_one = re.search(r'^\s*scale\s*=\s*1\.0\s*$', src, re.M)
    formula = re.search(r'ref_wpm\s*/\s*a\.wpm', src)
    if formula and not guarded:
        add('wpm_scale', 'FAIL', '默认路径就按 wpm 比缩放停顿（无 a.scale 开关）')
    elif formula and guarded and default_one:
        add('wpm_scale', 'PASS', '默认 scale=1.0，仅 --scale 显式开启（可接受）')
    else:
        add('wpm_scale', 'PASS', '未按 wpm 缩放')


def chk_dialog_cap():
    """对白条间停顿硬上限 0.76s（夏尔真人实测最大值）。"""
    src = read('mt_final_pause.py') + read('mt_pause_rules.py')
    m = re.search(r'DIALOG_CAP\s*=\s*([0-9.]+)', src)
    caps = [float(x) for x in re.findall(r"D['\"]?:\s*([0-9.]+)", src)]
    if m and float(m.group(1)) <= 0.76 + 1e-6:
        add('dialog_cap', 'PASS', 'DIALOG_CAP=%s ≤ 0.76' % m.group(1))
    elif 'TIERS_DIALOG' in src and re.search(r"'\.'\s*:\s*0\.7[0-6]", src):
        add('dialog_cap', 'PASS', 'TIERS_DIALOG 条间值 ≤ 0.76')
    else:
        add('dialog_cap', 'WARN', '没找到对白条间上限常量，需人工确认')


# ------------------------------------------------------------ C 陈旧产物
def chk_stale_artifacts():
    """判据脚本改了、产物没重跑。今天两次：narr_check（01:50 产物 vs 03:03 判据）、
    dialog_gate（01:53 产物 vs 02:54 判据）。产物里没有版本戳 → 人眼看不出来。

    已被明确判定作废的历史产物，文件名里带 `OBSOLETE` 就跳过 —— 它们本来就该比脚本旧，
    留着是当证据，不是当结论。判断「作废」必须另有文档依据（DECISIONS / STATE 里写明）。
    """
    pairs = [
        ('narr_check.py', '_narr_check6/_narr_check.json'),
        ('narr_gate_phys.py', '_narr_phys.json'),
        ('dialog_gate.py', '_gate_dlg_v5.json'),
        ('mk_pause_plan.py', '_pause_plan.jsonl'),
    ]
    stale = []
    for script, prod in pairs:
        ts, tp = mtime(script), mtime(prod)
        if tp == 0:
            continue
        if tp < ts:
            stale.append('%s 比 %s 旧 %.1f 分钟' % (prod, script, (ts - tp) / 60))
    # 历史产物：只登记，不判失败（文件名必须带 OBSOLETE 字样）
    hist = []
    for f in ('_gate_dlg.json', '_gate_dlg_v2.json', '_gate_dlg_v3.json', '_narr_check3'):
        if 'OBSOLETE' in f:
            hist.append(f)
    if stale:
        add('stale_artifacts', 'FAIL', '产物早于判据脚本（结论可能基于旧判据）：' + '; '.join(stale))
    else:
        note = '产物均不早于对应脚本'
        if hist:
            note += '（%d 份作废历史产物已改名 OBSOLETE）' % len(hist)
        add('stale_artifacts', 'PASS', note)


# -------------------------------------------------- D 分类错但数值对
def chk_tier_literals():
    """档位数值不该以裸字面量出现在判据代码里 —— 那是第二份事实源。
    应统一读 pause_tiers.json / TIERS_DIALOG。"""
    src = read('check_pause_batch.py')
    if not src:
        add('tier_literals', 'SKIP', 'check_pause_batch.py 不存在')
        return
    # 允许 MARKS/BANDS 这类定义字典存在，但不允许散落在逻辑里
    body = src.split('def ', 1)[-1]        # 函数体部分
    hits = re.findall(r'(?<![\d.])(1\.16|1\.53|1\.35|1\.695|0\.43)(?![\d])', body)
    if hits:
        add('tier_literals', 'WARN',
            '函数体里出现档位字面量 %s，建议改为读 pause_tiers.json' % sorted(set(hits)))
    else:
        add('tier_literals', 'PASS', '判据逻辑无裸档位字面量')


def chk_expr_coverage():
    """EXPR 表必须与本书编号体系匹配。若 key 全是 Wonder 的 L/I 编号，
    而音频是 c1_xxxx，覆盖率 = 0 ⇒ 19f 的 weak/none 逻辑形同不存在。"""
    fp = os.path.join(SETUP, '_punct_expr.json')
    if not os.path.exists(fp):
        add('expr_coverage', 'FAIL', '_punct_expr.json 不存在')
        return
    d = json.load(open(fp, encoding='utf-8'))
    keys = list(d)
    n_castle = sum(1 for k in keys if k.startswith('c'))
    n_wonder = len(keys) - n_castle
    plan_ids = set()
    pfp = os.path.join(SETUP, '_castle_en_ch123_plan.jsonl')
    if os.path.exists(pfp):
        for ln in open(pfp, encoding='utf-8'):
            ln = ln.strip()
            if ln:
                plan_ids.add(json.loads(ln)['id'])
    cover = len(set(keys) & plan_ids) / max(1, len(plan_ids))
    if cover < 0.05:
        add('expr_coverage', 'FAIL',
            'EXPR 只覆盖本书 %.1f%%（%d 条 Wonder / %d 条 c*）⇒ 19f 等于没做'
            % (100 * cover, n_wonder, n_castle))
    elif cover < 0.95:
        add('expr_coverage', 'WARN', 'EXPR 覆盖 %.0f%%' % (100 * cover))
    else:
        add('expr_coverage', 'PASS', 'EXPR 覆盖 %.0f%%' % (100 * cover))


def chk_tiers_track():
    """标注产物必须声明轨道。旁白没有 drop/beat，对白没有 inner/bound。
    拿错轨道的档位名标注 = 形态 D（数值对、分类错）。"""
    narr_ok = {'inner', 'bound', 'clause'}
    dlg_ok = {'drop', 'tight', 'clause', 'beat'}
    bad = []
    import glob
    for fp in glob.glob(os.path.join(SETUP, '_pause_vote', 'p_lead_v2_*.jsonl')):
        names = set()
        for ln in open(fp, encoding='utf-8'):
            ln = ln.strip()
            if ln:
                names.add(json.loads(ln).get('mark'))
        names.discard(None)
        if not names <= narr_ok:
            bad.append('%s 用了非旁白档位 %s' % (os.path.basename(fp), sorted(names - narr_ok)))
    if bad:
        add('tiers_track', 'FAIL', '旁白标注混入对白档位：' + '; '.join(bad))
    else:
        add('tiers_track', 'PASS', '旁白标注只用 inner/bound/clause')


# ------------------------------------------------------ E 用噪声伪造信号
def chk_shape_jitter():
    """旁白标注的 dur 必须**精确等于档位 median**（inner .51 / bound 1.135 / clause 1.695）。

    为什么这不是「填死值」的错：skill §18.34 的三档定案回测过 ——
    直接用 median，MAE 0.292s / R² 0.480；再加 R3（句子进度）增益为零（r²=0.048），
    AUC(bound>inner)=0.840。**中位就是最优估计，抖动只会偏离。**

    需求 19-0 的「同一句里每个停顿不一样长」限定在**对白**（依据是夏尔这个角色的
    情绪与语言自然度）。旁白由句法层级决定，同层级同长才对。
    我此前给 bound 填 1.05/1.15/1.25 是拿对白要求套旁白，2026-11-11 已归位。
    """
    import glob
    MED = {'inner': 0.51, 'bound': 1.135, 'clause': 1.695}
    bad = []
    for fp in glob.glob(os.path.join(SETUP, '_pause_vote', 'p_lead_v2_*.jsonl')):
        for ln in open(fp, encoding='utf-8'):
            ln = ln.strip()
            if not ln:
                continue
            r = json.loads(ln)
            m = r.get('mark')
            if m in MED and abs(float(r.get('dur', 0)) - MED[m]) > 0.005:
                bad.append('%s %s=%s(%s 应 %.3f)'
                           % (os.path.basename(fp), r['bid'], r.get('dur'), m, MED[m]))
    if bad:
        add('narr_tier_median', 'FAIL',
            '旁白 dur 偏离档位 median：' + '; '.join(bad[:5])
            + (' …共 %d 处' % len(bad) if len(bad) > 5 else ''))
    else:
        add('narr_tier_median', 'PASS', '旁白 dur 全部等于档位 median')

    src = read('apply_pause_shape.py')
    if src and 'DEPRECATED' not in src[:400]:
        add('shape_script_deprecated', 'WARN',
            'apply_pause_shape.py 仍在（按 why 关键词整形 + ±0.04 找空位），'
            '旁白已归位到 median，此脚本对旁白应停用')


def chk_memory_budget():
    """记忆文件的**字符**预算 —— 超限会被静默截断，比不全更危险。

    这是「一压缩就全忘」的机制性原因之一（2026-11-11 实测）：
      用户级 MEMORY.md 5489 字符 / 上限 4000 → 137%，**早就在被截**
      项目级 MEMORY.md 3788 字符 / 上限 3000 → 126%
    被截断后，agent 看到的是半份规则，而且**不会报错**。
    """
    MEM_USER = r'C:/Users/86178/.workbuddy/MEMORY.md'
    MEM_PROJ = (r'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/'
                r'.workbuddy/memory/MEMORY.md')
    bad, warn = [], []
    for name, p, cap in (('用户 MEMORY', MEM_USER, 4000),
                         ('项目 MEMORY', MEM_PROJ, 3000)):
        if not os.path.exists(p):
            continue
        n = len(open(p, encoding='utf-8').read())
        pct = 100.0 * n / cap
        s = '%s %d/%d 字符 (%.0f%%)' % (name, n, cap, pct)
        if n > cap:
            bad.append(s + ' 已超限→会被截断')
        elif pct > 90:
            warn.append(s + ' 接近上限')
    # skill body 体量（社区建议 <500 行；超了关键定案会落在注意力中段）
    sk = r'C:/Users/86178/.workbuddy/skills/dots-tts-dubbing/SKILL.md'
    if os.path.exists(sk):
        lines = sum(1 for _ in open(sk, encoding='utf-8'))
        if lines > 800:
            # 有速查表就只提示不告警
            head = open(sk, encoding='utf-8').read(3000)
            if '结论速查' not in head:
                warn.append('dots-tts-dubbing %d 行且无开头速查表（关键定案会落在中段）'
                            % lines)
    if bad:
        add('memory_budget', 'FAIL', '；'.join(bad))
    elif warn:
        add('memory_budget', 'WARN', '；'.join(warn))
    else:
        add('memory_budget', 'PASS', '记忆文件均在预算内')


def chk_state_fresh():
    """STATE.md 必须比当日日志新 —— 否则压缩后接不上（干了活但没写状态）。

    这是「上下文一压缩就全忘」的第二半：机制有了（resume.py 开场注入），
    但如果 STATE 是旧的，注入的也是旧内容。
    """
    st = os.path.join(SETUP, 'STATE.md')
    logs = sorted(glob.glob(r'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/'
                            r'.workbuddy/memory/20*.md'))
    if not logs or not os.path.exists(st):
        add('state_fresh', 'SKIP', '缺 STATE.md 或日志')
        return
    newest = max(logs, key=os.path.getmtime)
    d = os.path.getmtime(newest) - os.path.getmtime(st)
    if d > 2 * 3600:
        add('state_fresh', 'WARN',
            '日志 %s 比 STATE.md 新 %.1f 小时（干了活没更新状态，压缩后会接不上）'
            % (os.path.basename(newest), d / 3600))
    else:
        add('state_fresh', 'PASS', 'STATE.md 不比日志旧')


def chk_limit_branches():
    """`--limit` 必须在**所有**建清单的分支里生效。

    2026-11-11 实测：`--limit` 只写在 `--dir` 分支，`--plan ... --limit 20` 实际跑了全量 239 条，
    还把那批结果覆盖进了快照文件。这类「参数只在一条路径生效」的坑，报错是没有的、结果看着正常。
    """
    src = read('dialog_gate.py')
    if not src:
        add('limit_branches', 'SKIP', 'dialog_gate.py 不存在')
        return
    n_items = src.count('items.append(') + src.count('items = [{')
    branches = sum(1 for kw in ('a.cues', 'a.wav', 'a.plan') if kw in src)
    if 'a.limit' not in src:
        add('limit_branches', 'FAIL', 'dialog_gate 无 --limit 处理')
        return
    # 至少要有一处「截断 items」发生在建清单之后，且不是只截 files
    after = src.split('items.append(')[-1]
    if 'items = items[:a.limit]' in src:
        add('limit_branches', 'PASS',
            '--limit 在 items 层统一截断（%d 个建清单分支都覆盖）' % branches)
    elif 'files = files[:a.limit]' in src:
        add('limit_branches', 'FAIL',
            '--limit 只截 --dir 的 files（%d 处 items.append 不受控）' % n_items)
    else:
        add('limit_branches', 'WARN', '--limit 位置不明，人工确认')


def chk_plan_voice():
    """对白 plan 必须带 voice 字段。

    `gate_emotion(ref_emo=...)` 要判断「这条生成时用的是哪个情绪档」。
    没给 voice 就会退回声纹 1-NN 的最近档（音色最近 ≠ 情绪档），
    实测误报 ref_fallback 95 条（c2_0320 标注激动反抗被 1-NN 判成 excited 等）。
    """
    import json as _json
    p = 'G:/_setup/_dlg_plan_v2.jsonl'
    if not os.path.exists(p):
        add('plan_voice', 'SKIP', '_dlg_plan_v2.jsonl 不存在')
        return
    n = nov = 0
    try:
        for line in open(p, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            d = _json.loads(line)
            n += 1
            if not d.get('voice'):
                nov += 1
    except Exception as e:
        add('plan_voice', 'ERROR', '读 plan 失败：%s' % e)
        return
    if nov:
        add('plan_voice', 'FAIL',
            '%d/%d 行缺 voice 字段 ⇒ ref_fallback 会退化成 1-NN 猜档' % (nov, n))
    else:
        add('plan_voice', 'PASS', '%d 行全部带 voice，ref_emo 取生成时的档' % n)


CHECKS = [
    ('span_physical', chk_span_physical),
    ('span_single_source', chk_span_single_source),
    ('dead_params', chk_dead_params),
    ('no_stretch_segments', chk_no_stretch_segments),
    ('peak_ceil', chk_peak_ceil),
    ('texts_hardcode', chk_texts_hardcode),
    ('wpm_scale', chk_wpm_scale),
    ('dialog_cap', chk_dialog_cap),
    ('stale_artifacts', chk_stale_artifacts),
    ('tier_literals', chk_tier_literals),
    ('expr_coverage', chk_expr_coverage),
    ('tiers_track', chk_tiers_track),
    ('narr_tier_median', chk_shape_jitter),
    ('memory_budget', chk_memory_budget),
    ('state_fresh', chk_state_fresh),
    ('limit_branches', chk_limit_branches),
    ('plan_voice', chk_plan_voice),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('--only', default='', help='逗号分隔的检查名')
    a = ap.parse_args()

    want = set(x.strip() for x in a.only.split(',') if x.strip())
    for name, fn in CHECKS:
        if want and name not in want:
            continue
        try:
            fn()
        except Exception as e:
            add(name, 'ERROR', '%s: %s' % (type(e).__name__, e))

    w = max(len(r[0]) for r in RESULTS) + 1
    icon = {'PASS': '✓', 'WARN': '!', 'FAIL': '✗', 'SKIP': '-', 'ERROR': 'E'}
    print('=' * 72)
    print('audit —— 失效模式静态检查 (%s)' % time.strftime('%Y-%m-%d %H:%M'))
    print('=' * 72)
    for name, status, detail in RESULTS:
        print('%s %-*s %s' % (icon.get(status, '?'), w, name, detail))

    nf = sum(1 for r in RESULTS if r[1] == 'FAIL')
    ne = sum(1 for r in RESULTS if r[1] == 'ERROR')
    nw = sum(1 for r in RESULTS if r[1] == 'WARN')
    print('-' * 72)
    print('PASS %d / WARN %d / FAIL %d / ERROR %d'
          % (sum(1 for r in RESULTS if r[1] == 'PASS'), nw, nf, ne))
    if nf or ne:
        print('⇒ FAIL 项必须修完再继续，否则后续结论可能建立在错的判据/数据上')
    return 1 if (nf or ne) else 0


if __name__ == '__main__':
    sys.exit(main())
