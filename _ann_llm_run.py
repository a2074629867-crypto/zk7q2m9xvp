# -*- coding: utf-8 -*-
"""_ann_llm_run.py —— 直接调网关跑标注（不靠子 Agent，防「派不动」）

背景（2026-11-15 01:3x）：用户要求「HY4 + HY3 + DeepSeek 三路投票」。
用 Agent 工具指定 model="hy4" 直接起不来（models.json 里没有这两个 id，
子 Agent 秒杀）。真正的通道是本机网关：

    http://127.0.0.1:7863/v1/chat/completions

   lane   → model id
   hy4    → global:hy4free          (0 credit)
   hy3    → global:hy3              (0 credit)  ← 2026-11-15 12:1x 起替代 glm 作第三路
   ds     → global:deepseek-v4.1-flash-sg (0.11 credit/1k? 实测按次几十 token)

★ 三路固定为 hy4 + hy3 + ds。`glm`（global:glm-5.3-flash）本轮弃用：
  实测 0 产物，且用户明确要换 Hy3。历史 `_ann/**/glm/` 目录保留不动，只不再新跑。

本脚本自己发请求、自己校验（复用 `_ann_check_one.check_one`）、失败带错误回炉重标，
所以「三路互不可见」和「每批必须过自查」都是脚本保证的，不依赖执行体自觉。

用法：
  # 单路跑全部 20 包
  python _ann_llm_run.py --tasks _ann/tasks_narr_ctx --out _ann/out_narr/hy4 --lane hy4 -j 4
  # 三路一起（顺序跑，避免网关并发打爆）
  python _ann_llm_run.py --tasks _ann/tasks_narr_ctx --out-root _ann/out_narr --lanes hy4 hy3 ds -j 4
"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, "G:/_setup")
from _ann_check_one import check_one          # 唯一自检实现，不许重写

# ★ 2026-11-15 01:5x：7863（账号聚合网关）在 15 并发下全线 503（连 /models 都 200，
#   只有 completions 503），换到 7864（本机会话同款代理）三个 model id 全部可用。
GW = "http://127.0.0.1:7864/v1/chat/completions"
GW_ALT = "http://127.0.0.1:7863/v1/chat/completions"
from _llm_key import get_key
KEY = get_key()
LANE = {
    "hy4": "global:hy4free",
    "hy3": "global:hy3",
    "ds": "global:deepseek-v4.1-flash-sg",
    "ds2": "deepseek-v4.1-flash",       # 本机 7864（会话同款）
    # "glm": "global:glm-5.3-flash",    # 2026-11-15 12:1x 弃用，第三路改 hy3（见文件头）
    "mm": "global:minimax-m3.1-flash",     # HY4 通道单批 4 分钟（63 批约 4 小时），夜间换它做第三路
}

SYS = ("你是严格的韵律标注器。只输出一个 JSON 对象，不要任何解释、不要 markdown 代码块。"
       "严格遵守任务包 prompt 里的档位词表与输出格式。")


def post(model, messages, maxtok=16000, timeout=900, temp=0.7, url=None):
    body = json.dumps(dict(model=model, messages=messages, max_tokens=maxtok,
                           temperature=temp, stream=False)).encode()
    req = urllib.request.Request(url or GW, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    m = d["choices"][0]["message"]
    return (m.get("content") or ""), d.get("usage") or {}


def grab_json(s):
    s = (s or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("没有 JSON 对象")
    return json.loads(s[i:j + 1])


def run_batch(tasks, out, bname, lane, tries=6, maxtok=16000):
    try:
        src = json.load(open(os.path.join(tasks, bname), encoding="utf-8"))
        prompt = src["prompt"]
        payload = json.dumps({"items": src["items"]}, ensure_ascii=False)
    except Exception as e:
        # 非批文件 / 坏文件：只算这一批失败，绝不让异常冒到主线程
        print("  [%s %s] 不是合法批次，跳过: %s: %s" % (lane, bname, type(e).__name__, str(e)[:90]))
        return bname, False, 0, {}
    msgs = [{"role": "system", "content": SYS},
            {"role": "user", "content": prompt + "\n" + payload}]
    errs, nslot, last_raw = ["未开始"], 0, ""
    for k in range(tries):
        t0 = time.time()
        url = GW if k < 3 else GW_ALT            # 前 3 次主网关，之后全换备用网关
        try:
            raw, usage = post(LANE[lane], msgs, maxtok=maxtok, url=url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            msg = str(e)[:90]
            print("  [%s %s] 网络失败 %d/%d @%s: %s" %
                  (lane, bname, k + 1, tries, url.rsplit(":", 1)[-1], msg))
            if "503" in msg:
                # 503 no_healthy_account = 账号池冷却。8s 起步没用，必须长睡。
                time.sleep(min(90, 20 + 15 * k) + random.random() * 6)
            else:
                time.sleep(min(45, 6 * (k + 1)) + random.random() * 4)
            continue
        last_raw = raw
        try:
            obj = grab_json(raw)
            # 统一成 {"items":[...]}
            if isinstance(obj, list):
                obj = {"items": obj}
        except Exception as e:
            errs = ["JSON 解析失败: %s" % str(e)[:120]]
            print("  [%s %s] %s（%ds）" % (lane, bname, errs[0], time.time() - t0))
            msgs = msgs[:2] + [{"role": "user", "content":
                                "你上一次的输出不是合法 JSON（%s）。请只输出 JSON 对象，重来一次。"
                                % str(e)[:80]}]
            continue
        tmp = os.path.join(out, bname)
        json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        errs, nslot = check_one(out, bname, tasks)
        dt = time.time() - t0
        if not errs:
            print("  [%s %s] OK %d 槽位 %.0fs tok=%s/%s" %
                  (lane, bname, nslot, dt, usage.get("prompt_tokens"), usage.get("completion_tokens")))
            return bname, True, nslot, usage
        print("  [%s %s] 自查 %d 问题（%ds）: %s" % (lane, bname, len(errs), dt, errs[:3]))
        msgs = [{"role": "system", "content": SYS},
                {"role": "user", "content": prompt + "\n" + payload +
                 "\n\n# 你上一次的输出有 %d 个格式问题，必须全部修正后重发完整 JSON：\n%s"
                 % (len(errs), "\n".join(errs[:15]))}]
    # 全失败：留证，删掉坏文件（避免下游误用）
    bad = os.path.join(out, "_bad_%s.txt" % bname.replace(".json", ""))
    open(bad, "w", encoding="utf-8").write(last_raw or "")
    p = os.path.join(out, bname)
    if os.path.exists(p):
        os.remove(p)
    return bname, False, 0, {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--out", default=None, help="单路输出目录")
    ap.add_argument("--out-root", default=None, help="多路时用：<root>/<lane>")
    ap.add_argument("--lane", default=None)
    ap.add_argument("--lanes", nargs="+", default=None)
    ap.add_argument("--batches", nargs="+", default=None)
    ap.add_argument("-j", "--jobs", type=int, default=4)
    ap.add_argument("--tries", type=int, default=6, help="单批最大尝试次数（含换备用网关）")
    ap.add_argument("--redo", action="store_true", help="已有且合法的也重跑")
    ap.add_argument("--gw", default="", help="覆盖主网关（7864 忙时换 7863）")
    ap.add_argument("--maxtok", type=int, default=16000,
                    help="单次最大输出 token。hy4 思考极长，实测 8 条要 6万+，必须放大")
    a = ap.parse_args()
    global GW
    if a.gw:
        GW = a.gw

    lanes = a.lanes or ([a.lane] if a.lane else ["ds"])
    if a.out_root:
        pairs = [(l, os.path.join(a.out_root, l)) for l in lanes]
    else:
        assert a.out and len(lanes) == 1
        pairs = [(lanes[0], a.out)]

    allb = a.batches or sorted(x for x in os.listdir(a.tasks)
                               if x.endswith(".json") and x.startswith("batch_"))
    # ★ 2026-11-15 17:3x：tasks 目录里有 INDEX.json（顶层 list），旧 glob 会把它当批次，
    #   run_batch 里 src["prompt"] 抛 TypeError → 主线程 f.result() 重抛 → 整个池当场崩。
    #   这就是「每次只跑出个位数批次就断」的真因（不是 502，503 只是陪跑）。只吃 batch_*.json。
    t_start = time.time()
    for lane, out in pairs:
        os.makedirs(out, exist_ok=True)
        todo = []
        for b in allb:
            p = os.path.join(out, b)
            if os.path.exists(p) and not a.redo:
                errs, _ = check_one(out, b, a.tasks)
                if not errs:
                    continue
            todo.append(b)
        print("\n=== lane %s model=%s 待跑 %d/%d 批 → %s" %
              (lane, LANE[lane], len(todo), len(allb), out))
        ok = fail = 0
        with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(run_batch, a.tasks, out, b, lane, a.tries, a.maxtok): b for b in todo}
            for f in cf.as_completed(futs):
                try:
                    b, good, n, _u = f.result()
                except Exception as e:        # ★ 单批爆炸不许拖死全池
                    b = futs.get(f, "?")
                    print("  [%s %s] 批次异常，跳过继续: %s: %s"
                          % (lane, b, type(e).__name__, str(e)[:120]))
                    fail += 1
                    continue
                ok += good
                fail += (not good)
        print("=== lane %s 完成：OK %d / 失败 %d，用时 %.0fs" % (lane, ok, fail, time.time() - t_start))
        if fail:
            print("    ⚠ 有失败批次，重跑同一命令会自动只补失败的")


if __name__ == "__main__":
    main()
