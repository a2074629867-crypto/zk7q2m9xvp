# -*- coding: utf-8 -*-
"""把 ExpressiveSpeech 的 metadata 变成统一标签集。

标签来源（优先用路径里的原始 style，比二次标注更可信）：
  Expresso/splitted_conversation/<pair>/<style>/...  -> style
  IEMOCAP / NCSSD / M3ED / MultiDialog -> 取 conversations[].emotion

输出 jsonl: path, emotion(单标签字符串), speaker, dataset, src_style
"""
import json, os, re, argparse, collections

DS = "G:/_setup/datasets/ExpressiveSpeech"

# 原始 style -> 我们关心的情绪组（None = 不是情绪，排除）
STYLE_GROUP = {
    "angry": "激动反抗",
    "disgusted": "警惕",
    "fearful": "紧张",
    "sad-sympathetic": "委屈",
    "sympathetic-sad": "委屈",
    "happy": "兴奋",
    "laughing": "兴奋",
    "default": "平静",
    "calm": "平静",
    "awe": "惊讶",
    "confused": "困惑",
    "sleepy": "困倦",
    "desire": "渴望",
    "whisper": None,        # 发声方式
    "projected": None,      # 音量投射
    "enunciated": None,     # 咬字
    "fast": None,           # 语速
}

EMO_GROUP = {
    "angry": "激动反抗", "anger": "激动反抗", "frustration": "激动反抗",
    "disgusted": "警惕", "disgust": "警惕",
    "fear": "紧张", "fearful": "紧张", "anxious": "紧张",
    "sad": "委屈", "sadness": "委屈", "disappointed": "委屈",
    "happy": "兴奋",
    "surprised": "惊讶", "surprise": "惊讶",
    "neutral": "平静",
    "other": None, "unknown": None,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/labels_expspeech.jsonl")
    ap.add_argument("--only-expresso", action="store_true")
    ap.add_argument("--require-file", action="store_true", help="只保留磁盘上真实存在的")
    ap.add_argument("--max-per-style", type=int, default=0, help="每个 style 最多取多少条，0=不限")
    a = ap.parse_args()

    rows = []
    seen = collections.Counter()
    for line in open(os.path.join(DS, "metadata.jsonl"), encoding="utf-8"):
        for u in json.loads(line).get("conversations", []):
            rel = u.get("audio-path", "")
            if not rel:
                continue
            abs_p = os.path.join(DS, rel.replace("/", os.sep))
            emo_raw = str(u.get("emotion") or "")
            src = rel.split("/")[1] if "/" in rel else "?"
            if a.only_expresso and src != "Expresso":
                continue

            if src == "Expresso":
                m = re.search(r"splitted_conversation/([^/]+)/([^/]+)/", rel)
                if not m:
                    continue
                pair, style = m.group(1), m.group(2)
                grp = STYLE_GROUP.get(style)
                key_tag = style
                speaker = pair
            else:
                style = None
                # 多标签时取第一个能映射的
                grp = None
                for part in re.split(r"[,/]", emo_raw):
                    g = EMO_GROUP.get(part.strip().lower())
                    if g:
                        grp = g
                        break
                key_tag = emo_raw
                speaker = rel.split("/")[2] if rel.count("/") > 2 else "?"

            if not grp:
                continue
            if a.require_file and not os.path.exists(abs_p):
                continue
            if a.max_per_style and seen[key_tag] >= a.max_per_style:
                continue
            seen[key_tag] += 1
            rows.append({
                "path": abs_p,
                "emotion": grp,          # 统一到 7 组之一
                "speaker": speaker,
                "dataset": src,
                "src_style": key_tag,
                "dur": u.get("length"),
            })

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote %d -> %s" % (len(rows), a.out))
    c = collections.Counter(r["emotion"] for r in rows)
    print("情绪组:", dict(c))
    d = collections.Counter(r["dataset"] for r in rows)
    print("来源:", dict(d))


if __name__ == "__main__":
    main()
