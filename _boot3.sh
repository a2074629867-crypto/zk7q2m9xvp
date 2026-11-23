#!/bin/bash
cd /mnt/workspace/acpp || exit 1
EXP=2962805408
ACT=$(stat -c%s dots.gguf 2>/dev/null || echo 0)
echo "GGUF act=$ACT exp=$EXP"
if [ "$ACT" -ge 2960000000 ]; then
  S=$(sha256sum dots.gguf | cut -d' ' -f1)
  echo "SHA ${S:0:16} expect 5f2df7c42849feaa"
else
  echo "SIZE_SHORT keep_downloading"
fi
mkdir -p models/DotTTS-Edit-GGUF
if [ ! -f models/DotTTS-Edit-GGUF/dots-tts-edit-q8_0.gguf ] && [ "$ACT" -ge 2960000000 ]; then
  mv dots.gguf models/DotTTS-Edit-GGUF/dots-tts-edit-q8_0.gguf && echo MOVED
fi
cat > models/DotTTS-Edit-GGUF/.audiocpp-package-dots_tts_edit_q8_0.json <<'EOF'
{
  "schema_version": 1,
  "package_id": "dots_tts_edit_q8_0",
  "repo": "HereIsMark/audio.cpp-gguf",
  "requested_revision": "master",
  "resolved_revision": "master",
  "installed_at_unix": 1791980382,
  "files": {
    "DotTTS-Edit-GGUF/dots-tts-edit-q8_0.gguf": {
      "size": 2962805408,
      "etag": "5f2df7c42849feaaa4b3f0808b72804132bee6e6314563125973b15fc1e3a122"
    }
  }
}
EOF
ls -l models/DotTTS-Edit-GGUF/
pkill -f audiocpp_server 2>/dev/null
sleep 1
nohup ./dist/audiocpp_server --models models --backend cuda --host 127.0.0.1 --port 8080 > server.log 2>&1 &
echo "STARTED pid=$!"
sleep 30
echo "-- models API --"
curl -s --max-time 8 http://127.0.0.1:8080/v1/models | head -c 700
echo
echo "-- log tail --"
tail -12 server.log
echo "DONE stage3"
