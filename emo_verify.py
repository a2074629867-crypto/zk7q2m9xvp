"""情绪条件声纹检测器（emotion-conditioned speaker verification）。

思路（用户口径）：
  "说话人音色" = 是谁；"情绪音色" = 同一人在某情绪下的音色。
  所以判定时不该用"中性模板"去测情绪段，而应用**该角色该情绪的 ref** 当模板。

用法：
    from emo_verify import Vault
    v = Vault()                                  # 加载模板库
    r = v.verify("x.wav", role="Charles", emo="excited")
    print(r)   # {'sim': 0.72, 'best': '3_charles_excited', 'verdict': 'match'}

模板库文件：G:/_setup/_emo_refs.json
    {"Charles": {"neutral": [path...], "excited": [...], ...}, ...}
"""
import os, json
import numpy as np
import sys

sys.path.insert(0, "G:/_setup")
from sv_onnx import SV, load16, cos

REF_JSON = "G:/_setup/_emo_refs.json"


class Vault:
    def __init__(self, ref_json=REF_JSON, model="r293"):
        self.m = SV(model)
        self.refs = json.load(open(ref_json, encoding="utf-8"))
        self.T = {}          # (role, emo) -> list[(name, vec)]
        self._build()

    def _build(self):
        n = 0
        for role, emos in self.refs.items():
            for emo, items in emos.items():
                for it in items:
                    p = it["path"] if isinstance(it, dict) else it
                    name = it.get("name", os.path.basename(p)) if isinstance(it, dict) else os.path.basename(p)
                    if not os.path.exists(p):
                        print("MISS %s" % p)
                        continue
                    self.T.setdefault((role, emo), []).append((name, self.m.embed(p)))
                    n += 1
        print("vault: %d 档模板, %d 组 (role,emo)" % (n, len(self.T)))

    def _score(self, vec, role=None, emo=None):
        """返回 [(role, emo, name, cos)]，可按 role/emo 过滤"""
        out = []
        for (r, e), lst in self.T.items():
            if role and r != role:
                continue
            if emo and e != emo:
                continue
            for name, v in lst:
                out.append((r, e, name, cos(vec, v)))
        out.sort(key=lambda x: -x[3])
        return out

    def verify(self, wav, role="Charles", emo=None, thr=0.35):
        """判定 wav 是否属于 (role, emo)。

        对比三条线：
          same  —— 目标角色 + 目标情绪模板的最高相似度
          other_role —— 其他角色的最高相似度
          other_emo  —— 目标角色其他情绪的最高相似度
        """
        e = self.m.embed(wav)
        if emo:
            same = self._score(e, role=role, emo=emo)
            oth_r = self._score(e, role=None, emo=emo)
            oth_r = [x for x in oth_r if x[0] != role]
            oth_e = self._score(e, role=role)
            oth_e = [x for x in oth_e if x[1] != emo]
        else:
            same = self._score(e, role=role)
            oth_r = [x for x in self._score(e) if x[0] != role]
            oth_e = []
        s = same[0][3] if same else -1
        r = oth_r[0][3] if oth_r else -1
        q = oth_e[0][3] if oth_e else -1
        return {
            "role": role, "emo": emo,
            "sim": round(float(s), 4),
            "best": same[0][2] if same else None,
            "sim_other_role": round(float(r), 4),
            "sim_other_emo": round(float(q), 4),
            "margin_role": round(float(s - r), 4),
            "margin_emo": round(float(s - q), 4),
            "verdict": "match" if s >= thr and s > r else ("weak" if s >= thr * 0.7 else "miss"),
        }

    def profile(self, wav, topk=6):
        """不指定目标，输出这份音频最像谁、在什么情绪"""
        e = self.m.embed(wav)
        sc = self._score(e)
        return [{"role": r, "emo": m, "ref": n, "sim": round(float(v), 4)} for r, m, n, v in sc[:topk]]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--role", default="Charles")
    ap.add_argument("--emo", default=None)
    a = ap.parse_args()
    v = Vault()
    print(json.dumps(v.verify(a.wav, a.role, a.emo), ensure_ascii=False, indent=1))
    print("--- profile ---")
    for r in v.profile(a.wav):
        print("  %-8s %-9s %-26s %.4f" % (r["role"], r["emo"], r["ref"], r["sim"]))
