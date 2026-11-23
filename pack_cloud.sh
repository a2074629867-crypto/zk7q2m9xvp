#!/usr/bin/env bash
# =============================================================================
# 打「云端小件包」——只装仓库里放不下、又必须原样带走的东西。
#
# 为什么只要 194MB：代码走 git clone（公开仓库），大模型走 HF/ModelScope 直下，
# 剩下真正没法重建的只有「用户手切的参考音频」和「判据基线小台账」。
#
# 用法：
#     bash pack_cloud.sh            # 生成 _cloudpack.tar + 打印清单
#     bash pack_cloud.sh --check    # 只打印清单不打包
#
# 包内结构（解到云端 MR_ROOT 即用）：
#     _ref9/                  33 组 9s 参考 + _index_srt.json
#     castle_fr_ref/          用户亲自切的 13.58s Charles 参考（USER_REF 指向它）
#     out_sv/                 Z-norm 背景集 + 缓存
#     models/sv_hub/          wespeaker ResNet34/293 声纹 ONNX
#     emo_bench/out/ref_stats.json   情绪档分位基线
# =============================================================================
set -euo pipefail

ROOT="${MR_ROOT:-$(pwd)}"
cd "$ROOT"
OUT="$ROOT/_cloudpack.tar"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

ITEMS=(
  "_ref9"
  "castle_fr_ref"
  "out_sv/cues_znorm2.json"
  "out_sv/bg_castle.json"
  "out_sv/bg_hopegap.json"
  "out_sv/final_emo_znorm2.json"
  "models/sv_hub"
  "emo_bench/out/ref_stats.json"
)
# 旧片留下的其它背景集（存在就带上，很小）
for f in out_sv/cues_znorm.json out_sv/cluster.json out_sv/cues1nn.json out_sv/final_emo_znorm.json; do
  [ -f "$f" ] && ITEMS+=("$f")
done

printf '\n\033[1;36m== 云端包清单 ==\033[0m\n'
missing=0
total=0
for it in "${ITEMS[@]}"; do
  if [ ! -e "$it" ]; then
    printf '  \033[31m缺\033[0m  %s\n' "$it"; missing=$((missing+1)); continue
  fi
  if [ -d "$it" ]; then
    n=$(find "$it" -type f | wc -l | tr -d ' ')
    sz=$(du -sb "$it" | cut -f1)
    printf '  %-34s %4d 文件  %8s\n' "$it" "$n" "$(du -sh "$it" | cut -f1)"
  else
    sz=$(stat -c%s "$it" 2>/dev/null || wc -c < "$it")
    printf '  %-34s %4s       %8s\n' "$it" "1" "$(du -h "$it" | cut -f1)"
  fi
  total=$((total + sz))
done

printf '\n  合计 %s   缺件 %d 个\n' "$(numfmt --to=iec --suffix=B "$total" 2>/dev/null || echo "$total B")" "$missing"
[ "$missing" -gt 0 ] && printf '  \033[33m注意\033[0m：缺的条目云端会跑不了对应闸门\n'

if [ "$CHECK_ONLY" -eq 1 ]; then
  exit 0
fi

printf '\n打包中 ...\n'
rm -f "$OUT"
tar -cf "$OUT" --exclude='*.pyc' --exclude='__pycache__' "${ITEMS[@]}"
printf '  写出 %s  (%s)\n' "$OUT" "$(du -h "$OUT" | cut -f1)"
printf '  条目 %d 个，内含文件 %d 个\n' "${#ITEMS[@]}" "$(tar -tf "$OUT" | grep -vc '/$')"

cat <<EOF

上传到云实例（任选其一）：
  scp _cloudpack.tar root@<公网IP>:/root/mintreader/
  # 或先传 COS，再在实例里 coscmd download

云端解包（deploy_cloud.sh 第 5 步会自动做）：
  tar -xf _cloudpack.tar -C /root/mintreader

校验（两边 md5 应一致）：
  md5sum _cloudpack.tar     # 本机
  md5sum _cloudpack.tar     # 云上
EOF
