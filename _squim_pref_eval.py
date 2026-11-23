"""_squim_pref_eval.py —— torchaudio SQUIM（无参考 MOS）在 56 条人工偏好上的命中率。

SQUIM_SUBJECTIVE：无参考，预测主观 MOS（P.835 风格）
SQUIM_OBJECTIVE：需要参考音频，输出 STOI / PESQ / SI-SDR（我们没有参考，跳过）

跑法：G:/Python310/python.exe _squim_pref_eval.py
"""
import json
import os
import statistics
import warnings

warnings.filterwarnings("ignore")

ROOT = "G:/_setup"
SEEDS = ["42", "1234"]
LAB = os.path.join(ROOT, "_mt_labels_live.json")


def find_wav(uid, seed):
    for d in ("_mt_raw_s%s" % seed, "_mt_raw_%s" % seed):
        p = os.path.join(ROOT, d, uid + ".wav")
        if os.path.exists(p):
            return p
    return None


def main():
    import torch
    import torchaudio
    from torchaudio.pipelines import SQUIM_SUBJECTIVE

    model = SQUIM_SUBJECTIVE.get_model()
    model.eval()

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

    def mos(path):
        wav, sr = torchaudio.load(path)
        if wav.shape[0] > 1:
            wav = wav.mean(0, keepdim=True)
        if sr != 16000:
            wav = torchaudio.functional.resample(wav, sr, 16000)
        with torch.no_grad():
            out = model(wav)
        return float(out.squeeze())

    rows = []
    for i, p in enumerate(pairs, 1):
        try:
            sc = {s: mos(p[s]) for s in SEEDS}
        except Exception as e:
            print("  !! %s %s" % (p["uid"], e))
            continue
        rows.append(dict(uid=p["uid"], pick=p["pick"], **sc))
        if i % 10 == 0:
            print("  %d/%d" % (i, len(pairs)))

    print("\n=== SQUIM MOS 预测人工偏好（n=%d）===" % len(rows))
    if not rows:
        return
    hi = sum(1 for r in rows if r[r["pick"]] > r[[s for s in SEEDS if s != r["pick"]][0]])
    acc = hi / len(rows)
    print("  acc(higher=选中) = %.3f   best = %.3f" % (acc, max(acc, 1 - acc)))

    sel = [r[r["pick"]] for r in rows]
    oth = [r[[s for s in SEEDS if s != r["pick"]][0]] for r in rows]
    print("  选中 MOS %.4f  未选中 %.4f  差 %+.4f"
          % (statistics.mean(sel), statistics.mean(oth), statistics.mean(sel) - statistics.mean(oth)))
    print("  MOS 范围 %.3f ~ %.3f，标准差 %.4f"
          % (min(sel + oth), max(sel + oth), statistics.pstdev(sel + oth)))

    json.dump(rows, open(os.path.join(ROOT, "_squim_pref.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("写出 _squim_pref.json")


if __name__ == "__main__":
    main()
