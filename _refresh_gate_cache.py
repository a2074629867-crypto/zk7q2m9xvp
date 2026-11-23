# -*- coding: utf-8 -*-
"""_refresh_gate_cache.py —— 让闸门的两层特征缓存跟上被回填过的音频。

背景（2026-11-13 16:40 首次，之后又踩三次）：
  `_utt_emb/r34.npz` 与 `_mutcache_real/*.npz` 都按**文件名**命中，不校验音频是否变过。
  只要回填 / 改电平之后没刷缓存，G 类（intra 句内突变 + scs 档内离群）与声纹归属
  判的就是旧音频的向量 —— 会凭空造出「假信号」，让人去重做本来没问题的句子。

★ 2026-11-13 19:45 改法（第四例之后）：
  旧版靠读 `_backfill_r5/r6/nudge` 台账取 id，于是 r7~r10 的回填它完全看不到。
  **台账是会漏的第二手信息，音频 mtime 才是第一手事实。**
  现在改成：扫交付目录全部音频，逐个比 `音频 mtime > 缓存 mtime`，谁晚谁失效。
  台账只用来打印「本批有哪几轮回填」，不参与判定。

顺带：r34.npz 每次都整份删除重算（239 条约 46s），避免新旧混批。
"""
import glob, json, os

HERE = "G:/_setup"
AUD = os.path.join(HERE, "_audio_ch123/out")
MUT = os.path.join(HERE, "_mutcache_real")
EMB = os.path.join(HERE, "_utt_emb")


def main():
    wavs = sorted(glob.glob(os.path.join(AUD, "*.wav")))
    print("交付音频 %d 条" % len(wavs))

    # 只为汇报：这几轮各回填了多少条（不参与判定）
    for p in sorted(glob.glob(os.path.join(HERE, "_backfill_r*_log.json"))):
        try:
            n = len(json.load(open(p, encoding="utf-8")))
        except Exception:
            n = -1
        print("  (参考) %-28s %3d 条" % (os.path.basename(p), n))

    # 判定：音频比 intra 缓存新 ⇒ 缓存失效
    stale, no_cache = [], []
    for w in wavs:
        i = os.path.basename(w)[:-4]
        c = os.path.join(MUT, i + ".npz")
        if not os.path.exists(c):
            no_cache.append(i)
            continue
        if os.path.getmtime(w) > os.path.getmtime(c):
            os.remove(c)
            stale.append(i)

    print("intra 缓存失效并已删 %d 条：%s" % (len(stale), stale[:12] or "无"))
    print("本就无 intra 缓存 %d 条 %s" % (len(no_cache), no_cache[:5] or ""))

    z = os.path.join(EMB, "r34.npz")
    if os.path.exists(z):
        os.remove(z)
        print("已删 _utt_emb/r34.npz（由 _utt_verify.py r34 全量重算）")


if __name__ == "__main__":
    main()
