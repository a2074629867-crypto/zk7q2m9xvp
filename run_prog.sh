#!/bin/bash
set -u
ACPP="/c/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp"
REF="G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
RTE="called Sirius, is reaching Earth after traveling at 186,000 miles per second."
TXT="$(cat /g/_setup/scene_calmdeep.txt)"
OUT=/g/_setup/dots_prog
cd "$ACPP" || exit 1
run() {  # $1=text  $2=out
  ./audiocpp_cli.exe --task tts --family dots_tts --model "E:/tts-models/acpp/DotTTS-Edit-GGUF" \
    --backend vulkan --threads 6 --voice-ref "$REF" --reference-text "$RTE" \
    --text "$1" --seed 42 --out "$2" \
    --session-option dots_tts.mem_saver=true 2>&1 | grep -E "audio_out|error|failed" | tail -1
}
echo "=== A: rate 0.80 only ==="
run "<rate, factor=0.80>$TXT</rate>" "$OUT/A_rate080.wav"
echo "=== B: FLAT compiler (rate .84 + 3x pause L3) ==="
run "$(cat /g/_setup/tag_flat.txt)" "$OUT/B_flat.wav"
echo "=== C: MC compiler (per-clause rate + last-word stretch) ==="
run "$(cat /g/_setup/tag_mc.txt)" "$OUT/C_mc.wav"
echo ALLDONE
