# -*- coding: utf-8 -*-
"""按用户标注的 7 组时间码，从法语原声 eac3 切出 30 个音色切片（未分离）。
输出 G:/_setup/castle_fr_raw/<group>/<id>.wav
"""
import os
import subprocess

FF = "E:/tool/oopz/ffmpeg.exe"
SRC = "G:/NEW MOVIE/我是城堡之王/Je.suis.le.seigneur.du.chateau.1989.French.eac3"
OUT = "G:/_setup/castle_fr_raw"

PAD = 0.12  # 前后各留一点，避免削掉起音/尾音

# (组, 角色, id, t0, t1, 台词)
SLICES = [
    # ---- 1. Charles 普通说话（4 组之一）
    ("1_charles_normal", "charles", "c01_ne_comme_ca", 272.866, 273.940, "Je suis né comme ça aussi?"),
    ("1_charles_normal", "charles", "c02_breaud", 337.349, 338.142, "Vous êtes M. Bréaud?"),
    ("1_charles_normal", "charles", "c03_vernet", 340.206, 341.235, "Moi, je suis Charles Vernet."),
    ("1_charles_normal", "charles", "c04_ca_va_mieux", 362.356, 363.892, "Non. Ça va mieux, maintenant."),
    ("1_charles_normal", "charles", "c05_non_monsieur", 4152.431, 4153.248, "Non, monsieur."),
    ("1_charles_normal", "charles", "c06_si_elle_aime", 4184.758, 4186.031, "Et si elle, elle vous aime pas?"),
    ("1_charles_normal", "charles", "c07_c_moi_tinvite", 4307.514, 4308.961, "Laisse. C'est moi qui t'invite."),
    ("1_charles_normal", "charles", "c08_encore_riche", 4310.552, 4311.761, "je suis encore très riche."),

    # ---- 2. Charles 轻声说话
    ("2_charles_soft", "charles", "c09_rien_marriver", 2983.240, 2984.460, "Mais il pouvait rien m'arriver."),
    ("2_charles_soft", "charles", "c10_jamais_peur", 2986.927, 2988.520, "Maman, j'aurai plus jamais peur."),
    ("2_charles_soft", "charles", "c11_dartagnan", 2998.313, 2999.453, "Maman, je suis d'Artagnan."),
    ("2_charles_soft", "charles", "c12_non_maman", 3935.283, 3935.917, "Non, maman."),
    ("2_charles_soft", "charles", "c13_cadeau_thomas", 3937.557, 3938.797, "C'est le cadeau de Thomas."),
    ("2_charles_soft", "charles", "c14_plus_rien_faire", 4917.033, 4918.553, "Tu peux plus rien me faire, maintenant."),

    # ---- 3. Charles 激动
    ("3_charles_excited", "charles", "c15_pas_de_mere", 2277.334, 2279.054, "Tu dis ça parce que t'as pas de mère!"),
    ("3_charles_excited", "charles", "c16_menteur", 2289.850, 2293.477, "Menteur! Ton père n'est rien du tout! Il plaît pas à ma mère, elle le déteste!"),
    ("3_charles_excited", "charles", "c17_breaud_venu", 4540.277, 4541.531, "M. Bréaud est venu."),
    ("3_charles_excited", "charles", "c18_il_taime", 4543.524, 4544.291, "Il t'aime."),

    # ---- 4. Charles 生气
    ("4_charles_angry", "charles", "c19_jeté_pierre", 2540.186, 2541.980, "Qui a jeté la pierre dans ma chambre?"),
    ("4_charles_angry", "charles", "c20_corbeau", 2545.865, 2547.405, "Qui a mis le corbeau dans mon lit?"),
    ("4_charles_angry", "charles", "c21_demande_pardon", 2556.495, 2558.898, "Je demande pardon à Charles pour tout ce que j'ai fait."),
    ("4_charles_angry", "charles", "c22_vas_y_repete", 2559.928, 2560.961, "Vas-y, répète!"),

    # ---- 5. Hooper(Thomas) 大声说
    ("5_hooper_loud", "hooper", "h01_riche_pauvres", 2295.090, 2298.450, "Il est riche et vous êtes pauvres. C'est pour ça que vous êtes venus,"),
    ("5_hooper_loud", "hooper", "h02_femmes_seules", 2298.804, 2302.879, "pour que ta mère puisse se marier avec mon père. Les femmes seules font ça."),
    ("5_hooper_loud", "hooper", "h03_argent_robes", 2302.879, 2306.390, "Il faut qu'on leur donne de l'argent, une maison, des robes..."),

    # ---- 6. Hooper 平静普通
    ("6_hooper_calm", "hooper", "h04_sale_voleur", 1926.704, 1929.991, "Voleur! Espèce de sale voleur."),

    # ---- 7. Hooper 求饶
    ("7_hooper_begging", "hooper", "h05_vertige", 2506.156, 2508.926, "Je peux pas, j'ai le vertige!"),
    ("7_hooper_begging", "hooper", "h06_cest_moi_1", 2542.932, 2543.865, "C'est moi."),
    ("7_hooper_begging", "hooper", "h07_cest_moi_2", 2547.956, 2548.899, "C'est moi."),
    ("7_hooper_begging", "hooper", "h08_pardon", 2561.775, 2564.588, "Je demande pardon à Charles pour ce que j'ai fait."),
]


def main():
    ok = 0
    for grp, who, sid, t0, t1, line in SLICES:
        d = os.path.join(OUT, grp)
        os.makedirs(d, exist_ok=True)
        a = max(0.0, t0 - PAD)
        dur = (t1 + PAD) - a
        out = os.path.join(d, sid + ".wav")
        cmd = [FF, "-y", "-hide_banner", "-loglevel", "error",
               "-ss", "%.3f" % a, "-t", "%.3f" % dur, "-i", SRC,
               "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(out):
            ok += 1
            print("OK  %-22s %6.2fs  %s" % (sid, dur, line[:52]))
        else:
            print("ERR %-22s %s" % (sid, r.stderr.strip()[:90]))
    print("\n%d/%d 切片完成 -> %s" % (ok, len(SLICES), OUT))


if __name__ == "__main__":
    main()
