# -*- coding: utf-8 -*-
"""参考本身能不能被判成「厌恶/disgusted」——决定 警惕 是否 emo_unreachable。"""
import json, os, sys
sys.path.insert(0, "G:/_setup"); sys.path.insert(0, "G:/_setup/emo_bench")
import ser as S
HERE = "G:/_setup"
REF = {
 "Thomas_wary_1":   "_cloud_backup/voice_lib/Thomas_wary_1.wav",
 "Thomas_defiant_1":"_cloud_backup/voice_lib/Thomas_defiant_1.wav",
 "Charles_angry_2": "_cloud_backup/voice_lib/Charles_angry_2.wav",
 "Fielding_wary_c301": "refs_cast/Fielding_wary_c301.wav",
 "Fielding_wary_c049": "refs_cast/Fielding_wary_c049.wav",
 "Fielding_defiant_c078": "refs_cast/Fielding_defiant_c078.wav",
}
e2v = S.E2V(os.path.join(HERE, "models/ms/iic/emotion2vec_plus_large"))
for k, p in REF.items():
    p = os.path.join(HERE, p)
    if not os.path.exists(p):
        print("%-22s MISSING" % k); continue
    sc = e2v.score(p) or {}
    top = sc.get("_top")
    print("%-22s top=%-16s disg=%.4f fear=%.4f sad=%.4f neut=%.4f"
          % (k, top, sc.get("厌恶/disgusted",0), sc.get("恐惧/fearful",0),
             sc.get("难过/sad",0), sc.get("中立/neutral",0)), flush=True)
