# -*- coding: utf-8 -*-
"""BT 下载，但 peer 流量走 SOCKS5 代理。

为什么需要这个：本机直连 BT 实测只有 40–130 KB/s（17 个 seed 的种也一样），
而同一台机器走 Clash 代理的 HTTP 能到 11 MB/s。aria2 的 --all-proxy 只管
HTTP/FTP 和 tracker 请求，**不管 peer 连接**，所以 aria2 救不了。
libtorrent 的 proxy_peer_connections 能真正把 peer 流量塞进 SOCKS5。

用法:
  python dl_torrent.py --magnet "magnet:?xt=..." --out dl --min 3
  python dl_torrent.py --magnet-file m.txt --out dl     # 一直下到完
"""
import argparse
import os
import sys
import time

import libtorrent as lt


def build_session(port=7897, socks=True):
    s = lt.default_settings()
    s["listen_interfaces"] = "0.0.0.0:6881,[::]:6881"
    s["alert_mask"] = lt.alert.category_t.status_notification
    s["announce_to_all_tiers"] = True
    s["announce_to_all_trackers"] = True
    s["enable_dht"] = True
    s["enable_lsd"] = True
    s["enable_upnp"] = False
    s["enable_natpmp"] = False
    if socks:
        s["proxy_type"] = int(lt.proxy_type_t.socks5)
        s["proxy_hostname"] = "127.0.0.1"
        s["proxy_port"] = port
        s["proxy_peer_connections"] = True
        s["proxy_tracker_connections"] = True
        s["proxy_hostnames"] = True
    return lt.session(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--magnet", action="append", default=[])
    ap.add_argument("--magnet-file")
    ap.add_argument("--out", default="dl")
    ap.add_argument("--port", type=int, default=7897)
    ap.add_argument("--no-socks", action="store_true")
    ap.add_argument("--min", type=float, default=0, help="跑多少分钟后强制停（0=下完为止）")
    ap.add_argument("--video-only", action="store_true", default=True,
                    help="只下视频文件，跳过 sample/nfo/srt")
    a = ap.parse_args()

    magnets = list(a.magnet)
    if a.magnet_file:
        for line in open(a.magnet_file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                magnets.append(line)
    if not magnets:
        sys.exit("给 --magnet 或 --magnet-file")

    os.makedirs(a.out, exist_ok=True)
    ses = build_session(a.port, socks=not a.no_socks)
    print("session 就绪，socks=%s:%d" % ("127.0.0.1" if not a.no_socks else "-", a.port), flush=True)

    handles = []
    for mg in magnets:
        p = lt.parse_magnet_uri(mg)
        p.save_path = a.out
        h = ses.add_torrent(p)
        handles.append(h)

    t_end = time.time() + a.min * 60 if a.min else None
    t_last = 0.0
    pruned = set()

    while True:
        time.sleep(1)
        alive = 0
        for i, h in enumerate(handles):
            st = h.status()
            if not st.has_metadata:
                alive += 1
                continue
            if i not in pruned and st.has_metadata:
                prio = []
                for fi, f in enumerate(st.torrent_file.files()):
                    low = f.path.lower()
                    keep = low.endswith((".mkv", ".mp4", ".avi", ".m4v", ".ts"))
                    prio.append(1 if keep else 4 if not a.video_only else 0)
                h.prioritize_files(prio)
                pruned.add(i)
            if st.state not in (lt.torrent_status.seeding, lt.torrent_status.finished):
                alive += 1

        now = time.time()
        if now - t_last > 15:
            t_last = now
            parts = []
            for h in handles:
                st = h.status()
                name = st.name[:38] if st.name else "?"
                parts.append("%s %d%% %dKB/s sd%d" % (
                    name, int(st.progress * 100),
                    st.download_payload_rate // 1024, st.num_seeds))
            print(" | ".join(parts), flush=True)

        if alive == 0:
            print("全部完成", flush=True)
            break
        if t_end and time.time() > t_end:
            print("到时退出（仍在跑）", flush=True)
            break

    for h in handles:
        st = h.status()
        print("%-50s %5.1f%% %s" % (st.name[:50], st.progress * 100,
                                    "OK" if st.progress >= 0.999 else "未完成"))


if __name__ == "__main__":
    main()
