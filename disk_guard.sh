#!/bin/bash
# C: 盘空间守护：s1 每次存盘会删旧 ckpt，实测这些删除会进 C: 回收站（931MB/个）。
# 上次就是这么把 C: 撑到 100% 导致训练崩在 e12。这里每 60s 检查一次，
# 一旦 C: 可用 < 4GB 就把回收站里的大文件永久删除（find -delete 不进回收站）。
RB="/c/\$Recycle.Bin"
LOG=/g/_setup/disk_guard.log
: > "$LOG"
echo "$(date '+%F %H:%M:%S') guard start, C: avail=$(df -h /c | tail -1 | awk '{print $4}')" >> "$LOG"
while true; do
  avail_kb=$(df -k /c | tail -1 | awk '{print $4}')
  if [ "$avail_kb" -lt 4194304 ]; then   # < 4GB
    echo "$(date '+%H:%M:%S') C: 仅剩 $((avail_kb/1024))MB -> 清理回收站" >> "$LOG"
    find "$RB" -type f -size +50M -delete 2>/dev/null
    sleep 4
    avail2=$(df -k /c | tail -1 | awk '{print $4}')
    echo "$(date '+%H:%M:%S') 清理后 C: $((avail2/1024))MB" >> "$LOG"
  fi
  sleep 60
done
