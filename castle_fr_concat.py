# -*- coding: utf-8 -*-
"""把每组切片拼成一条 8-13s 的长参考（voice_ref 用），中间插 0.35s 静音。
输出 G:/_setup/castle_fr_ref/<group>.wav
"""
import os
import subprocess

FF = "E:/tool/oopz/ffmpeg.exe"
CLEAN = "G:/_setup/castle_fr_clean"
OUT = "G:/_setup/castle_fr_ref"
GAP = 0.35

ORDER = {
    "1_charles_normal": ["c01_ne_comme_ca", "c02_breaud", "c03_vernet", "c04_ca_va_mieux",
                         "c05_non_monsieur", "c06_si_elle_aime", "c07_c_moi_tinvite",
                         "c08_encore_riche"],
    "2_charles_soft": ["c09_rien_marriver", "c10_jamais_peur", "c11_dartagnan",
                       "c12_non_maman", "c13_cadeau_thomas", "c14_plus_rien_faire"],
    "3_charles_excited": ["c15_pas_de_mere", "c16_menteur", "c17_breaud_venu", "c18_il_taime"],
    "4_charles_angry": ["c19_jeté_pierre", "c20_corbeau", "c21_demande_pardon", "c22_vas_y_repete"],
    "5_hooper_loud": ["h01_riche_pauvres", "h02_femmes_seules", "h03_argent_robes"],
    "6_hooper_calm": ["h04a_intro_verse", "h04b_papa_seul"],
    "6b_hooper_scold": ["h04a_sale_voleur", "h04b_tenfuies", "h04b2_menteur",
                        "h04c_menteur_voleur", "h04d_reveiller_pere"],
    "7_hooper_begging": ["h05_vertige", "h06_cest_moi_1", "h07_cest_moi_2", "h08_pardon"],
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for grp, ids in ORDER.items():
        files = [os.path.join(CLEAN, grp, i + ".wav") for i in ids]
        files = [f for f in files if os.path.exists(f)]
        if not files:
            print("SKIP", grp)
            continue
        # 用 concat filter：每段后接一段静音
        inputs = []
        for f in files:
            inputs += ["-i", f]
        parts = []
        labels = []
        for i in range(len(files)):
            if i < len(files) - 1:
                parts.append("[%d:a]apad=pad_dur=%s[a%d]" % (i, GAP, i))
                labels.append("[a%d]" % i)
            else:
                parts.append("[%d:a]anull[a%d]" % (i, i))
                labels.append("[a%d]" % i)
        fc = ";".join(parts) + ";" + "".join(labels) + "concat=n=%d:v=0:a=1[out]" % len(files)
        dst = os.path.join(OUT, grp + ".wav")
        r = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error"] + inputs +
                           ["-filter_complex", fc, "-map", "[out]",
                            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", dst],
                           capture_output=True, text=True)
        if r.returncode:
            print("ERR", grp, r.stderr.strip()[:120])
        else:
            d = subprocess.run([FF, "-hide_banner", "-i", dst], capture_output=True, text=True).stderr
            dur = [l for l in d.splitlines() if "Duration" in l]
            print("OK  %-20s %s" % (grp, dur[0].split("Duration:")[1].split(",")[0].strip() if dur else "?"))


if __name__ == "__main__":
    main()
