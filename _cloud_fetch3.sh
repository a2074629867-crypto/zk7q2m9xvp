cd /home/aistudio && mkdir -p up2 && cd up2
curl -sSL --max-time 180 -o c01.bin 'https://ntfy.sh/file/jUPZUYBhkTHY.gz'
rm -rf voice_lib && tar xzf c01.bin && ls voice_lib | wc -l
cp -f voice_lib/*.wav /home/aistudio/voice_lib/
cat prompt_text >> /home/aistudio/voice_lib/prompt_text
sort -u /home/aistudio/voice_lib/prompt_text > /tmp/pt && mv /tmp/pt /home/aistudio/voice_lib/prompt_text
grep -c . /home/aistudio/voice_lib/prompt_text
grep '^Thomas_loud_6|' /home/aistudio/voice_lib/prompt_text | head -1
ls /home/aistudio/voice_lib/*.wav | wc -l
echo DONE
