# -*- coding: utf-8 -*-
"""_reg_tier48.py —— 把 A/B 验证通过的 48k 参考追加进参考库（不覆盖、不改名旧文件）。

依据（_ab48_log.json，2026-11-13 20:22）：
  | 档 | 基线 cos_char / MOS | 采用参考 | 新 cos_char / MOS | 条数 |
  | Thomas_loud_1     | 0.652 / 2.23 | c285_p0 → Thomas_loud_5     | 0.774 / 2.60 | 62 |
  | Charles_neutral_1 | 0.379 / 2.54 | c181_p1 → Charles_neutral_4 | 0.643 / 2.57 | 12 |
  | Charles_excited_1 | 0.368 / 1.24 | c305_p0 → Charles_excited_4 | 0.546 / 1.95 |  6 |
  未通过（保持原样）：Charles_soft_1（换 48k 掉 MOS 0.79；换 wronged 掉 1.05）、Thomas_calm_1。

做法：**追加**新条目（编号续在后面），不改动原有参考 —— `plan.voice` 改成新名字即可，
旧参考与旧音频都留着，随时可回退。写文件前检查同名，冲突就加后缀（不吃上次的亏）。
"""
import json, os, shutil, sys

HERE = "G:/_setup"
LIB = os.path.join(HERE, "_emo_refs_all.json")
VOICE = os.path.join(HERE, "_cloud_backup/voice_lib")
CAND = os.path.join(HERE, "_refs_new/cand")
MEAS = os.path.join(HERE, "_refs_new/meas.json")

# (role, emo, cid, 说明)
ADD = [
    ("Thomas",  "loud",    "c285_p0", "Tu sais ce qui va arriver? Mon père va te mettre dehors."),
    ("Charles", "neutral", "c181_p1", "J'en ai pas besoin."),
    ("Charles", "excited", "c305_p0", "Eh bien, Thomas, vous oubliez nos accords?"),
]


def main():
    lib = json.load(open(LIB, encoding="utf-8"))
    meas = {r["cid"]: r for r in json.load(open(MEAS, encoding="utf-8"))}

    for role, emo, cid, text in ADD:
        src = os.path.join(CAND, cid + ".wav")
        if not os.path.exists(src):
            print("!! 缺候选 %s" % src); continue
        items = lib.setdefault(role, {}).setdefault(emo, [])
        n = len(items) + 1
        dst = os.path.join(VOICE, "%s_%s_%d.wav" % (role, emo, n))
        # 冲突检查（上次覆盖 Thomas_wary_1 的教训）
        while os.path.exists(dst) or any(
                (it.get("path") if isinstance(it, dict) else it) == dst for it in items):
            n += 1
            dst = os.path.join(VOICE, "%s_%s_%d.wav" % (role, emo, n))
        os.makedirs(VOICE, exist_ok=True)
        shutil.copy2(src, dst)
        items.append(dict(path=dst, text=text,
                          src="refs_new_48k(%s) AB-verified 2026-11-13" % cid,
                          mos=meas.get(cid, {}).get("mos")))
        print("+ %-9s %-9s %-3d  %s  ← %s (MOS %.2f)"
              % (role, emo, n, os.path.basename(dst), cid, meas.get(cid, {}).get("mos") or 0))

    json.dump(lib, open(LIB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写 %s" % LIB)


if __name__ == "__main__":
    main()
