# -*- coding: utf-8 -*-
import json
import re

G = "G:/_setup/_accent_eval_set.json"
B = "G:/_setup/_blind"
MODELS = ["A", "B", "C", "step5", "hy4"]

g = json.load(open(G, encoding="utf-8"))
key = {v: k for k, v in json.load(open(f"{B}/key.json", encoding="utf-8")).items()}

rs = {}
for n in MODELS:
    t = open(f"{B}/out_{n}.json", encoding="utf-8").read()
    arr = json.loads(re.search(r"\[.*\]", t, re.S).group(0))
    rs[n] = {r["id"]: ("ART" if "ART" in r["label"].upper() else "val") for r in arr}


def show(it, x, tag):
    votes = {n: rs[n].get(x, "?") for n in MODELS}
    nart = sum(1 for v in votes.values() if v == "ART")
    print(f"\n[{x}] {tag}  top1=\"{it['top1']}\"  pos={it['pos']+1}/{it['n']}  gold={it['label']}")
    print(f"  {it['text']}")
    print(f"  votes: " + "  ".join(f"{n}={v}" for n, v in votes.items()) + f"   => {nart}/5 ARTIFACT")
    if it.get("dispute_why"):
        print(f"  my note: {it['dispute_why']}")


print("=" * 70)
print("A. ambiguous (gold counted as valid, but no firm answer)")
print("=" * 70)
for it in g["items"]:
    if it["label"] == "ambiguous":
        show(it, key[it["uid"]], "ambiguous")

print("\n" + "=" * 70)
print("B. disputed (my gold said valid, all LLMs say artifact)")
print("=" * 70)
for it in g["items"]:
    if it.get("disputed"):
        show(it, key[it["uid"]], "disputed")

print("\n" + "=" * 70)
print("C. clean-set disagreement (the only one)")
print("=" * 70)
for it in g["items"]:
    x = key[it["uid"]]
    if it["label"] == "valid_focus" and not it.get("disputed") and rs["hy4"].get(x) == "ART":
        show(it, x, "clean but hy4/step5 disagree")
