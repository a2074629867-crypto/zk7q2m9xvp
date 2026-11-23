"""_nisqa_pref_eval.py —— NISQA（TTS 专用模型）在 56 条人工 A/B 偏好上的命中率。

与 audiobox / SQUIM 同条件对比。NISQA 有 mos / noi / col / dis / loud 五个输出，
其中 DIS（Discontinuity）测断流与硬切，COL（Coloration）测音色染色。

跑法：G:/Python310/python.exe _nisqa_pref_eval.py
"""
import json
import os
import shutil
import statistics

import torch

_orig_load = torch.load


def _patched(*a, **k):
    k.setdefault("weights_only", False)
    return _orig_load(*a, **k)


torch.load = _patched

ROOT = "G:/_setup"
SEEDS = ["42", "1234"]
LAB = os.path.join(ROOT, "_mt_labels_live.json")
STAGE = os.path.join(ROOT, "_nisqa_pref")
MODEL = "D:/eval_models/nisqa/nisqa_tts.tar"
DIMS = ["mos_pred", "noi_pred", "col_pred", "dis_pred", "loud_pred"]


def find_wav(uid, seed):
    for d in ("_mt_raw_s%s" % seed, "_mt_raw_%s" % seed):
        p = os.path.join(ROOT, d, uid + ".wav")
        if os.path.exists(p):
            return p
    return None


def main():
    lab = json.load(open(LAB, encoding="utf-8"))
    pairs = []
    for uid, v in lab.items():
        p = str(v.get("pick"))
        if p not in SEEDS:
            continue
        got = {s: find_wav(uid, s) for s in SEEDS}
        if all(got.values()):
            pairs.append(dict(uid=uid, pick=p, **got))
    print("可比单元 %d" % len(pairs))

    os.makedirs(STAGE, exist_ok=True)
    for f in os.listdir(STAGE):
        os.remove(os.path.join(STAGE, f))
    for p in pairs:
        for s in SEEDS:
            shutil.copy2(p[s], os.path.join(STAGE, "%s__s%s.wav" % (p["uid"], s)))
    print("staged %d files" % len(os.listdir(STAGE)))

    from nisqa.NISQA_model import nisqaModel
    args = {
        "mode": "predict_dir", "pretrained_model": MODEL, "data_dir": STAGE,
        "output_dir": os.path.join(ROOT, "_nisqa_pref_out"),
        "tr_bs_val": 8, "tr_num_workers": 0, "tr_parallel": False,
        "ms_channel": None, "dim": True, "tr_verbose": "noleave",
    }
    m = nisqaModel(args)
    df = m.predict()

    # 列名随模型而变：nisqa_tts.tar 只输出 mos_pred，四维模型才有 noi/col/dis/loud
    dims = [d for d in DIMS if d in df.columns]
    print("可用维度: %s" % dims)

    # 解析文件名 → (uid, seed)
    sc = {}
    for _, r in df.iterrows():
        base = os.path.splitext(os.path.basename(str(r["deg"])))[0]
        uid, _, seed = base.rpartition("__s")
        sc.setdefault(uid, {})[seed] = {d: float(r[d]) for d in dims}

    rows = [p for p in pairs if p["uid"] in sc and all(s in sc[p["uid"]] for s in SEEDS)]
    print("打分成功 %d 单元" % len(rows))

    print("\n=== NISQA 预测人工偏好（n=%d）===" % len(rows))
    print("%-12s %-8s %-8s %-8s" % ("dim", "higher", "lower", "best"))
    for d in dims:
        hi = sum(1 for p in rows
                 if sc[p["uid"]][p["pick"]][d] > sc[p["uid"]][[s for s in SEEDS if s != p["pick"]][0]][d])
        lo = len(rows) - hi
        print("%-12s %-8.3f %-8.3f %-8.3f" % (d, hi / len(rows), lo / len(rows), max(hi, lo) / len(rows)))

    print("\n=== 选中 vs 未选中 均值 ===")
    for d in dims:
        sel = [sc[p["uid"]][p["pick"]][d] for p in rows]
        oth = [sc[p["uid"]][[s for s in SEEDS if s != p["pick"]][0]][d] for p in rows]
        print("  %-10s 选中 %.4f  未选中 %.4f  差 %+.4f" % (d, statistics.mean(sel), statistics.mean(oth),
                                                          statistics.mean(sel) - statistics.mean(oth)))

    json.dump(dict(n=len(rows), scores=sc), open(os.path.join(ROOT, "_nisqa_pref.json"), "w",
                                                 encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写出 _nisqa_pref.json")


if __name__ == "__main__":
    main()
