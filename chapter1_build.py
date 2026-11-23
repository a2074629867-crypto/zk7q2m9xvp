# -*- coding: utf-8 -*-
"""chapter1_build.py —— 从 v6 训练标签还原《Wonder》第一章文本，剔除人物对白，输出旁白文本。

对白识别：
  1) 归属动词硬规则（said / asked / replied / answered / continued / whispered ...）
  2) 归属句前后的「话本身」按显式区间扩展（SPEECH_SPANS，可编辑）
  3) 输出报告，逐条列出被剔除的句子，便于人工复核

用法：
  python chapter1_build.py --out-dir G:/_setup/chapter1
"""
import argparse
import json
import re
from pathlib import Path

LABELS = Path("G:/_setup/gsv5probe/logs/mcconaughey_v6/2-name2text.txt")

# 归属动词（句内出现即判为对白句）
ATTR_RE = re.compile(
    r"\b(said|asked|replied|answered|continued|shouted|yelled|muttered|responded)\b", re.I)

# 归属句之后仍然属于「话本身」的续句（显式区间，1-based 句号，闭区间）
# 依据：语义上仍是被引述的说话内容，没有叙事动作
SPEECH_SPANS = [
    (49, 49),   # "Well if it isn't my two favorite people," he said ...
    (52, 53),   # "What are we looking for?" Zoe asked.
    (54, 55),   # "Venus," Grandpa replied ... and a meteor shower is starting any minute.
    (59, 63),   # "My love," said Grandpa ... wonderful.
    (64, 65),   # "Like what?" Zoe asked.
    (66, 67),   # "Well, let me see." Grandpa said ...
    (79, 81),   # "In this moment," Grandpa continued ... in distant galaxies.
]


def load_sentences():
    rows = []
    for line in LABELS.read_text(encoding="utf-8").splitlines():
        q = line.split("\t")
        if len(q) < 4:
            continue
        m = re.search(r"_(\d+)_(\d+)\.wav$", q[0])
        if not m:
            continue
        rows.append((int(m.group(1)) / 32000, int(m.group(2)) / 32000, q[3].strip()))
    rows.sort()
    txt = re.sub(r"\s+", " ", " ".join(t for _, _, t in rows)).strip()
    return re.split(r"(?<=[.!?])\s+", txt)


def detect_dialogue(sents):
    idx = set()
    # 1) 归属动词
    attr_hits = []
    for i, s in enumerate(sents):
        if ATTR_RE.search(s):
            idx.add(i + 1)
            attr_hits.append(i + 1)
    # 2) 显式区间
    for a, b in SPEECH_SPANS:
        for k in range(a, b + 1):
            idx.add(k)
    return idx, attr_hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="G:/_setup/chapter1")
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    sents = load_sentences()
    cut, attr_hits = detect_dialogue(sents)

    kept, removed = [], []
    for i, s in enumerate(sents):
        n = i + 1
        (removed if n in cut else kept).append((n, s))

    narration = " ".join(s for _, s in kept)
    (out / "chapter1_narration.txt").write_text(narration, encoding="utf-8")
    (out / "chapter1_full.txt").write_text(" ".join(sents), encoding="utf-8")

    json.dump(dict(total_sentences=len(sents),
                   total_words=sum(len(s.split()) for s in sents),
                   kept_words=len(narration.split()),
                   removed_words=sum(len(s.split()) for _, s in removed),
                   attribution_hits=attr_hits,
                   removed=[dict(idx=n, text=s) for n, s in removed],
                   kept_idx=[n for n, _ in kept]),
              open(out / "chapter1_dialogue_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("句子 %d 句 / %d 词" % (len(sents), sum(len(s.split()) for s in sents)))
    print("剔除对白 %d 句 / %d 词（归属动词命中 %d 句）" % (
        len(removed), sum(len(s.split()) for _, s in removed), len(attr_hits)))
    print("保留旁白 %d 句 / %d 词" % (len(kept), len(narration.split())))
    print()
    print("=== 被剔除的句子 ===")
    for n, s in removed:
        print("  %3d| %s" % (n, s))
    print()
    print("→ %s" % (out / "chapter1_narration.txt"))


if __name__ == "__main__":
    main()
