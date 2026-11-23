cd /home/aistudio/up
echo "STEP1 untar"
tar xzf all.tgz && echo UNTAR_OK || echo UNTAR_FAIL
echo "count: $(ls voice_lib | wc -l)"
echo "STEP2 copy"
cp -f voice_lib/*.wav /home/aistudio/voice_lib/ && echo COPY_OK
echo "voice wav now: $(ls /home/aistudio/voice_lib/*.wav | wc -l)"
echo "STEP3 prompt"
python3 /home/aistudio/up/merge_prompt.py
echo "lines: $(wc -l < /home/aistudio/voice_lib/prompt_text)"
echo DONE
