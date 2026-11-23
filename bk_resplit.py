# -*- coding: utf-8 -*-
"""拆句重生成：长块后段声码器崩坏 → 逐句生成再拼接。

    G:/Python310/python.exe bk_resplit.py [BK_4 BK_7 ...]

每条：同 ref / 同 reference_text / 同 seed 逐句生成 → 按标点插静音拼接。
"""
import os
import subprocess
import sys
import time
import wave

import numpy as np

ACPP_DIR = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/_setup/castle_fr_ref"
OUT = "G:/_setup/dots_edit2"
TMP = "G:/_setup/dots_edit2/_split"

REF_TEXT = {
    "1_charles_normal": "Je suis né comme ça aussi? Vous êtes M. Bréaud? Moi, je suis Charles Vernet. Non. Ça va mieux, maintenant. Non, monsieur. Et si elle, elle vous aime pas? Laisse. C'est moi qui t'invite. je suis encore très riche.",
    "2_charles_soft": "Mais il pouvait rien m'arriver. Maman, j'aurai plus jamais peur. Maman, je suis d'Artagnan. Non, maman. C'est le cadeau de Thomas. Tu peux plus rien me faire, maintenant.",
    "3_charles_excited": "Tu dis ça parce que t'as pas de mère! Menteur! Ton père n'est rien du tout! Il plaît pas à ma mère, elle le déteste! M. Bréaud est venu. Il t'aime.",
    "4_charles_angry": "Qui a jeté la pierre dans ma chambre? Qui a mis le corbeau dans mon lit? Je demande pardon à Charles pour tout ce que j'ai fait. Vas-y, répète!",
    "5_hooper_loud": "Il est riche et vous êtes pauvres. C'est pour ça que vous êtes venus, pour que ta mère puisse se marier avec mon père. Les femmes seules font ça. Il faut qu'on leur donne de l'argent, une maison, des robes...",
    "6_hooper_calm": "N'accablez point, madame, un prince malheureux. Il ne faut point ici nous attendrir tous deux. Un trouble assez cruel m'agite et me dévore sans que des pleurs si chers me déchirent encore. J'ai dit à papa que je voulais rester seul avec vous.",
    "6b_hooper_scold": "Espèce de sale voleur. Tu t'enfuies. Menteur! T'es un menteur et un voleur. Je vais aller réveiller mon père et je vais lui tout dire.",
    "7_hooper_begging": "Je peux pas, j'ai le vertige! C'est moi. C'est moi. Je demande pardon à Charles pour ce que j'ai fait.",
}

# tag -> (组, 完整原文, [(分句文本, 句末停顿秒)])
SPLIT = {
    "2": ("2_charles_soft",
          "I'm all right. I don't want to touch one, that's all. No. I'd rather not.",
          [("I'm all right.", 0.42),
           ("I don't want to touch one, that's all.", 0.42),
           ("No. I'd rather not.", 0.0)]),
    "4": ("4_charles_angry",
          "But I wouldn't go on whining, like you. Scaredy Hooper. You are scared. You're scared now.",
          [("But I wouldn't go on whining, like you.", 0.38),
           ("Scaredy Hooper.", 0.30),
           ("You are scared.", 0.30),
           ("You're scared now.", 0.0)]),
    "5": ("5_hooper_loud",
          "It's because of me. You're scared of me, Kingshaw, you're Mummy's little scaredy-pet. You don't know what I might do to you, I could do anything at all.",
          [("It's because of me.", 0.34),
           ("You're scared of me, Kingshaw.", 0.34),
           ("You're Mummy's little scaredy-pet.", 0.34),
           ("You don't know what I might do to you.", 0.30),
           ("I could do anything at all.", 0.0)]),
    "7": ("7_hooper_begging",
          "I don't like it here, I want to go home. I don't want to be lost. I want to go home.",
          [("I don't like it here, I want to go home.", 0.42),
           ("I don't want to be lost.", 0.38),
           ("I want to go home.", 0.0)]),
}


def gen(text, ref, rtext, mt, out, extra=None, seed=42):
    cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
           "--backend", "vulkan", "--threads", "6",
           "--voice-ref", ref, "--reference-text", rtext,
           "--text", text,
           "--request-option", "max_tokens=%d" % mt, "--seed", str(seed),
           "--out", out,
           "--session-option", "dots_tts.mem_saver=true", "--metrics"]
    for e in (extra or []):
        i = cmd.index("--out")
        cmd[i:i] = ["--request-option", e]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ACPP_DIR)
    ok = os.path.exists(out) and os.path.getsize(out) > 40000
    if not ok:
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        print("     ERR", " | ".join(tail), flush=True)
    return ok


def rd(p):
    with wave.open(p, "rb") as w:
        sr, ch, nf = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = w.readframes(nf)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def trim(a, sr, thr_db=-45.0, pad=0.05):
    n = int(0.01 * sr)
    k = len(a) // n
    if k < 3:
        return a
    e = np.array([np.sqrt(np.mean(a[i * n:(i + 1) * n] ** 2) + 1e-12) for i in range(k)])
    db = 20 * np.log10(e + 1e-9)
    on = np.where(db > thr_db)[0]
    if len(on) == 0:
        return a
    s = max(0, int((on[0]) * n - pad * sr))
    t = min(len(a), int((on[-1] + 1) * n + pad * sr))
    return a[s:t]


def wr(p, a, sr):
    x = np.clip(a, -1.0, 1.0)
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767.0).astype("<i2").tobytes())


def main():
    tags = sys.argv[1:] or list(SPLIT.keys())
    os.makedirs(TMP, exist_ok=True)
    for tag in tags:
        gid, full, parts = SPLIT[tag]
        ref = os.path.join(REF, gid + ".wav")
        rtext = REF_TEXT[gid]
        print("=" * 72, flush=True)
        print("BK_%s  %s  %d 句" % (tag, gid, len(parts)), flush=True)
        # 清掉旧分句，避免上一次残留的索引错位
        for f in os.listdir(TMP):
            if f.startswith("BK%s_p" % tag) and f.endswith(".wav"):
                os.remove(os.path.join(TMP, f))
        chunks = []
        for i, (txt, gap) in enumerate(parts):
            pf = os.path.join(TMP, "BK%s_p%d.wav" % (tag, i))
            mt = max(180, int(len(txt.split()) * 22) + 120)
            t0 = time.time()
            ok = gen(txt, ref, rtext, mt, pf)
            print("  [%d] %-46s mt=%-4d %s %4.1fs" %
                  (i, txt[:46], mt, "OK" if ok else "FAIL", time.time() - t0), flush=True)
            if not ok:
                time.sleep(15)
                ok = gen(txt, ref, rtext, mt, pf)
                print("       retry ->", "OK" if ok else "FAIL", flush=True)
            if not ok:
                continue
            a, sr = rd(pf)
            chunks.append((trim(a, sr), gap))
            time.sleep(12)
        if not chunks:
            print("  ALL FAIL", flush=True)
            continue
        sr = 48000
        pieces = []
        for i, (a, gap) in enumerate(chunks):
            pieces.append(a)
            if i < len(chunks) - 1 and gap > 0:
                pieces.append(np.zeros(int(gap * sr), dtype=np.float32))
        y = np.concatenate(pieces)
        out = os.path.join(OUT, "BK_%s_r.wav" % tag)
        wr(out, y, sr)
        print("  -> %s  %.2fs" % (os.path.basename(out), len(y) / sr), flush=True)
        time.sleep(18)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
