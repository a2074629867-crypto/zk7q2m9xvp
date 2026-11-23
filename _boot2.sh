#!/bin/bash
cd /mnt/workspace/acpp || exit 1
echo "SIZE gguf=$(stat -c%s dots.gguf 2>/dev/null || echo 0)"
tar -xzf bundle.tgz 2>&1 | head -3
echo "CLOUD $(ls cloud 2>/dev/null | tr '\n' ' ')"
export LD_LIBRARY_PATH=$PWD/dist/lib:$PWD/dist/bin:$PWD/dist/lib64:$LD_LIBRARY_PATH
B=$PWD/dist/lib/audiocpp_server
echo "RUNCHK $($B --version 2>&1 | head -2 | tr '\n' '|')"
$B --help > help.txt 2>&1
echo "HELPLINES $(wc -l < help.txt)"
echo "----- head -----"
head -34 help.txt
echo "----- flags -----"
grep -oE '^\s+--[a-z0-9-]+' help.txt | awk '{print $1}' | sort -u | tr '\n' ' '
echo
echo "DONE stage2"
