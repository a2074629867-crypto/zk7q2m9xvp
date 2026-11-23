#!/usr/bin/env bash
# 回算分级工作流：ctl 8 seed + tag 3 seed（本地测量，不碰云端）
set -u
cd /g/_setup || exit 1
PY="G:/Python310/python.exe"

build_prom() {  # $1=dir  $2=prefix
  local d="$1" p="$2"
  local pd="_mt_adv_prom_${p##*_}"
  local n
  n=$(ls "$pd" 2>/dev/null | wc -l)
  [ "$n" -ge 49 ] && return 0
  local U
  U=$(ls "$d"/*.wav 2>/dev/null | sed 's#.*/##; s#\.wav$##' | paste -sd,)
  [ -z "$U" ] && return 0
  echo "  [prom] $d"
  timeout 900 "$PY" _prom_build.py --prefix "$p" --dir "$d" --units "$U" --prom-out "$pd" >/dev/null 2>&1
}

measure_dir() {  # $1=dir  $2=out
  local d="$1" o="$2"
  [ -f "$o" ] && { echo "  [skip] $d"; return 0; }
  "$PY" - "$d" "$o" <<'PY'
import json, os, sys, glob
d, o = sys.argv[1], sys.argv[2]
st = json.load(open("_mt_adv_state.json", encoding="utf-8"))["units"]
pd = "_mt_adv_prom_" + d.split("_")[-1]
items = []
for w in sorted(glob.glob(d + "/*.wav")):
    uid = os.path.basename(w)[:-4]
    p = os.path.join(pd, "%s__%s.prom" % (d, uid))
    if not os.path.exists(p) or uid not in st:
        continue
    x = st[uid]
    items.append(dict(uid=uid, text=x["text"], wav=w, prom=p,
                      advs=x.get("advs") or [x["adv"]]))
json.dump(items, open("_pol_man_tmp.json", "w", encoding="utf-8"), ensure_ascii=False)
print("  [meas] %s %d 条" % (d, len(items)))
PY
  timeout 1800 "$PY" _adv_prom.py --batch _pol_man_tmp.json --out "$o" >/dev/null 2>&1
  cp -f _pol_man_tmp.json "_pol_man_$(basename $d).json" 2>/dev/null
}

echo "=== ctl 8 seed ==="
for s in 2061 2063 2065 2067 2069 2071 2073 2075; do
  build_prom "_mt_adv_ctl_$s" "_mt_adv_ctl_$s"
  measure_dir "_mt_adv_ctl_$s" "_pol_res__mt_adv_ctl_$s.json"
done

echo "=== tag 3 seed（只用于验证「标签是不是最后手段」）==="
for s in 2061 2063 2065; do
  build_prom "_mt_adv_s$s" "_mt_adv_s$s"
  measure_dir "_mt_adv_s$s" "_pol_res__mt_adv_s$s.json"
done

echo "=== 汇总 ==="
"$PY" mt_seed_policy.py --simulate --seeds 2061,2063,2065,2067,2069,2071,2073,2075 2>&1 | tail -16
echo
"$PY" mt_seed_policy.py --simulate --seeds 2061,2063,2065 --tag 2>&1 | tail -12
echo DONE_POLICY_SIM
