#!/bin/bash
set -u
ACPP="/c/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab/acpp"
REF="G:/_setup/dots_edit2/REF_early2_9.17s.wav"
RTE="$(cat /g/_setup/dots_edit2/REF_early2.txt)"
OUT=/g/_setup/dots_open
PLAIN="$(cat /g/_setup/dots_test/castle40.txt)"
cd "$ACPP" || exit 1
run() {
  ./audiocpp_cli.exe --task tts --family dots_tts --model "E:/tts-models/acpp/DotTTS-Edit-GGUF" \
    --backend vulkan --threads 6 --voice-ref "$REF" --reference-text "$RTE" \
    --text "$1" --seed 42 --out "$2" \
    --session-option dots_tts.mem_saver=true 2>&1 | grep -E "audio_out|error|failed" | tail -1
}
echo "=== OPEN-A: 开头参考 + 无标签 ==="
run "$PLAIN" "$OUT/A_open.wav"
echo "=== OPEN-C: 开头参考 + rate 0.71 ==="
run "<rate factor=\"0.71\">$PLAIN</rate>" "$OUT/C_open.wav"
echo ALLDONE
