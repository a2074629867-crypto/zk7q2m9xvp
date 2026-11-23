# -*- coding: utf-8 -*-
"""_ann_rate_groups.py —— 用网关模型给「一口气」句组做慢读标注（2026-11-20）。

用户口径（02:2x）：「用 Hy4 flash 来标注就行，一个模型即可。或者说用我们自己的模型，
也就是当前会话用的 DeepSeek V4.1 flash 和 Hy4 flash 来投票。两个模型够了。」

单位：`rate_llm_narr.json` 里的 618 个句组（≤5 词的碎句已并进下一句）。
输出：每批一个 json，最后 merge 成 gid -> slow(0/1) + why。
两个模型都判 1 才算慢（宁缺勿滥）；一票 1 一票 0 记 disputed，按不慢处理。

用法：
  python _ann_rate_groups.py --build
  python _ann_rate_groups.py --run --lanes hy4 ds --jobs 4
  python _ann_rate_groups.py --merge
"""
import argparse, concurrent.futures as cf, json, os, re, sys, time
import urllib.error, urllib.request

sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = r"G:/_setup"
TASKS = os.path.join(BASE, r"_ann/rate_groups/tasks")
OUT = os.path.join(BASE, r"_ann/rate_groups/out")
GW = "http://127.0.0.1:7864/v1/chat/completions"
from _llm_key import get_key
KEY = get_key()
LANE = {"hy4": "global:hy4free", "ds": "deepseek-v4.1-flash"}
BATCH = 15

SYS = ("你是严格的朗读韵律标注器。只输出一个 JSON 对象，不要解释、不要 markdown 代码块。")

PROMPT = """你在给英文小说 Susan Hill《I'm the King of the Castle》的**中文旁白朗读**做「放慢」标注。
主角是 11 岁的查尔斯·金斯豪（Charles Kingshaw），被父亲带到 Warings 宅子寄住，长期受 Edmund Hooper 欺凌。

下面给你若干个「一口气」单元（每个 1~4 句，是朗读时一口气读完的片段）。逐个判断：
**这一口气读出来，是否应该明显放慢。**

该慢（slow=1）：
- 悲伤 / 临终 / 死亡 / 屈辱 / 恐惧 / 孤独 / 诀别 / 回忆里最痛的一拍
- 重点看查尔斯的戏：他被羞辱、想母亲、夜里害怕、独自哭、被关起来、被逼到绝境

不该慢（slow=0）：
- 叙述推进、动作、事务（分家产、看房子、搬家）、景物铺陈、对白标签
- 只是「气氛阴沉」但事件还在往前走 —— 也不要慢

慢要少见：全书 618 口气里大约只有 12~18% 该慢，宁缺勿滥。
同一个情绪高点可以连着标两三个，但不要整段都标。

输出（只输出 JSON）：
{"items":[{"gid":"G001","slow":0,"why":"不超过12字"}]}
每个 gid 必须出现一次，顺序与输入一致；why 写清是哪一类情绪。
"""


def load_groups():
    d = json.load(open(os.path.join(BASE, "rate_llm_narr.json"), encoding="utf-8"))
    S = d["sentences"]
    txt = {r["id"]: r["text"] for r in
           (json.loads(l) for l in open(os.path.join(BASE, "_narr_plan_for_pause.jsonl"), encoding="utf-8") if l.strip())
           if r.get("speaker") == "narrator"}
    order = [i for b in json.load(open(os.path.join(BASE, "_narr_blocks.json"), encoding="utf-8")) for i in b["ids"]]
    groups = {}
    for i in order:
        g = S[i]["group"]
        groups.setdefault(g, []).append(i)
    out = []
    for g in sorted(groups):
        ids = groups[g]
        out.append({"gid": g, "text": " ".join(txt[i] for i in ids).strip()})
    return out


