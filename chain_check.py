"""音色检测一条龙：角色归属 + 情绪音色档 + 置信度。

模板库 = G:/_setup/_emo_refs.json（从电影里重建的 8 档 25 条干净 ref）
方法   = 1-NN（每条 ref 单独当模板）+ Z-norm（用电影对白做背景分布）

用法：
  python chain_check.py --wav x.wav
  python chain_check.py --list out/final_labels.jsonl --out out/emo_znorm.json
"""
import os, sys, json, argparse, collections
import numpy as np

sys.path.insert(0, "G:/_setup")
from sv_onnx import SV

LIB = "G:/_setup/_emo_refs.json"
BG = "G:/_setup/out_sv/cues_znorm2.json"


def _zdict(keys, z):
    """(role, emo, ref) × z → 唯一 key 的 dict。

    同一「角色/情绪」下有多条模板，用 "Role/emo" 当 key 会被后者覆盖前者，
    下游算 max 时就少看了几条模板。这里做同名计数，重复的加 #2 #3。
    """
    out, seen = {}, {}
    for (role, emo, _name), v in zip(keys, z):
        base = "%s/%s" % (role, emo)
        seen[base] = seen.get(base, 0) + 1
        k = base if seen[base] == 1 else "%s#%d" % (base, seen[base])
        out[k] = round(float(v), 2)
    return out


