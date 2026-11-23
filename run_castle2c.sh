#!/bin/bash
set -u
ACPP="/c/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp"
REF="G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav"
RTE="called Sirius, is reaching Earth after traveling at 186,000 miles per second."
OUT=/g/_setup/dots_castle2
PLAIN="$(cat /g/_setup/dots_test/castle40.txt)"
cd "$ACPP" || exit 1
run() {
  ./audiocpp_cli.exe --task tts --family dots_tts --model "E:/tts-models/acpp/DotTTS-Edit-GGUF" \
    --backend vulkan --threads 6 --voice-ref "$REF" --reference-text "$RTE" \
    --text "$1" --seed 42 --out "$2" \
    --session-option dots_tts.mem_saver=true 2>&1 | grep -E "audio_out|error|failed" | tail -1
}
echo "=== C: rate 0.71 ==="
run "<rate factor=\"0.71\">$PLAIN</rate>" "$OUT/C_rate071.wav"
echo ALLDONE