def build():
    os.makedirs(TASKS, exist_ok=True)
    gs = load_groups()
    n = 0
    for k in range(0, len(gs), BATCH):
        chunk = gs[k:k + BATCH]
        name = "batch_%02d.json" % (k // BATCH)
        json.dump({"prompt": PROMPT, "items": chunk}, open(os.path.join(TASKS, name), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        n += 1
    json.dump({"n_groups": len(gs), "n_batches": n, "batch": BATCH},
              open(os.path.join(TASKS, "INDEX.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("build: %d 组 → %d 批 → %s" % (len(gs), n, TASKS))


def post(model, messages, maxtok=8000, timeout=600):
    body = json.dumps(dict(model=model, messages=messages, max_tokens=maxtok,
                           temperature=0.3, stream=False)).encode()
    req = urllib.request.Request(GW, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["choices"][0]["message"].get("content") or ""


def grab(s):
    s = (s or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no json")
    return json.loads(s[i:j + 1])


def check(obj, items):
    want = [it["gid"] for it in items]
    if not isinstance(obj, dict):
        return ["顶层不是对象（拿到 %s）" % type(obj).__name__]
    got = obj.get("items") if isinstance(obj, dict) else None
    if not isinstance(got, list):
        return ["items 不是 list"]
    errs = []
    seen = [str(x.get("gid")) for x in got if isinstance(x, dict)]
    miss = [g for g in want if g not in seen]
    if miss:
        errs.append("缺 %d 个: %s" % (len(miss), miss[:5]))
    for x in got:
        if not isinstance(x, dict):
            errs.append("非对象项")
            continue
        if x.get("slow") not in (0, 1, "0", "1"):
            errs.append("%s slow 非法 %r" % (x.get("gid"), x.get("slow")))
    return errs


def run(lanes, jobs, tries=5, only=None):
    names = sorted(x for x in os.listdir(TASKS) if x.startswith("batch_"))
    if only:
        names = [n for n in names if n in only]
    for lane in lanes:
        out = os.path.join(OUT, lane)
        os.makedirs(out, exist_ok=True)
        todo = [n for n in names if not (os.path.exists(os.path.join(out, n)) and
                                         not check(json.load(open(os.path.join(out, n), encoding="utf-8")),
                                                   json.load(open(os.path.join(TASKS, n), encoding="utf-8"))["items"]))]
        print("=== lane %s (%s) 待跑 %d/%d" % (lane, LANE[lane], len(todo), len(names)))

        def one(bn):
            try:
                return _one(bn)
            except Exception as e:      # 单批爆炸不许拖死全池（11-15 的教训）
                print("  [%s %s] 批次异常跳过: %s: %s" % (lane, bn, type(e).__name__, str(e)[:100]))
                return bn, False

        def _one(bn):
            src = json.load(open(os.path.join(TASKS, bn), encoding="utf-8"))
            msgs = [{"role": "system", "content": SYS},
                    {"role": "user", "content": PROMPT + "\n" + json.dumps({"items": src["items"]}, ensure_ascii=False)}]
            for k in range(tries):
                t0 = time.time()
                try:
                    raw = post(LANE[lane], msgs)
                except (urllib.error.URLError, TimeoutError, OSError) as e:
                    print("  [%s %s] 网络 %d: %s" % (lane, bn, k + 1, str(e)[:70]))
                    time.sleep(10 + 10 * k)
                    continue
                try:
                    obj = grab(raw)
                except Exception as e:
                    print("  [%s %s] JSON 失败: %s" % (lane, bn, str(e)[:60]))
                    msgs = msgs[:2] + [{"role": "user", "content": "上次输出不是合法 JSON。只输出 JSON 对象。"}]
                    continue
                errs = check(obj, src["items"])
                if errs:
                    print("  [%s %s] 自查: %s" % (lane, bn, errs[:2]))
                    msgs = msgs[:2] + [{"role": "user", "content": PROMPT + "\n" +
                                        json.dumps({"items": src["items"]}, ensure_ascii=False) +
                                        "\n\n上次有这些问题，修正后重发完整 JSON：\n" + "\n".join(errs[:8])}]
                    continue
                json.dump(obj, open(os.path.join(out, bn), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print("  [%s %s] OK %d 项 %.0fs" % (lane, bn, len(obj["items"]), time.time() - t0))
                return bn, True
            print("  [%s %s] 放弃" % (lane, bn))
            return bn, False

        ok = 0
        with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
            for bn, good in ex.map(one, todo):
                ok += good
        print("=== lane %s 完成 %d/%d" % (lane, ok, len(todo)))


def merge():
    gs = load_groups()
    want = [g["gid"] for g in gs]
    votes = {}
    for lane in LANE:
        d = os.path.join(OUT, lane)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.startswith("batch_"):
                continue
            for it in json.load(open(os.path.join(d, fn), encoding="utf-8"))["items"]:
                gid = str(it.get("gid"))
                votes.setdefault(gid, {})[lane] = (int(it.get("slow")), (it.get("why") or "")[:40])
    rows = []
    for gid in want:
        v = votes.get(gid, {})
        s = [v[l][0] for l in v]
        slow = 1 if (len(s) >= 2 and all(x == 1 for x in s)) else 0
        disp = 1 if (len(s) >= 2 and len(set(s)) > 1) else 0
        why = next((v[l][1] for l in v if v[l][0] == 1), "")
        rows.append({"gid": gid, "slow": slow, "disputed": disp, "why": why, "votes": {l: v[l][0] for l in v}})
    json.dump({"_meta": {"n": len(rows), "n_slow": sum(r["slow"] for r in rows),
                         "n_disputed": sum(r["disputed"] for r in rows),
                         "lanes": sorted({l for r in rows for l in r["votes"]})},
               "items": rows},
              open(os.path.join(BASE, "rate_groups_vote.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("merge: %d 组，慢 %d（%.1f%%），分歧 %d" %
          (len(rows), sum(r["slow"] for r in rows), 100.0 * sum(r["slow"] for r in rows) / len(rows),
           sum(r["disputed"] for r in rows)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--lanes", nargs="+", default=["hy4"])
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", nargs="+", default=None)
    a = ap.parse_args()
    if a.build:
        build()
    if a.run:
        run(a.lanes, a.jobs, only=a.only)
    if a.merge:
        merge()