class EmoVoice:
    def __init__(self, model="r34", lib=LIB, bg=BG, exclude_emo=None, bg_map=None):
        # lib/bg 必须可换：换一部片子时角色、背景分布全变了，硬编码只能跑这一片。
        # exclude_emo：角色判定时排除某些情绪档。Charles/soft 只有 3 条 1.5-1.9s 的
        # 低声素材，会把 Thomas 吸过去；但删掉它又会让 Charles 少 3 个模板。
        # 做成开关而不是直接删，是为了让「保纯度」和「多放行」能分开选。
        # bg_map：{角色: 背景集 json}，按角色分域做 Z-norm。多片合库时必须给 —— 见
        # _znorm_bg_map 的说明。
        self.lib_path, self.bg_path = lib, bg
        self.excluded = set(exclude_emo or ())
        self.bg_map = dict(bg_map) if bg_map else None
        self.m = SV(model)
        libd = json.load(open(lib, encoding="utf-8"))
        self.keys, self.mats = [], []
        for role, emos in libd.items():
            for emo, items in emos.items():
                if emo in self.excluded:
                    continue
                for it in items:
                    p = it["path"] if isinstance(it, dict) else it
                    if os.path.exists(p):
                        self.keys.append((role, emo, os.path.basename(p)))
                        self.mats.append(self.m.embed(p))
        self.mats = np.array(self.mats)
        self._znorm_bg()

    def _znorm_bg(self):
        if self.bg_map:
            return self._znorm_bg_map()
        bg = json.load(open(self.bg_path, encoding="utf-8"))
        paths = [r["path"] for r in bg]
        # 缓存：393 条背景 embedding 要 35–40s，日常当闸门用太慢。
        # 指纹 = 模板条数 + 背景条数 + 背景首末路径 + 两个库的路径，
        # 换片（lib/bg 变了）必须重算，否则会拿上一片的 μ/σ 去归一化这一片。
        cache = "G:/_setup/out_sv/znorm_cache.json"
        key = "%d|%d|%s|%s|%s|%s" % (len(self.keys), len(paths),
                                     paths[0] if paths else "", paths[-1] if paths else "",
                                     os.path.basename(self.lib_path),
                                     os.path.basename(self.bg_path))
        # 不同片各存一份缓存，否则换片会覆盖上一片的 μ/σ（下次换回来又要重算 40s）
        import hashlib
        cache = "G:/_setup/out_sv/znorm_cache_%s.json" % hashlib.md5(key.encode()).hexdigest()[:10]
        if os.path.exists(cache):
            try:
                d = json.load(open(cache, encoding="utf-8"))
                if d.get("key") == key and len(d.get("mu", [])) == len(self.mats):
                    self.mu = np.array(d["mu"], dtype=np.float32)
                    self.sd = np.array(d["sd"], dtype=np.float32)
                    return
            except Exception:
                pass
        M = np.full((len(paths), len(self.mats)), np.nan, dtype=np.float32)
        for i, p in enumerate(paths):
            try:
                M[i] = self.mats @ self.m.embed(p)
            except Exception:
                pass
        self.mu = np.nanmean(M, 0)
        self.sd = np.nanstd(M, 0) + 1e-9
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            json.dump({"key": key, "mu": self.mu.tolist(), "sd": self.sd.tolist()},
                      open(cache, "w", encoding="utf-8"))
        except Exception:
            pass

    def _znorm_bg_map(self):
        """按角色分域做 Z-norm：每个模板只用**自己那部片**的背景句归一化。

        为什么必须分域（2026-11-09 实测）
        --------------------------------
        多片合库后拿单一背景集（城堡片 393 条儿童对白）去归一化所有模板：
          Charles   μ 0.13–0.25  σ 0.13–0.18
          Joseph    μ 0.01–0.10  σ 0.06–0.11
        Joseph 模板跟法语片台词本来就远，μ 低、σ 更小 ⇒ 一点点相似度就放大成
        z=+2 以上，三个新角色把法语片台词全吸走：PASS 38→17、准确率 86.4%→47.5%。
        而原始余弦的 1-NN 准确率两版都是 96.6% —— 说明坏的是归一化，不是库。

        分域后每个模板的 z 都是相对「自己那部片的普通句子」而言，才可比。
        """
        import hashlib
        mu = np.zeros(len(self.mats), dtype=np.float32)
        sd = np.ones(len(self.mats), dtype=np.float32)
        sig = []
        for role, p in sorted(self.bg_map.items()):
            idx = [i for i, k in enumerate(self.keys) if k[0] == role]
            if not idx or not os.path.exists(p):
                continue
            bg = json.load(open(p, encoding="utf-8"))
            paths = [r["path"] for r in bg if os.path.exists(r["path"])]
            sig.append("%s:%s:%d" % (role, os.path.basename(p), len(paths)))
            cache = "G:/_setup/out_sv/znorm_map_%s.json" % hashlib.md5(
                ("|".join(sig) + "|" + self.lib_path).encode()).hexdigest()[:10]
            if os.path.exists(cache):
                try:
                    d = json.load(open(cache, encoding="utf-8"))
                    if len(d.get("mu", [])) == len(idx):
                        mu[idx] = d["mu"]
                        sd[idx] = d["sd"]
                        continue
                except Exception:
                    pass
            M = np.full((len(paths), len(idx)), np.nan, dtype=np.float32)
            for j, q in enumerate(paths):
                try:
                    M[j] = self.mats[idx] @ self.m.embed(q)
                except Exception:
                    pass
            mu[idx] = np.nanmean(M, 0)
            sd[idx] = np.nanstd(M, 0) + 1e-9
            try:
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                json.dump({"mu": mu[idx].tolist(), "sd": sd[idx].tolist()},
                          open(cache, "w", encoding="utf-8"))
            except Exception:
                pass
            print("  Z-norm[%s] %d 条背景 → %d 个模板  μ %.2f–%.2f"
                  % (role, len(paths), len(idx), mu[idx].min(), mu[idx].max()), flush=True)
        self.mu, self.sd = mu, sd

    def check(self, wav, role_blind=()):
        """role_blind：这些情绪档只当「情绪参考」，不参与角色归属。

        为什么要分开：Charles/soft 只有 3 条 1.5–1.9s 的低声素材，1-NN 会把 Thomas
        的低声句全吸过去。但 soft 作为**情绪**模板是有效的（委屈就是低声）。
        删掉整档 = 连情绪参考也丢了；不删 = 判角色时被吸走。
        所以按用途拆：情绪档用全库 top1，角色归属用剔掉 role_blind 的 top1。
        """
        e = self.m.embed(wav)
        cos = self.mats @ e
        z = (cos - self.mu) / self.sd

        # ① 全库 top1 —— 情绪档 / 展示用
        order_all = np.argsort(-z)
        ka1 = self.keys[order_all[0]]

        # ② 角色归属用的 top1 —— 剔掉 role_blind 档
        blind = set(role_blind or ())
        mask = np.array([k[1] not in blind for k in self.keys], dtype=bool)
        if blind and mask.any() and not mask.all():
            zr = np.where(mask, z, -1e9)
        else:
            zr = z
        order = np.argsort(-zr)
        k1, k2 = self.keys[order[0]], self.keys[order[1]]

        # 角色必须从模板库动态取 —— 原版写死 Charles/Thomas，换一部片直接
        # ValueError: max() arg is an empty sequence。
        roles = list(dict.fromkeys(k[0] for k in self.keys))
        role_max = {r: float(max(zr[j] for j, k in enumerate(self.keys) if k[0] == r))
                    for r in roles}
        top_role = k1[0]
        others = [v for r, v in role_max.items() if r != top_role]
        # role_z = top1 角色领先第二角色多少（两角色时等价于 zc−zt 的绝对值）
        role_z = role_max[top_role] - (max(others) if others else 0.0)
        return {
            "role": k1[0], "emo": k1[1], "ref": k1[2],
            "z1": round(float(zr[order[0]]), 3), "z2": round(float(zr[order[1]]), 3),
            "top2": "%s/%s" % (k2[0], k2[1]),
            "margin": round(float(zr[order[0]] - zr[order[1]]), 3),
            "role_z": round(float(role_z), 3),
            "role_max": {k: round(v, 3) for k, v in role_max.items()},
            "confident": bool(zr[order[0]] >= 0.7 and (zr[order[0]] - zr[order[1]]) >= 0.2),
            # 情绪视角（含 role_blind 档）：判角色时被排除的档，作为情绪参考仍然有效。
            # key 必须唯一 —— 同一「角色/情绪」下有多条模板，用 "Role/emo" 当 key
            # 会互相覆盖只留最后一条。踩过：z_target 本该 1.43，被覆盖成 0.92，
            # gap 从 +0.49 变 −0.02，判定整个反过来。
            "role_top": ka1[0],
            "emo_top": ka1[1], "ref_emo": ka1[2], "z_emo": round(float(z[order_all[0]]), 3),
            "z_all": _zdict(self.keys, z),
            # 角色视角（已剔除 role_blind）—— 下游算 z_target/z_other 必须用这一份，
            # 否则会出现「role 判成 Thomas、但 z_target(Charles) 高过 z_other」的自相矛盾。
            "z_role": _zdict([k for k, m in zip(self.keys, mask) if m],
                             [v for v, m in zip(z, mask) if m]),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--list")
    ap.add_argument("--out")
    a = ap.parse_args()
    ev = EmoVoice()
    print("模板 %d 条" % len(ev.keys), flush=True)

    if a.wav:
        print(json.dumps(ev.check(a.wav), ensure_ascii=False, indent=1))
        return

    items = [json.loads(l) for l in open(a.list, encoding="utf-8")]
    out = []
    for i, d in enumerate(items):
        r = ev.check(d["path"])
        r["name"] = os.path.basename(d["path"])
        r["target_emo"] = d.get("emotion")
        r["who"] = d.get("who")
        out.append(r)
        if (i + 1) % 20 == 0:
            print("  %d/%d" % (i + 1, len(items)), flush=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写 ->", a.out)
    print("角色:", dict(collections.Counter(r["role"] for r in out)))
    print("置信: %d/%d" % (sum(1 for r in out if r["confident"]), len(out)))


if __name__ == "__main__":
    main()
