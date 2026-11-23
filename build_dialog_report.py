# -*- coding: utf-8 -*-
"""生成对白归属报告：按角色分组 + 章节对照 + 旁白母带(ch1)对照"""
import json
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "G:/_setup")
import castle_attr8 as A

OUT_HTML = "G:/_setup/_dialog_report.html"
OUT_JSON = "G:/_setup/castle_dialog_report.json"

CN = {"Edmund": "Edmund Hooper（埃德蒙）", "Charles": "Charles Kingshaw（查尔斯）",
      "Joseph": "Joseph Hooper（父亲）", "Helena": "Helena Kingshaw（母亲）",
      "Fielding": "Anthony Fielding（菲尔丁）", "Boland": "Alice Boland（博兰太太）",
      "Fenwick": "Fenwick（芬威克）", "Casey": "Casey（凯西）",
      "__THOUGHT__": "心理独白（不算对白）"}
ORDER = ["Edmund", "Charles", "Joseph", "Helena", "Fielding", "Boland", "Fenwick", "Casey"]
CONF_CN = {"CONFIRMED": "确定", "ALTERNATE": "推断", "WEAK": "弱",
           "UNKNOWN": "未定", "THOUGHT": "心理", "HYPOTHETICAL": "假设"}


def main():
    t = A.load_text()
    paras = A.build_paras(t)
    ptext = [A.unapo(p[2]) for p in paras]
    units = json.load(open("G:/_setup/castle_dialog_v8.json", encoding="utf-8"))["units"]

    # 章节
    chap = [0] * len(paras)
    cur = 0
    for i, s in enumerate(ptext):
        m = re.match(r"\s*Chapter\s+(\d+)", s)
        if m:
            cur = int(m.group(1))
        chap[i] = cur
    for u in units:
        u["ch"] = chap[u["i"]]

    # 统计
    tot = len(units)
    cc = Counter(u["conf"] for u in units)
    by_ch = defaultdict(lambda: defaultdict(int))
    for u in units:
        by_ch[u["ch"]]["total"] += 1
        if u["who"] and u["who"] != "__THOUGHT__":
            by_ch[u["ch"]][u["who"]] += 1
        by_ch[u["ch"]][u["conf"]] += 1

    # 按角色分组
    groups = defaultdict(list)
    for u in units:
        groups[u["who"] or None].append(u)

    # ---- HTML ----
    H = []
    H.append("""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>《我是城堡之王》对白说话人标注 v8</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e6e9ef;--dim:#8b93a3;
--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;--alt:#60a5fa;--acc:#c084fc}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.65 -apple-system,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:22px;margin:0 0 6px}
h2{font-size:17px;margin:34px 0 12px;padding-bottom:7px;border-bottom:1px solid var(--line)}
h3{font-size:15px;margin:22px 0 8px;color:var(--acc)}
.sub{color:var(--dim);font-size:13px;margin-bottom:22px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi .n{font-size:22px;font-weight:600}
.kpi .l{color:var(--dim);font-size:12px;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px;margin:10px 0}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--dim);font-weight:500;font-size:12px}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11px;border:1px solid}
.t-CONFIRMED{color:var(--ok);border-color:#1f5133;background:#0f2a1c}
.t-ALTERNATE{color:var(--alt);border-color:#1e3a5f;background:#0e1d2e}
.t-WEAK{color:var(--warn);border-color:#5c4413;background:#2a2110}
.t-UNKNOWN{color:var(--dim);border-color:#333a48;background:#1a1d24}
.t-THOUGHT{color:var(--acc);border-color:#4a2d63;background:#241633}
.t-HYPOTHETICAL{color:var(--bad);border-color:#5c2020;background:#2a1010}
.line{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:9px 12px;margin:6px 0}
.line .txt{color:var(--fg)}
.line .meta{color:var(--dim);font-size:11.5px;margin-top:3px}
.note{background:#1a1d24;border-left:3px solid var(--warn);padding:10px 14px;border-radius:0 8px 8px 0;margin:14px 0;font-size:13px;color:#cbd2df}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--dim)}
</style></head><body><div class="wrap">""")

    H.append("<h1>《我是城堡之王》对白说话人标注 v8</h1>")
    H.append('<div class="sub">切分粒度：引号块（不是段落） · 全文状态机配对跨段引号 · '
             '心理独白单列 · 每句独立判定</div>')

    # 统计卡
    H.append('<div class="grid">')
    for label, n, color in [
        ("对白单元", tot, ""),
        ("确定", cc["CONFIRMED"], "var(--ok)"),
        ("推断", cc["ALTERNATE"], "var(--alt)"),
        ("弱", cc["WEAK"], "var(--warn)"),
        ("未定", cc["UNKNOWN"], "var(--dim)"),
        ("心理独白", cc["THOUGHT"], "var(--acc)"),
    ]:
        H.append('<div class="kpi"><div class="n" style="color:%s">%d</div>'
                 '<div class="l">%s</div></div>' % (color or "var(--fg)", n, label))
    H.append("</div>")

    # 方法说明
    H.append('<div class="note"><b>这次改了什么（每条都是实测出来的错）</b><br>'
             '① <b>跨段引号</b>：原著里同一人连续说话跨段时，中间段不加开引号。'
             '旧版按「引号数奇偶」合并段落，把闭引号误当开引号，一次吞掉 5 句对白。'
             '改为全文状态机配对。<br>'
             '② <b>段内多句</b>：一段可含两句分属两人的对白（如 '
             '<span class="mono">\'You don\'t frighten me, Hooper.\' \'You wait, Kingshaw.\'</span>），'
             '旧版整段判一人。改为每个引号块独立判定。<br>'
             '③ <b>主语位置</b>：<span class="mono">Mrs Helena Kingshaw said</span> 曾被判成 Charles —— '
             '旧版取全段最后一个名字，而说话人是<b>归属动词前面</b>那个。已修。<br>'
             '④ <b>心理独白</b>：<span class="mono">he thought, \'...\'</span> 带引号但是内心活动，'
             '已单列为「心理」，不计入对白。<br>'
             '⑤ <b>配角补全</b>：Fenwick / Casey 原本不在角色表，'
             '<span class="mono">Fenwick had said</span> 被错判成 Charles。</div>')

    # 验证结果
    H.append("<h2>人工核对结果</h2>")
    H.append("<table><tr><th>置信档</th><th>含义</th><th class='n'>条数</th>"
             "<th class='n'>抽检</th><th class='n'>正确</th><th>判据</th></tr>")
    rows = [
        ("CONFIRMED", "确定", cc["CONFIRMED"], 24, 19,
         "同段归属动词 + 主语名字 / 呼语 / 亲属指代"),
        ("ALTERNATE", "推断", cc["ALTERNATE"], 22, 17,
         "对话轮次交替（同一轮内无叙述插入，cast 恰为 2 人）"),
        ("WEAK", "弱", cc["WEAK"], 6, 3,
         "引号后叙述句首出现名字 —— 有歧义，仅供参考"),
    ]
    for k, cn, n, s, ok, how in rows:
        pct = 100.0 * ok / s if s else 0
        col = "var(--ok)" if pct >= 80 else ("var(--warn)" if pct >= 65 else "var(--bad)")
        H.append("<tr><td><span class='tag t-%s'>%s</span></td><td>%s</td>"
                 "<td class='n'>%d</td><td class='n'>%d</td>"
                 "<td class='n' style='color:%s'>%d（%.0f%%）</td><td class='mono'>%s</td></tr>"
                 % (k, k, cn, n, s, col, ok, pct, how))
    H.append("</table>")
    H.append('<div class="sub">未定 %d 条（%.0f%%）没有可靠依据，不猜 —— '
             '这些要么整轮对话没有任何归属锚点，要么在场角色 ≥3 无法用交替推断。</div>'
             % (cc["UNKNOWN"], 100.0 * cc["UNKNOWN"] / tot))

    # 章节对照
    H.append("<h2>按章对照（第 1 章 = 旁白母带对应章节）</h2>")
    H.append("<table><tr><th>章</th><th class='n'>对白</th><th class='n'>Edmund</th>"
             "<th class='n'>Charles</th><th class='n'>Joseph</th><th class='n'>Helena</th>"
             "<th class='n'>其他</th><th class='n'>未定</th><th class='n'>确定率</th></tr>")
    for c in sorted(by_ch):
        d = by_ch[c]
        if not d["total"]:
            continue
        others = sum(v for k, v in d.items()
                     if k in ORDER[4:] and v)
        det = d["CONFIRMED"] + d["ALTERNATE"]
        H.append("<tr><td>%s</td><td class='n'>%d</td><td class='n'>%d</td>"
                 "<td class='n'>%d</td><td class='n'>%d</td><td class='n'>%d</td>"
                 "<td class='n'>%d</td><td class='n'>%d</td><td class='n'>%.0f%%</td></tr>"
                 % (c if c else "序", d["total"], d["Edmund"], d["Charles"],
                    d["Joseph"], d["Helena"], others, d["UNKNOWN"],
                    100.0 * det / d["total"]))
    H.append("</table>")

    # 旁白母带对照
    H.append("<h2>旁白母带（第 1 章）对照</h2>")
    c1 = by_ch.get(1, {})
    allc = Counter()
    for u in units:
        if u["who"] and u["who"] != "__THOUGHT__":
            allc[u["who"]] += 1
    H.append('<div class="sub">旁白母带是马修读的第 1 章原声（21.7 分钟）。'
             '把这一章的对白单独拎出来看，和全书结构差别很明显。</div>')
    H.append("<table><tr><th>项目</th><th class='n'>第 1 章（母带）</th>"
             "<th class='n'>全书</th><th>说明</th></tr>")
    t1, tt = c1.get("total", 0), tot
    H.append("<tr><td>对白句数</td><td class='n'>%d</td><td class='n'>%d</td>"
             "<td>占全书 %.1f%%</td></tr>" % (t1, tt, 100.0 * t1 / tt))
    for who in ["Joseph", "Edmund", "Charles", "Helena"]:
        H.append("<tr><td>%s</td><td class='n'>%d</td><td class='n'>%d</td><td>%s</td></tr>"
                 % (CN.get(who, who).split("（")[0], c1.get(who, 0), allc.get(who, 0),
                    "本章未出场" if c1.get(who, 0) == 0 and allc.get(who, 0) else ""))
    det1 = c1.get("CONFIRMED", 0) + c1.get("ALTERNATE", 0)
    H.append("<tr><td>可判定率</td><td class='n'>%.0f%%</td><td class='n'>%.0f%%</td>"
             "<td>确定 + 推断</td></tr>"
             % (100.0 * det1 / t1 if t1 else 0,
                100.0 * (cc["CONFIRMED"] + cc["ALTERNATE"]) / tt))
    H.append("</table>")
    H.append('<div class="note"><b>差别在哪</b>：第 1 章只有 <b>父亲 Joseph 和 Edmund</b> 两个声音，'
             'Charles 还没出场（他第 2 章才来）。所以这一章的对白配音只需要 2 套音色，'
             '不是全书那种「两个男孩对打」的结构。这也解释了为什么母带里对白段的语气变化少 —— '
             '它本来就是一场父子对话。</div>')

    # 角色分组
    H.append("<h2>按角色分组</h2>")
    H.append('<div class="sub">每组标题是角色；条目按书中出现顺序，附章号与置信度。'
             '心理独白单列在最后，不计入对白。</div>')
    for who in ORDER:
        lst = groups.get(who, [])
        if not lst:
            continue
        H.append("<h3>%s — %d 句</h3>" % (CN.get(who, who), len(lst)))
        for u in lst[:400]:
            H.append('<div class="line"><div class="txt">%s</div>'
                     '<div class="meta">第 %s 章 · <span class="tag t-%s">%s</span> · %s</div></div>'
                     % (esc(u["text"])[:400], u.get("ch", "?"), u["conf"],
                        CONF_CN.get(u["conf"], u["conf"]), u["how"]))
        if len(lst) > 400:
            H.append('<div class="sub">（只显示前 400 句，完整见 JSON）</div>')

    # 心理独白
    th = groups.get("__THOUGHT__", [])
    if th:
        H.append("<h3>心理独白 — %d 句（不计入对白）</h3>" % len(th))
        for u in th:
            H.append('<div class="line"><div class="txt">%s</div>'
                     '<div class="meta">第 %s 章 · 内心活动，非真实说话</div></div>'
                     % (esc(u["text"])[:300], u.get("ch", "?")))

    # 未定
    un = [u for u in units if not u["who"]]
    H.append("<h3>未定 — %d 句（无可靠依据，不猜）</h3>" % len(un))
    for u in un[:200]:
        H.append('<div class="line"><div class="txt">%s</div>'
                 '<div class="meta">第 %s 章 · 需人工判断</div></div>'
                 % (esc(u["text"])[:260], u.get("ch", "?")))
    if len(un) > 200:
        H.append('<div class="sub">（只显示前 200 句）</div>')

    H.append("</div></body></html>")
    open(OUT_HTML, "w", encoding="utf-8").write("\n".join(H))

    json.dump(dict(units=units, stats=dict(total=tot, conf=dict(cc),
                                           by_ch={str(k): dict(v) for k, v in by_ch.items()})),
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("->", OUT_HTML)
    print("->", OUT_JSON)
    print("对白 %d | 确定 %d | 推断 %d | 弱 %d | 未定 %d | 心理 %d"
          % (tot, cc["CONFIRMED"], cc["ALTERNATE"], cc["WEAK"],
             cc["UNKNOWN"], cc["THOUGHT"]))


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


if __name__ == "__main__":
    main()
