# -*- coding: utf-8 -*-
"""批量：切片 -> 44.1k -> HTDemucs 分离 -> vocals -> 高通/降噪/归一 -> 成品

输入 G:/_setup/castle_fr_raw/<group>/*.wav
输出 G:/_setup/castle_fr_clean/<group>/<id>.wav   (48k mono pcm16)
     G:/_setup/castle_fr_clean/<group>/<id>_bed.wav (伴奏，仅留档，不入库)
"""
import os
import shutil
import subprocess
import sys

FF = "E:/tool/oopz/ffmpeg.exe"
ACPP_DIR = "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp"
ACPP = os.path.join(ACPP_DIR, "audiocpp_cli.exe")
MODEL = "E:/tts-models/HTDemucs-GGUF/htdemucs-q8_0.gguf"
RAW = "G:/_setup/castle_fr_raw"
CLEAN = "G:/_setup/castle_fr_clean"
TMP = "G:/_setup/_sep_tmp"

# 人声后处理：80Hz 高通去低频残留 + 轻降噪 + 峰值归一
AF = ("highpass=f=80:poles=2,"
      "afftdn=nf=-30:tn=1,"
      "loudnorm=I=-20:TP=-1.5:LRA=11")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def process(src, dst, bed_dst):
    base = os.path.splitext(os.path.basename(src))[0]
    t44 = os.path.join(TMP, base + "_44.wav")
    sepdir = os.path.join(TMP, base + "_sep")
    os.makedirs(sepdir, exist_ok=True)

    r = run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
             "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", t44])
    if r.returncode:
        return "ERR ffmpeg44 " + r.stderr[:80]

    r = run([ACPP, "--task", "sep", "--family", "htdemucs", "--model", MODEL,
             "--backend", "vulkan", "--threads", "6",
             "--audio", t44, "--out-dir", sepdir], cwd=ACPP_DIR)
    voc = os.path.join(sepdir, "vocals.wav")
    if not os.path.exists(voc):
        return "ERR sep " + (r.stdout + r.stderr).strip()[-100:]

    r = run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", voc,
             "-af", AF, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", dst])
    if r.returncode:
        return "ERR ffmpegpost " + r.stderr[:80]

    # 伴奏留档（人声反相不现实，直接把 other+bass+drums 混一起做参考）
    run([FF, "-y", "-hide_banner", "-loglevel", "error",
         "-i", os.path.join(sepdir, "other.wav"),
         "-i", os.path.join(sepdir, "bass.wav"),
         "-i", os.path.join(sepdir, "drums.wav"),
         "-filter_complex", "[0][1][2]amix=inputs=3:normalize=0",
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", bed_dst])

    shutil.rmtree(sepdir, ignore_errors=True)
    if os.path.exists(t44):
        os.remove(t44)
    return "OK"


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    os.makedirs(TMP, exist_ok=True)
    ok = err = 0
    for grp in sorted(os.listdir(RAW)):
        gdir = os.path.join(RAW, grp)
        if not os.path.isdir(gdir):
            continue
        odir = os.path.join(CLEAN, grp)
        os.makedirs(odir, exist_ok=True)
        for f in sorted(os.listdir(gdir)):
            if not f.endswith(".wav") or f.startswith("_"):
                continue
            if only and only not in f:
                continue
            dst = os.path.join(odir, f)
            bed = os.path.join(odir, os.path.splitext(f)[0] + "_bed.wav")
            if os.path.exists(dst) and os.path.getsize(dst) > 20000:
                print("[skip] %s/%s" % (grp, f))
                continue
            st = process(os.path.join(gdir, f), dst, bed)
            print("%-4s %-24s %s" % (st, f, grp), flush=True)
            if st == "OK":
                ok += 1
            else:
                err += 1
    print("\n完成 %d，失败 %d -> %s" % (ok, err, CLEAN))


if __name__ == "__main__":
    main()
