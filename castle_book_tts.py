# -*- coding: utf-8 -*-
"""用 8 组法语原声音色，让每个角色念小说里对应情绪的原文台词。
串行跑（禁并发 audiocpp），每组之间 sleep 20s。
"""
import os
import subprocess
import time

ACPP_DIR = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/acpp/DotTTS-Edit-GGUF"
REF = "G:/_setup/castle_fr_ref"
OUT = "G:/_setup/dots_edit2"

REF_TEXT = {
    "1_charles_normal": "Je suis né comme ça aussi? Vous êtes M. Bréaud? Moi, je suis Charles Vernet. Non. Ça va mieux, maintenant. Non, monsieur. Et si elle, elle vous aime pas? Laisse. C'est moi qui t'invite. je suis encore très riche.",
    "2_charles_soft": "Mais il pouvait rien m'arriver. Maman, j'aurai plus jamais peur. Maman, je suis d'Artagnan. Non, maman. C'est le cadeau de Thomas. Tu peux plus rien me faire, maintenant.",
    "3_charles_excited": "Tu dis ça parce que t'as pas de mère! Menteur! Ton père n'est rien du tout! Il plaît pas à ma mère, elle le déteste! M. Bréaud est venu. Il t'aime.",
    "4_charles_angry": "Qui a jeté la pierre dans ma chambre? Qui a mis le corbeau dans mon lit? Je demande pardon à Charles pour tout ce que j'ai fait. Vas-y, répète!",
    "5_hooper_loud": "Il est riche et vous êtes pauvres. C'est pour ça que vous êtes venus, pour que ta mère puisse se marier avec mon père. Les femmes seules font ça. Il faut qu'on leur donne de l'argent, une maison, des robes...",
    "6_hooper_calm": "N'accablez point, madame, un prince malheureux. Il ne faut point ici nous attendrir tous deux. Un trouble assez cruel m'agite et me dévore sans que des pleurs si chers me déchirent encore. J'ai dit à papa que je voulais rester seul avec vous.",
    "6b_hooper_scold": "Espèce de sale voleur. Tu t'enfuies. Menteur! T'es un menteur et un voleur. Je vais aller réveiller mon père et je vais tout lui dire.",
    "7_hooper_begging": "Je peux pas, j'ai le vertige! C'est moi. C'est moi. Je demande pardon à Charles pour ce que j'ai fait.",
}

# 组 -> (英文台词, max_tokens)
LINES = [
    ("1_charles_normal", "It's called St Vincent's. That's nothing. It's only an old house. I'm all right.", 420),
    ("2_charles_soft", "I'm all right. I don't want to touch one, that's all. No. I'd rather not.", 420),
    ("3_charles_excited", "I'm a bowman, I'm the head warrior of this castle. If I shoot an arrow, I can kill you.", 460),
    ("4_charles_angry", "But I wouldn't go on whining, like you. Scaredy Hooper. You are scared. You're scared now.", 460),
    ("5_hooper_loud", "It's because of me. You're scared of me, Kingshaw, you're Mummy's little scaredy-pet. You don't know what I might do to you, I could do anything at all.", 620),
    ("6_hooper_calm", "I'm King of the Castle! You'd better come down, show-off, if you fall you'll split your head open.", 480),
    ("6b_hooper_scold", "Open one of the cases, then. I'll let you. Why not? Scaredy-baby, scared of a moth! Pick one up.", 500),
    ("7_hooper_begging", "I don't like it here, I want to go home. I don't want to be lost. I want to go home.", 460),
]


def main():
    for gid, text, mt in LINES:
        ref = os.path.join(REF, gid + ".wav")
        out = os.path.join(OUT, "BK_" + gid.split("_")[0] + ".wav")
        if not os.path.exists(ref):
            print("MISSING ref", gid, flush=True)
            continue
        if os.path.exists(out) and os.path.getsize(out) > 200000:
            print("[skip]", gid, flush=True)
            continue
        print("=" * 70, flush=True)
        print(gid, "|", text[:70], flush=True)
        cmd = [ACPP, "--task", "tts", "--family", "dots_tts", "--model", MODEL,
               "--backend", "vulkan", "--threads", "6",
               "--voice-ref", ref, "--reference-text", REF_TEXT[gid],
               "--text", text,
               "--request-option", "max_tokens=%d" % mt, "--seed", "42",
               "--out", out,
               "--session-option", "dots_tts.mem_saver=true", "--metrics"]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=ACPP_DIR)
        tail = [l for l in (r.stdout + r.stderr).splitlines()
                if any(k in l for k in ("audio_duration_ms", "failed", "error", "Error"))]
        print("  " + (" | ".join(tail[-2:]) if tail else "no metrics"), flush=True)
        print("  size:", os.path.getsize(out) if os.path.exists(out) else 0, flush=True)
        time.sleep(20)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
